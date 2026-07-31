from dataclasses import dataclass
from datetime import date
from uuid import UUID
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from audit.services import record_event
from documents.models import ElectronicReceipt
from payments.models import Payment
from .models import Sale, SaleLine

VAT_RATE = 19

@dataclass(frozen=True)
class TaxPreview:
    net: int; vat: int; total: int

def calculate_tax_preview(total: int, classification: str) -> TaxPreview:
    if total <= 0: raise ValidationError("El monto total debe ser mayor que cero.")
    if classification == Sale.TaxClassification.EXEMPT: return TaxPreview(total, 0, total)
    if classification != Sale.TaxClassification.TAXABLE: raise ValidationError("Clasificación tributaria inválida.")
    net = round(total / 1.19)
    return TaxPreview(net, total - net, total)

@transaction.atomic
def register_manual_operation(*, organization, actor, operation_date: date, payment_date: date, total: int, transfer_reference: str, detail: str, classification: str, customer_name="", customer_tax_id="", observations="", idempotency_key: UUID):
    external_id = f"manual:{idempotency_key}"
    existing = Sale.objects.filter(organization=organization, origin_system="MANUAL", external_id=external_id).first()
    if existing: return existing, False
    preview = calculate_tax_preview(total, classification)
    possible_duplicate = Payment.objects.filter(organization=organization, payment_date=payment_date, amount=total, transfer_reference=transfer_reference).exists() if transfer_reference else False
    try:
        with transaction.atomic():
            sale = Sale.objects.create(organization=organization, operation_date=operation_date, detail=detail, customer_name=customer_name, customer_tax_id=customer_tax_id, observations=observations, tax_classification=classification, net_amount=preview.net, vat_amount=preview.vat, total_amount=preview.total, reconciliation_status=Sale.ReconciliationStatus.POSSIBLE_DUPLICATE if possible_duplicate else Sale.ReconciliationStatus.PENDING, origin_system="MANUAL", external_id=external_id, created_by=actor)
    except IntegrityError:
        return Sale.objects.get(organization=organization, origin_system="MANUAL", external_id=external_id), False
    SaleLine.objects.create(sale=sale, description=detail, quantity=1, unit_amount=total, total_amount=total)
    Payment.objects.create(organization=organization, sale=sale, payment_date=payment_date, amount=total, transfer_reference=transfer_reference, created_by=actor)
    record_event(organization=organization, actor=actor, action="manual_operation.created", target=sale, metadata={"classification": classification})
    return sale, True

@transaction.atomic
def register_manual_receipt(*, organization, actor, sale, document_type: int, folio: int, tax_issue_date: date, issuer_name="", signer_name=""):
    if sale.organization_id != organization.id: raise ValidationError("La venta no pertenece a la organización.")
    if document_type == 39 and not organization.dte_39_enabled: raise ValidationError("DTE 39 no está habilitado para esta organización.")
    if document_type == 41 and not organization.dte_41_enabled: raise ValidationError("DTE 41 no está habilitado para esta organización.")
    expected = 39 if sale.tax_classification == Sale.TaxClassification.TAXABLE else 41
    if document_type != expected: raise ValidationError("El tipo DTE no coincide con la clasificación de la venta.")
    receipt = ElectronicReceipt.objects.create(organization=organization, sale=sale, document_type=document_type, folio=folio, tax_issue_date=tax_issue_date, net_amount=sale.net_amount, vat_amount=sale.vat_amount, total_amount=sale.total_amount, issuer_name=issuer_name, signer_name=signer_name, status=ElectronicReceipt.Status.ACCEPTED, created_by=actor)
    sale.status = Sale.Status.DOCUMENTED
    paid = sum(sale.payments.values_list("amount", flat=True))
    sale.reconciliation_status = Sale.ReconciliationStatus.RECONCILED if paid == receipt.total_amount else Sale.ReconciliationStatus.AMOUNT_DIFFERENCE
    sale.save(update_fields=["status", "reconciliation_status"])
    sale.payments.update(reconciled_at=timezone.now())
    record_event(organization=organization, actor=actor, action="receipt.manual_accepted", target=receipt, metadata={"folio": folio, "document_type": document_type})
    return receipt

SALE_TRANSITIONS = {"DRAFT":{"READY","CANCELLED"}, "READY":{"DOCUMENTED","OBSERVED","CANCELLED"}, "OBSERVED":{"READY","CANCELLED"}, "DOCUMENTED":set(), "CANCELLED":set()}
RECEIPT_TRANSITIONS = {"NOT_CREATED":{"PREPARED"}, "PREPARED":{"SUBMITTING"}, "SUBMITTING":{"ACCEPTED","REJECTED","UNCERTAIN"}, "UNCERTAIN":{"ACCEPTED","REJECTED"}, "ACCEPTED":{"CANCELLATION_PENDING"}, "CANCELLATION_PENDING":{"CANCELLED","REJECTED"}, "REJECTED":set(), "CANCELLED":set()}

def validate_transition(current, target, graph):
    if target not in graph.get(current, set()): raise ValidationError(f"Transición inválida: {current} → {target}")

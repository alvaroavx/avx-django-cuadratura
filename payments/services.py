from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from audit.services import record_event
from documents.models import ElectronicReceipt
from payments.models import Payment
from sales.models import Sale


@transaction.atomic
def register_historical_receipt_payment(
    *, organization, receipt_id, actor, payment_date: date, amount: int,
    transfer_reference="", source_file_hash="", source_row=None,
):
    receipt = (
        ElectronicReceipt.objects.select_for_update()
        .select_related("sale")
        .get(pk=receipt_id, organization=organization)
    )
    sale = Sale.objects.select_for_update().get(pk=receipt.sale_id, organization=organization)
    if receipt.status != ElectronicReceipt.Status.ACCEPTED or receipt.tax_issue_date is None:
        raise ValidationError("Solo se puede conciliar el pago de una boleta aceptada con fecha tributaria.")
    if sale.status != Sale.Status.DOCUMENTED:
        raise ValidationError("La venta vinculada a la boleta no está documentada.")
    if amount != receipt.total_amount or amount != sale.total_amount:
        raise ValidationError("El monto del pago no coincide con la boleta oficial.")

    existing = list(Payment.objects.select_for_update().filter(organization=organization, sale=sale))
    if existing:
        if (
            len(existing) == 1
            and existing[0].payment_date == payment_date
            and existing[0].amount == amount
            and existing[0].transfer_reference == transfer_reference
        ):
            return existing[0], False
        raise ValidationError("La venta ya tiene pagos registrados y requiere revisión.")

    payment = Payment.objects.create(
        organization=organization,
        sale=sale,
        payment_date=payment_date,
        amount=amount,
        transfer_reference=transfer_reference,
        reconciled_at=timezone.now(),
        created_by=actor,
    )
    sale.reconciliation_status = Sale.ReconciliationStatus.RECONCILED
    sale.save(update_fields=["reconciliation_status"])
    record_event(
        organization=organization,
        actor=actor,
        action="payment.historical_matched",
        target=sale,
        metadata={
            "source_file_hash": source_file_hash,
            "source_row": source_row,
            "payment_date": payment_date.isoformat(),
            "amount": amount,
            "receipt_folio": receipt.folio,
            "document_type": receipt.document_type,
        },
    )
    return payment, True

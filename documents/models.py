import uuid
from django.db import models
from django.db.models import F, Q
from organizations.models import TaxpayerOrganization
from sales.models import Sale

class ElectronicReceipt(models.Model):
    class DocumentType(models.IntegerChoices):
        TAXABLE_RECEIPT=39,"Boleta electrónica afecta"; EXEMPT_RECEIPT=41,"Boleta electrónica exenta"
    class Status(models.TextChoices):
        NOT_CREATED="NOT_CREATED","No creada"; PREPARED="PREPARED","Preparada"; SUBMITTING="SUBMITTING","Enviando"; UNCERTAIN="UNCERTAIN","Estado incierto"; ACCEPTED="ACCEPTED","Aceptada"; REJECTED="REJECTED","Rechazada"; CANCELLATION_PENDING="CANCELLATION_PENDING","Anulación pendiente"; CANCELLED="CANCELLED","Anulada"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(TaxpayerOrganization, on_delete=models.PROTECT, related_name="receipts")
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="receipts")
    document_type = models.PositiveSmallIntegerField(choices=DocumentType.choices)
    folio = models.PositiveBigIntegerField(null=True, blank=True)
    tax_issue_date = models.DateField(null=True, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    net_amount = models.PositiveBigIntegerField(default=0)
    vat_amount = models.PositiveBigIntegerField(default=0)
    total_amount = models.PositiveBigIntegerField(default=0)
    issuer_name = models.CharField(max_length=200, blank=True)
    signer_name = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.NOT_CREATED)
    track_id = models.CharField(max_length=120, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "document_type", "folio"], condition=Q(folio__isnull=False), name="uq_receipt_org_type_folio"),
            models.CheckConstraint(condition=Q(net_amount=F("total_amount")-F("vat_amount")), name="receipt_net_plus_vat_total"),
            models.CheckConstraint(condition=Q(document_type=39) | Q(vat_amount=0), name="receipt_dte41_vat_zero"),
        ]


import uuid
from django.db import models
from django.db.models import F, Q
from organizations.models import TaxpayerOrganization

class Sale(models.Model):
    class Status(models.TextChoices):
        DRAFT="DRAFT","Borrador"; READY="READY","Lista"; DOCUMENTED="DOCUMENTED","Documentada"; OBSERVED="OBSERVED","Observada"; CANCELLED="CANCELLED","Anulada"
    class TaxClassification(models.TextChoices):
        TAXABLE="TAXABLE","Afecta"; EXEMPT="EXEMPT","Exenta"
    class ReconciliationStatus(models.TextChoices):
        PENDING="PENDING","Pendiente"; RECONCILED="RECONCILED","Conciliada"; AMOUNT_DIFFERENCE="AMOUNT_DIFFERENCE","Diferencia de monto"; POSSIBLE_DUPLICATE="POSSIBLE_DUPLICATE","Posible duplicado"; CLASSIFICATION_CONFLICT="CLASSIFICATION_CONFLICT","Conflicto de clasificación"; CORRECTION_REQUIRED="CORRECTION_REQUIRED","Requiere corrección"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(TaxpayerOrganization, on_delete=models.PROTECT, related_name="sales")
    operation_date = models.DateField()
    registered_at = models.DateTimeField(auto_now_add=True)
    detail = models.CharField(max_length=500)
    customer_name = models.CharField(max_length=200, blank=True)
    customer_tax_id = models.CharField(max_length=12, blank=True)
    observations = models.TextField(blank=True)
    tax_classification = models.CharField(max_length=16, choices=TaxClassification.choices)
    net_amount = models.PositiveBigIntegerField()
    vat_amount = models.PositiveBigIntegerField()
    total_amount = models.PositiveBigIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.READY)
    reconciliation_status = models.CharField(max_length=32, choices=ReconciliationStatus.choices, default=ReconciliationStatus.PENDING)
    origin_system = models.CharField(max_length=80, default="MANUAL")
    external_id = models.CharField(max_length=160)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="created_sales")
    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(net_amount__gte=0) & Q(vat_amount__gte=0) & Q(total_amount__gt=0), name="sale_positive_amounts"),
            models.CheckConstraint(condition=Q(net_amount=F("total_amount")-F("vat_amount")), name="sale_net_plus_vat_total"),
            models.CheckConstraint(condition=Q(tax_classification="TAXABLE") | Q(vat_amount=0), name="sale_exempt_vat_zero"),
            models.UniqueConstraint(fields=["organization", "origin_system", "external_id"], name="uq_sale_org_origin_external"),
        ]

class SaleLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="lines")
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    unit_amount = models.PositiveBigIntegerField()
    total_amount = models.PositiveBigIntegerField()


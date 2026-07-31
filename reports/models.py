import uuid
from django.conf import settings
from django.db import models
from organizations.models import TaxpayerOrganization

class MonthlyClose(models.Model):
    class Status(models.TextChoices):
        OPEN="OPEN","Abierto"; HAS_EXCEPTIONS="HAS_EXCEPTIONS","Con excepciones"; READY_TO_CLOSE="READY_TO_CLOSE","Listo para cerrar"; CLOSED="CLOSED","Cerrado"; REOPENED="REOPENED","Reabierto"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(TaxpayerOrganization, on_delete=models.PROTECT, related_name="monthly_closes")
    period = models.DateField(help_text="Primer día del mes")
    version = models.PositiveIntegerField()
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="monthly_closes")
    file = models.FileField(upload_to="monthly_books/%Y/%m/", blank=True)
    file_hash = models.CharField(max_length=64, blank=True)
    total_net = models.PositiveBigIntegerField(default=0)
    total_vat = models.PositiveBigIntegerField(default=0)
    total_amount = models.PositiveBigIntegerField(default=0)
    second_category_withholding = models.PositiveBigIntegerField(default=0, verbose_name="Retención segunda categoría")
    ppm = models.PositiveBigIntegerField(default=0, verbose_name="PPM manual")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.OPEN)
    reopen_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "period", "version"], name="uq_close_org_period_version")]


import uuid
from django.conf import settings
from django.db import models
from organizations.models import TaxpayerOrganization


class ImportBatch(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "UPLOADED", "Cargado"
        VALIDATED = "VALIDATED", "Validado"
        BLOCKED = "BLOCKED", "Bloqueado"
        COMMITTED = "COMMITTED", "Confirmado"
        FAILED = "FAILED", "Fallido"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        TaxpayerOrganization, on_delete=models.PROTECT, related_name="import_batches"
    )
    period = models.DateField(help_text="Primer día del período")
    parser_version = models.CharField(max_length=40)
    original_filename = models.CharField(max_length=255)
    source_file = models.FileField(upload_to="private/imports/%Y/%m/")
    file_hash = models.CharField(max_length=64)
    file_size = models.PositiveBigIntegerField()
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uploaded_imports"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UPLOADED)
    detected_rows = models.PositiveIntegerField(default=0)
    new_rows = models.PositiveIntegerField(default=0)
    existing_rows = models.PositiveIntegerField(default=0)
    conflict_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    ignored_rows = models.PositiveIntegerField(default=0)
    taxable_rows = models.PositiveIntegerField(default=0)
    exempt_rows = models.PositiveIntegerField(default=0)
    total_net = models.PositiveBigIntegerField(default=0)
    total_vat = models.PositiveBigIntegerField(default=0)
    total_amount = models.PositiveBigIntegerField(default=0)
    declared_net = models.PositiveBigIntegerField(null=True, blank=True)
    declared_vat = models.PositiveBigIntegerField(null=True, blank=True)
    declared_total = models.PositiveBigIntegerField(null=True, blank=True)
    validation_errors = models.JSONField(default=list, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    committed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "file_hash"], name="uq_import_batch_org_hash"
            )
        ]
        ordering = ["-uploaded_at"]


class ImportRow(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "Nueva"
        ALREADY_IMPORTED = "ALREADY_IMPORTED", "Ya importada"
        CONFLICT = "CONFLICT", "Conflicto"
        ERROR = "ERROR", "Error"
        IGNORED = "IGNORED", "Ignorada"
        IMPORTED = "IMPORTED", "Importada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT, related_name="rows")
    line_number = models.PositiveIntegerField()
    original_data = models.JSONField(default=dict)
    normalized_data = models.JSONField(default=dict)
    fingerprint = models.CharField(max_length=64, blank=True)
    classification = models.CharField(max_length=16, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    errors = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices)
    sale = models.ForeignKey(
        "sales.Sale", on_delete=models.PROTECT, null=True, blank=True, related_name="import_rows"
    )
    receipt = models.ForeignKey(
        "documents.ElectronicReceipt",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="import_rows",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["batch", "line_number"], name="uq_import_row_line")
        ]
        ordering = ["line_number"]


import uuid
from django.db import models
from organizations.models import TaxpayerOrganization

class SiiProfile(models.Model):
    class Environment(models.TextChoices):
        DISABLED="DISABLED","Deshabilitado"; CERTIFICATION="CERTIFICATION","Certificación"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(TaxpayerOrganization, on_delete=models.PROTECT, related_name="sii_profile")
    environment = models.CharField(max_length=16, choices=Environment.choices, default=Environment.DISABLED)
    productive_issuance_enabled = models.BooleanField(default=False, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

class SiiSubmissionAttempt(models.Model):
    class Status(models.TextChoices):
        PREPARED="PREPARED","Preparado"; SUBMITTING="SUBMITTING","Enviando"; UNCERTAIN="UNCERTAIN","Incierto"; ACCEPTED="ACCEPTED","Aceptado"; REJECTED="REJECTED","Rechazado"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(TaxpayerOrganization, on_delete=models.PROTECT, related_name="sii_attempts")
    receipt = models.ForeignKey("documents.ElectronicReceipt", on_delete=models.PROTECT, related_name="submission_attempts")
    status = models.CharField(max_length=16, choices=Status.choices)
    track_id = models.CharField(max_length=120, blank=True)
    request_fingerprint = models.CharField(max_length=64)
    error_code = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


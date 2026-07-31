import uuid
from django.conf import settings
from django.db import models

class TaxpayerOrganization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tax_id = models.CharField("RUT", max_length=12, unique=True)
    legal_name = models.CharField("Razón social", max_length=200)
    trade_name = models.CharField("Nombre de fantasía", max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    dte_39_enabled = models.BooleanField("DTE 39 declarado", default=False)
    dte_41_enabled = models.BooleanField("DTE 41 declarado", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self): return f"{self.legal_name} ({self.tax_id})"

class OrganizationMembership(models.Model):
    class Role(models.TextChoices):
        ORGANIZATION_ADMIN = "ORGANIZATION_ADMIN", "Administrador de organización"
        ACCOUNTANT = "ACCOUNTANT", "Contadora/or"
        OPERATOR = "OPERATOR", "Operador/a"
        VIEWER = "VIEWER", "Solo lectura"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(TaxpayerOrganization, on_delete=models.PROTECT, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="organization_memberships")
    role = models.CharField(max_length=32, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "user"], name="uq_membership_org_user")]

class UserInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        ACCEPTED = "ACCEPTED", "Aceptada"
        EXPIRED = "EXPIRED", "Expirada"
        REVOKED = "REVOKED", "Revocada"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(TaxpayerOrganization, on_delete=models.PROTECT, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=32, choices=OrganizationMembership.Role.choices)
    token_digest = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sent_invitations")
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "email"], condition=models.Q(status="PENDING"), name="uq_pending_invitation_org_email")]


"""Clientes técnicos de la API de Cuadratura (ADR 0005 y 0006).

Un cliente representa a un sistema externo (p. ej. Plataforma Elemental). Se autentica
con dos factores: un token Bearer del que solo se guarda el SHA-256 y la firma Ed25519
de cada request con una llave privada que nunca sale del cliente. Solo puede operar
sobre las organizaciones vinculadas explícitamente y sus operaciones se registran con
su propio `origin_system`, que Cuadratura asigna y el cliente no puede elegir.
"""

import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

from organizations.models import TaxpayerOrganization

ORIGIN_SYSTEM_VALIDATOR = RegexValidator(
    r"^[A-Z][A-Z0-9_]{1,39}$",
    "Use mayúsculas, dígitos y guion bajo (p. ej. ELEMENTAL).",
)
RESERVED_ORIGIN_SYSTEMS = {"MANUAL", "CASHBOOK_CSV_V1"}


class ApiClient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField("Nombre", max_length=120, unique=True)
    origin_system = models.CharField(
        "Sistema de origen",
        max_length=40,
        unique=True,
        validators=[ORIGIN_SYSTEM_VALIDATOR],
        help_text="Código con el que se registran las ventas y pagos recibidos de este cliente.",
    )
    service_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="api_client",
        help_text="Usuario técnico sin acceso web; figura como autor en lotes y auditoría.",
    )
    token_prefix = models.CharField(max_length=16, unique=True)
    token_digest = models.CharField(max_length=64, unique=True)
    token_expires_at = models.DateTimeField("Token vence", null=True, blank=True)
    previous_token_prefix = models.CharField(max_length=16, blank=True)
    previous_token_digest = models.CharField(max_length=64, blank=True)
    previous_token_valid_until = models.DateTimeField(
        null=True, blank=True, help_text="Hasta cuándo sigue aceptándose el token anterior tras una rotación."
    )
    public_key = models.CharField(
        "Llave pública Ed25519",
        max_length=64,
        blank=True,
        help_text="32 bytes en base64. Verifica la firma de cada request; la llave privada queda en el cliente.",
    )
    is_active = models.BooleanField("Activo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    token_rotated_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "cliente API"
        verbose_name_plural = "clientes API"

    def __str__(self):
        return f"{self.name} ({self.origin_system})"


class ApiClientOrganization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(ApiClient, on_delete=models.PROTECT, related_name="organization_links")
    organization = models.ForeignKey(
        TaxpayerOrganization, on_delete=models.PROTECT, related_name="api_client_links"
    )
    is_active = models.BooleanField("Activo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["client", "organization"], name="uq_api_client_organization")
        ]
        verbose_name = "organización de cliente API"
        verbose_name_plural = "organizaciones de clientes API"

    def __str__(self):
        return f"{self.client} → {self.organization}"


class ApiAccessFailure(models.Model):
    """Intento rechazado contra la API. Sirve para detectar abuso y para bloquear IPs.

    Nunca guarda el token ni el cuerpo del request; solo el prefijo público del token.
    """

    class Reason(models.TextChoices):
        MISSING_TOKEN = "missing_token", "Sin token"
        INVALID_TOKEN = "invalid_token", "Token inválido"
        EXPIRED_TOKEN = "expired_token", "Token vencido"
        SIGNATURE_REQUIRED = "signature_required", "Cliente sin llave pública"
        INVALID_SIGNATURE = "invalid_signature", "Firma inválida"
        STALE_REQUEST = "stale_request", "Marca de tiempo fuera de ventana"
        REPLAYED_REQUEST = "replayed_request", "Nonce repetido"
        ORGANIZATION_NOT_ALLOWED = "organization_not_allowed", "Organización no habilitada"
        RATE_LIMITED = "rate_limited", "Límite de frecuencia"
        HTTPS_REQUIRED = "https_required", "Sin HTTPS"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    client = models.ForeignKey(
        ApiClient, on_delete=models.PROTECT, null=True, blank=True, related_name="access_failures"
    )
    token_prefix = models.CharField(max_length=16, blank=True)
    reason = models.CharField(max_length=32, choices=Reason.choices)
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=300)
    user_agent = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["ip_address", "occurred_at"], name="ix_api_failure_ip_time")]
        verbose_name = "intento fallido de API"
        verbose_name_plural = "intentos fallidos de API"

    def __str__(self):
        return f"{self.occurred_at:%Y-%m-%d %H:%M} {self.reason} {self.ip_address or '-'}"


class ApiRateCounter(models.Model):
    """Contador por ventana fija en PostgreSQL, compartido entre procesos del servidor."""

    key = models.CharField(max_length=120)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["key", "window_start"], name="uq_api_rate_counter_window")
        ]


class ApiRequestNonce(models.Model):
    """Nonce ya usado por un cliente; impide reenviar un request firmado capturado."""

    client = models.ForeignKey(ApiClient, on_delete=models.CASCADE, related_name="nonces")
    nonce = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["client", "nonce"], name="uq_api_request_nonce")]

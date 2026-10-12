import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from audit.services import record_event

from .models import RESERVED_ORIGIN_SYSTEMS, ApiClient, ApiClientOrganization

TOKEN_SCHEME = "cdr"


def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _new_token():
    prefix = secrets.token_hex(4)
    return prefix, f"{TOKEN_SCHEME}_{prefix}_{secrets.token_urlsafe(32)}"


def _audit(client, action, *, actor=None, organizations=None, metadata=None):
    """Registra el evento en cada organización afectada (la auditoría es por tenant)."""
    targets = organizations if organizations is not None else [
        link.organization for link in client.organization_links.select_related("organization")
    ]
    for organization in targets:
        record_event(
            organization=organization,
            actor=actor,
            action=action,
            target=client,
            metadata={"origin_system": client.origin_system, **(metadata or {})},
        )


def _expiry(days):
    days = settings.API_TOKEN_DEFAULT_DAYS if days is None else days
    return timezone.now() + timedelta(days=days) if days else None


def token_prefix(raw_token):
    """Prefijo público del token (sirve para registrar fallos sin guardar el secreto)."""
    parts = (raw_token or "").split("_", 2)
    if len(parts) == 3 and parts[0] == TOKEN_SCHEME and len(parts[1]) <= 16:
        return parts[1]
    return ""


def normalize_public_key(value):
    """Valida una llave pública Ed25519 en base64 y la devuelve normalizada."""
    from .security import load_public_key

    value = (value or "").strip()
    load_public_key(value)
    return value


@transaction.atomic
def create_api_client(
    *, name, origin_system, organizations=(), public_key="", expires_in_days=None, actor=None
):
    """Crea el cliente, su usuario técnico y sus vínculos. Devuelve (cliente, token).

    El token se muestra una sola vez: solo se persiste su SHA-256. `public_key` es la
    llave Ed25519 del cliente para verificar sus firmas.
    """
    try:
        public_key = normalize_public_key(public_key) if public_key else ""
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    origin_system = origin_system.strip().upper()
    if origin_system in RESERVED_ORIGIN_SYSTEMS:
        raise ValidationError(f"El sistema de origen {origin_system} está reservado.")
    user = get_user_model()(username=f"api-{origin_system.lower().replace('_', '-')}", is_active=False)
    user.set_unusable_password()
    user.full_clean()
    user.save()
    prefix, token = _new_token()
    client = ApiClient(
        name=name.strip(),
        origin_system=origin_system,
        service_user=user,
        token_prefix=prefix,
        token_digest=_digest(token),
        token_expires_at=_expiry(expires_in_days),
        public_key=public_key,
    )
    client.full_clean()
    client.save()
    for organization in organizations:
        ApiClientOrganization.objects.create(client=client, organization=organization)
    _audit(
        client,
        "api_client.created",
        actor=actor,
        metadata={"token_prefix": prefix, "signed_requests": bool(public_key)},
    )
    return client, token


@transaction.atomic
def link_api_client_organization(client, organization, *, actor=None, active=True):
    """Habilita o deshabilita un cliente en una organización, con auditoría."""
    link, _ = ApiClientOrganization.objects.get_or_create(client=client, organization=organization)
    link.is_active = active
    link.save(update_fields=["is_active"])
    _audit(
        client,
        "api_client.organization_linked" if active else "api_client.organization_unlinked",
        actor=actor,
        organizations=[organization],
    )
    return link


@transaction.atomic
def rotate_api_client_token(client, *, expires_in_days=None, grace_hours=None, actor=None):
    """Emite un token nuevo. El anterior sigue válido `grace_hours` (0 = se corta ya),
    para cambiar el secreto en el cliente sin interrumpir el servicio."""
    grace_hours = settings.API_TOKEN_ROTATION_GRACE_HOURS if grace_hours is None else grace_hours
    now = timezone.now()
    previous_prefix = client.token_prefix
    prefix, token = _new_token()
    client.previous_token_prefix = previous_prefix if grace_hours else ""
    client.previous_token_digest = client.token_digest if grace_hours else ""
    client.previous_token_valid_until = now + timedelta(hours=grace_hours) if grace_hours else None
    client.token_prefix = prefix
    client.token_digest = _digest(token)
    client.token_rotated_at = now
    client.token_expires_at = _expiry(expires_in_days)
    client.save()
    _audit(
        client,
        "api_client.token_rotated",
        actor=actor,
        metadata={"token_prefix": prefix, "previous_prefix": previous_prefix, "grace_hours": grace_hours},
    )
    return token


@transaction.atomic
def set_api_client_public_key(client, public_key, *, actor=None):
    try:
        client.public_key = normalize_public_key(public_key)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    client.save(update_fields=["public_key"])
    _audit(client, "api_client.public_key_set", actor=actor, metadata={"public_key": client.public_key})
    return client


def authenticate_token(raw_token):
    """Devuelve (cliente, None) si el token es válido, o (None, "invalid"|"expired")."""
    prefix = token_prefix(raw_token)
    if not prefix:
        return None, "invalid"
    digest = _digest(raw_token)
    client = ApiClient.objects.filter(token_prefix=prefix, is_active=True).first()
    if client is None:
        previous = ApiClient.objects.filter(
            previous_token_prefix=prefix, is_active=True, previous_token_valid_until__gt=timezone.now()
        ).first()
        if previous and hmac.compare_digest(previous.previous_token_digest, digest):
            ApiClient.objects.filter(pk=previous.pk).update(last_used_at=timezone.now())
            return previous, None
        return None, "invalid"
    if not hmac.compare_digest(client.token_digest, digest):
        return None, "invalid"
    if client.token_expires_at and client.token_expires_at <= timezone.now():
        return None, "expired"
    ApiClient.objects.filter(pk=client.pk).update(last_used_at=timezone.now())
    return client, None


def linked_organizations(client):
    return [
        link.organization
        for link in client.organization_links.select_related("organization").filter(
            is_active=True, organization__is_active=True
        ).order_by("organization__legal_name")
    ]

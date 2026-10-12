"""Controles de seguridad de la API v1 (ADR 0006).

Cada request autenticado pasa, en orden, por:
1. HTTPS obligatorio (`API_REQUIRE_HTTPS`).
2. Bloqueo temporal de la IP si acumula demasiados fallos de autenticación.
3. Token Bearer válido, activo y vigente.
4. Firma Ed25519 del request con la llave privada del cliente (segundo factor),
   marca de tiempo dentro de la ventana y nonce no usado.
5. Límite de frecuencia por cliente.

Todo rechazo queda en `ApiAccessFailure` y en el logger `cuadratura.api.security`,
sin token ni cuerpo del request.
"""

import base64
import binascii
import hashlib
import ipaddress
import logging
import re
import time
from dataclasses import dataclass
from datetime import timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import ApiAccessFailure, ApiRateCounter, ApiRequestNonce
from .services import authenticate_token, token_prefix

logger = logging.getLogger("cuadratura.api.security")

HEADER_TIMESTAMP = "X-Cuadratura-Timestamp"
HEADER_NONCE = "X-Cuadratura-Nonce"
HEADER_SIGNATURE = "X-Cuadratura-Signature"
NONCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
AUTH_FAILURE_REASONS = {
    ApiAccessFailure.Reason.MISSING_TOKEN,
    ApiAccessFailure.Reason.INVALID_TOKEN,
    ApiAccessFailure.Reason.EXPIRED_TOKEN,
    ApiAccessFailure.Reason.INVALID_SIGNATURE,
    ApiAccessFailure.Reason.STALE_REQUEST,
    ApiAccessFailure.Reason.REPLAYED_REQUEST,
}


@dataclass
class Rejection:
    status: int
    code: str
    message: str
    retry_after: int | None = None


def client_ip(request):
    """IP del cliente. Detrás de un proxy, `API_CLIENT_IP_HEADER` nombra el encabezado
    que el proxy fija (p. ej. HTTP_X_REAL_IP); nunca se confía en X-Forwarded-For crudo."""
    header = getattr(settings, "API_CLIENT_IP_HEADER", "")
    raw = (request.META.get(header) if header else None) or request.META.get("REMOTE_ADDR", "")
    raw = raw.split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


def record_failure(request, reason, *, client=None, raw_token=""):
    ip = client_ip(request)
    prefix = token_prefix(raw_token)
    ApiAccessFailure.objects.create(
        ip_address=ip,
        client=client,
        token_prefix=prefix,
        reason=reason,
        method=request.method[:10],
        path=request.path[:300],
        user_agent=request.headers.get("User-Agent", "")[:200],
    )
    logger.warning(
        "api_access_denied reason=%s ip=%s client=%s token_prefix=%s path=%s",
        reason,
        ip or "-",
        client.origin_system if client else "-",
        prefix or "-",
        request.path[:300],
    )


def https_rejection(request):
    if getattr(settings, "API_REQUIRE_HTTPS", False) and not request.is_secure():
        record_failure(request, ApiAccessFailure.Reason.HTTPS_REQUIRED)
        return Rejection(403, "https_required", "La API solo acepta conexiones HTTPS.")
    return None


def ip_block_rejection(request):
    """Bloquea temporalmente una IP con demasiados fallos de autenticación. Detrás de un
    proxy sin `API_CLIENT_IP_HEADER`, todas las llamadas comparten la IP del proxy y un
    atacante podría bloquear al cliente legítimo: configure el encabezado o use 0."""
    ip = client_ip(request)
    if ip is None or settings.API_AUTH_FAILURE_LIMIT <= 0:
        return None
    window = settings.API_AUTH_FAILURE_WINDOW_MINUTES
    failures = ApiAccessFailure.objects.filter(
        ip_address=ip,
        reason__in=AUTH_FAILURE_REASONS,
        occurred_at__gte=timezone.now() - timedelta(minutes=window),
    ).count()
    if failures >= settings.API_AUTH_FAILURE_LIMIT:
        logger.warning("api_ip_blocked ip=%s failures=%s", ip, failures)
        return Rejection(
            429,
            "too_many_failures",
            "Demasiados intentos fallidos desde esta dirección; espere antes de reintentar.",
            retry_after=window * 60,
        )
    return None


def _hit_counter(key, window_seconds):
    now = timezone.now()
    epoch = int(now.timestamp())
    window_start = now - timedelta(seconds=epoch % window_seconds, microseconds=now.microsecond)
    with transaction.atomic():
        updated = ApiRateCounter.objects.filter(key=key, window_start=window_start).update(count=F("count") + 1)
        if not updated:
            try:
                with transaction.atomic():
                    ApiRateCounter.objects.create(key=key, window_start=window_start, count=1)
            except IntegrityError:
                ApiRateCounter.objects.filter(key=key, window_start=window_start).update(count=F("count") + 1)
            ApiRateCounter.objects.filter(window_start__lt=now - timedelta(days=1)).delete()
        count = ApiRateCounter.objects.get(key=key, window_start=window_start).count
    retry_after = window_seconds - (epoch % window_seconds)
    return count, retry_after


def rate_limit_rejection(request, client):
    limit = settings.API_RATE_LIMIT_PER_MINUTE
    count, retry_after = _hit_counter(f"client:{client.pk}", 60)
    if count > limit:
        record_failure(request, ApiAccessFailure.Reason.RATE_LIMITED, client=client)
        return Rejection(
            429, "rate_limited", f"Se superó el límite de {limit} requests por minuto.", retry_after=retry_after
        )
    return None


def signing_message(method, full_path, timestamp, nonce, body):
    """Texto que el cliente firma con Ed25519 (UTF-8)."""
    return "\n".join(
        [method.upper(), full_path, str(timestamp), nonce, hashlib.sha256(body or b"").hexdigest()]
    ).encode()


def load_public_key(value):
    try:
        raw = base64.b64decode(value, validate=True)
        return Ed25519PublicKey.from_public_bytes(raw)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("La llave pública debe ser Ed25519 de 32 bytes en base64.") from exc


def signature_rejection(request, client, raw_token, body):
    Reason = ApiAccessFailure.Reason
    if not client.public_key:
        if not getattr(settings, "API_REQUIRE_SIGNATURES", True):
            return None
        record_failure(request, Reason.SIGNATURE_REQUIRED, client=client, raw_token=raw_token)
        return Rejection(
            401, "signature_required", "Este cliente no tiene llave pública registrada; las firmas son obligatorias."
        )
    timestamp = request.headers.get(HEADER_TIMESTAMP, "")
    nonce = request.headers.get(HEADER_NONCE, "")
    signature = request.headers.get(HEADER_SIGNATURE, "")
    if not (timestamp.isdigit() and NONCE_PATTERN.match(nonce) and signature):
        record_failure(request, Reason.INVALID_SIGNATURE, client=client, raw_token=raw_token)
        return Rejection(
            401,
            "invalid_signature",
            f"Faltan o son inválidos {HEADER_TIMESTAMP}, {HEADER_NONCE} o {HEADER_SIGNATURE}.",
        )
    if abs(time.time() - int(timestamp)) > settings.API_SIGNATURE_MAX_SKEW_SECONDS:
        record_failure(request, Reason.STALE_REQUEST, client=client, raw_token=raw_token)
        return Rejection(401, "stale_request", "La marca de tiempo está fuera de la ventana permitida.")
    try:
        load_public_key(client.public_key).verify(
            base64.b64decode(signature, validate=True),
            signing_message(request.method, request.get_full_path(), timestamp, nonce, body),
        )
    except (InvalidSignature, ValueError, binascii.Error):
        record_failure(request, Reason.INVALID_SIGNATURE, client=client, raw_token=raw_token)
        return Rejection(401, "invalid_signature", "La firma del request no es válida.")
    try:
        with transaction.atomic():
            ApiRequestNonce.objects.create(client=client, nonce=nonce)
    except IntegrityError:
        record_failure(request, Reason.REPLAYED_REQUEST, client=client, raw_token=raw_token)
        return Rejection(401, "replayed_request", "Este nonce ya fue usado.")
    # Evidencia de origen: se guarda con el lote para demostrar quién firmó qué.
    request.api_signature = {
        "algorithm": "Ed25519",
        "public_key": client.public_key,
        "timestamp": int(timestamp),
        "nonce": nonce,
        "body_sha256": hashlib.sha256(body or b"").hexdigest(),
        "signature": signature,
    }
    ApiRequestNonce.objects.filter(
        client=client,
        created_at__lt=timezone.now() - timedelta(seconds=2 * settings.API_SIGNATURE_MAX_SKEW_SECONDS),
    ).delete()
    return None


def authenticate_request(request, raw_token, body):
    """Aplica los controles 3 a 5 (la vista ya aplicó HTTPS y bloqueo por IP).
    Devuelve (cliente, None) o (None, Rejection)."""
    Reason = ApiAccessFailure.Reason
    client, problem = authenticate_token(raw_token)
    if client is None:
        reason = Reason.EXPIRED_TOKEN if problem == "expired" else Reason.INVALID_TOKEN
        record_failure(request, reason, raw_token=raw_token)
        if problem == "expired":
            return None, Rejection(401, "expired_token", "El token venció; solicite uno nuevo.")
        return None, Rejection(401, "invalid_token", "El token no es válido o el cliente está inactivo.")
    rejection = signature_rejection(request, client, raw_token, body) or rate_limit_rejection(request, client)
    if rejection:
        return None, rejection
    return client, None

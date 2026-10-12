"""API HTTP v1 de Cuadratura (ADR 0005 y 0006).

JSON sobre HTTPS. Cada cliente técnico se autentica con `Authorization: Bearer <token>`
y firma cada request con Ed25519 (ver `integrations/security.py`). Los errores tienen la
forma {"error": {"code", "message", "details"}}. La raíz `/api/v1/` se describe a sí
misma para que cualquier sistema pueda reconocer cómo conectarse.
"""

from datetime import date
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.core.exceptions import RequestDataTooBig, ValidationError
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from imports.models import ImportBatch
from imports.operations_v1 import CONTRACT_VERSION, MAX_JSON_SIZE, MAX_OPERATIONS
from imports.services import (
    BatchIdConflict,
    PeriodAlreadySubmitted,
    PeriodClosed,
    create_api_preview_batch,
)
from organizations.models import TaxpayerOrganization

from . import security
from .models import ApiAccessFailure
from .services import linked_organizations

API_VERSION = "v1"
SCHEMA_PATH = Path(__file__).resolve().parent / "contracts" / f"{CONTRACT_VERSION}.schema.json"
BATCH_STATUS_MEANING = {
    ImportBatch.Status.VALIDATED: "Recibido y válido; espera confirmación de una persona en Cuadratura.",
    ImportBatch.Status.BLOCKED: "Recibido con errores o conflictos; no puede confirmarse. Corrija y reenvíe.",
    ImportBatch.Status.COMMITTED: "Confirmado; las operaciones ya están registradas en Cuadratura.",
    ImportBatch.Status.FAILED: "Falló el procesamiento.",
    ImportBatch.Status.UPLOADED: "Recibido, sin validar.",
}


def api_error(status, code, message, details=None, retry_after=None):
    response = JsonResponse(
        {"error": {"code": code, "message": message, "details": details or []}},
        status=status,
        json_dumps_params={"ensure_ascii": False},
    )
    if status == 401:
        response["WWW-Authenticate"] = 'Bearer realm="cuadratura"'
    if retry_after:
        response["Retry-After"] = str(retry_after)
    return response


def rejection_response(rejection):
    return api_error(rejection.status, rejection.code, rejection.message, retry_after=rejection.retry_after)


def api_response(payload, status=200):
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})


def _bearer_token(request):
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _authenticate(request):
    """Aplica todos los controles de `security`. Devuelve (cliente, None) o (None, respuesta)."""
    for check in (security.https_rejection, security.ip_block_rejection):
        rejection = check(request)
        if rejection:
            return None, rejection_response(rejection)
    token = _bearer_token(request)
    if token is None:
        security.record_failure(request, ApiAccessFailure.Reason.MISSING_TOKEN)
        return None, api_error(
            401, "authentication_required", "Falta el encabezado Authorization: Bearer <token>."
        )
    try:
        body = request.body
    except RequestDataTooBig:
        return None, api_error(413, "payload_too_large", f"El cuerpo supera {MAX_JSON_SIZE} bytes.")
    client, rejection = security.authenticate_request(request, token, body)
    if rejection:
        return None, rejection_response(rejection)
    return client, None


def api_client_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        client, error = _authenticate(request)
        if error:
            return error
        request.api_client = client
        return view(request, *args, **kwargs)

    return wrapper


def _organization_not_allowed(request):
    security.record_failure(
        request, ApiAccessFailure.Reason.ORGANIZATION_NOT_ALLOWED, client=request.api_client
    )
    return api_error(403, "organization_not_allowed", "El cliente no está habilitado para esta organización.")


def _linked_organization(client, organization_id):
    organization = TaxpayerOrganization.objects.filter(pk=organization_id, is_active=True).first()
    if organization is None or not client.organization_links.filter(
        organization=organization, is_active=True
    ).exists():
        return None
    return organization


def _period(value):
    try:
        return date.fromisoformat(f"{value}-01")
    except ValueError:
        return None


def _batch_url(request, batch):
    return request.build_absolute_uri(
        reverse("api-v1-batch-detail", args=[batch.organization_id, f"{batch.period:%Y-%m}", batch.id])
    )


def serialize_batch(request, batch):
    metadata = batch.source_metadata or {}
    return {
        "id": str(batch.id),
        "batch_id": metadata.get("batch_id", ""),
        "organization_id": str(batch.organization_id),
        "period": f"{batch.period:%Y-%m}",
        "contract_version": batch.parser_version,
        "status": batch.status,
        "status_meaning": BATCH_STATUS_MEANING.get(batch.status, ""),
        "received_at": batch.uploaded_at.isoformat(),
        "committed_at": batch.committed_at.isoformat() if batch.committed_at else None,
        "counts": {
            "new": batch.new_rows,
            "already_imported": batch.existing_rows,
            "conflicts": batch.conflict_rows,
            "errors": batch.error_rows,
            "excluded": batch.ignored_rows,
        },
        "totals": {"net": batch.total_net, "vat": batch.total_vat, "total": batch.total_amount},
        "errors": batch.validation_errors,
        "rows": [
            {
                "line": row.line_number,
                "external_id": row.normalized_data.get("external_id") or row.original_data.get("external_id", ""),
                "status": row.status,
                "messages": [*row.errors, *row.warnings],
            }
            for row in batch.rows.all()
        ],
        "links": {
            "self": _batch_url(request, batch),
            "review": request.build_absolute_uri(
                reverse("import-preview", args=[batch.organization_id, f"{batch.period:%Y-%m}", batch.id])
            ),
        },
    }


@require_GET
def api_root(request):
    """Descubrimiento: describe la API; con token válido agrega cliente y organizaciones."""
    payload = {
        "service": "cuadratura",
        "api_version": API_VERSION,
        "authentication": {
            "type": "bearer+ed25519",
            "header": "Authorization: Bearer <token>",
            "obtain": "Un administrador de Cuadratura emite el token con `manage.py create_api_client`.",
            "signature": {
                "algorithm": "Ed25519",
                "headers": [security.HEADER_TIMESTAMP, security.HEADER_NONCE, security.HEADER_SIGNATURE],
                "message": "MÉTODO\\nRUTA_CON_QUERY\\nTIMESTAMP_UNIX\\nNONCE\\nSHA256_HEX_DEL_CUERPO",
                "encoding": "base64",
                "max_clock_skew_seconds": settings.API_SIGNATURE_MAX_SKEW_SECONDS,
                "required": settings.API_REQUIRE_SIGNATURES,
            },
            "rate_limit_per_minute": settings.API_RATE_LIMIT_PER_MINUTE,
        },
        "contracts": [
            {
                "version": CONTRACT_VERSION,
                "description": "Lote mensual de operaciones con sus pagos confirmados, en CLP enteros.",
                "schema": request.build_absolute_uri(reverse("api-v1-contract-schema", args=[CONTRACT_VERSION])),
                "limits": {"max_bytes": MAX_JSON_SIZE, "max_operations": MAX_OPERATIONS},
            }
        ],
        "endpoints": [
            {"method": "GET", "path": "/api/v1/", "description": "Esta descripción."},
            {
                "method": "POST",
                "path": "/api/v1/organizations/{organization_id}/periods/{YYYY-MM}/batches/",
                "description": "Envía un lote; queda en revisión hasta que una persona lo confirme.",
            },
            {
                "method": "GET",
                "path": "/api/v1/organizations/{organization_id}/periods/{YYYY-MM}/batches/{id}/",
                "description": "Consulta el estado y el acuse de un lote enviado.",
            },
        ],
    }
    rejection = security.https_rejection(request)
    if rejection:
        return rejection_response(rejection)
    if "Authorization" in request.headers:
        client, error = _authenticate(request)
        if error:
            return error
        payload["client"] = {"name": client.name, "origin_system": client.origin_system}
        payload["organizations"] = [
            {"id": str(org.id), "tax_id": org.tax_id, "legal_name": org.legal_name}
            for org in linked_organizations(client)
        ]
    return api_response(payload)


@require_GET
def contract_schema(request, contract_version):
    if contract_version != CONTRACT_VERSION:
        return api_error(404, "not_found", "Contrato desconocido.")
    return HttpResponse(SCHEMA_PATH.read_bytes(), content_type="application/schema+json; charset=utf-8")


@csrf_exempt
@require_http_methods(["POST"])
@api_client_required
def batch_create(request, organization_id, period):
    client = request.api_client
    organization = _linked_organization(client, organization_id)
    if organization is None:
        return _organization_not_allowed(request)
    month = _period(period)
    if month is None:
        return api_error(400, "invalid_period", "El período debe tener formato AAAA-MM.")
    if request.content_type != "application/json":
        return api_error(415, "unsupported_media_type", "El cuerpo debe enviarse como application/json.")
    content = request.body
    if len(content) > MAX_JSON_SIZE:
        return api_error(413, "payload_too_large", f"El cuerpo supera {MAX_JSON_SIZE} bytes.")
    try:
        batch, created = create_api_preview_batch(
            organization=organization,
            expected_period=month,
            client=client,
            content=content,
            signature=getattr(request, "api_signature", None),
        )
    except BatchIdConflict as exc:
        return api_error(409, "batch_id_conflict", exc.messages[0])
    except PeriodAlreadySubmitted as exc:
        return api_error(409, "period_already_submitted", exc.messages[0])
    except PeriodClosed as exc:
        return api_error(409, "period_closed", exc.messages[0])
    except ValidationError as exc:
        return api_error(400, "invalid_document", exc.messages[0], exc.messages[1:])
    response = api_response({"batch": serialize_batch(request, batch)}, status=201 if created else 200)
    response["Location"] = _batch_url(request, batch)
    return response


@require_GET
@api_client_required
def batch_detail(request, organization_id, period, batch_id):
    client = request.api_client
    organization = _linked_organization(client, organization_id)
    if organization is None:
        return _organization_not_allowed(request)
    month = _period(period)
    batch = (
        ImportBatch.objects.filter(
            pk=batch_id,
            organization=organization,
            period=month,
            source_metadata__origin_system=client.origin_system,
        )
        .prefetch_related("rows")
        .first()
        if month
        else None
    )
    if batch is None:
        return api_error(404, "not_found", "Lote no encontrado.")
    return api_response({"batch": serialize_batch(request, batch)})


def not_found(request, unmatched=""):
    return api_error(404, "not_found", "Recurso no encontrado. Consulte GET /api/v1/.")


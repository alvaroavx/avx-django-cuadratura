# API v1 de Cuadratura — guía para conectar un sistema

Decisión y razones: [ADR 0005](adr/0005-api-v1.md) y, para la seguridad, [ADR 0006](adr/0006-seguridad-api.md). Esquema del contrato:
`integrations/contracts/cuadratura-operations-v1.schema.json`. El mismo esquema se sirve
en `/api/v1/contracts/cuadratura-operations-v1.schema.json`.

## 1. Dar de alta el cliente (administrador de Cuadratura)

El sistema cliente genera primero su par de llaves Ed25519 y entrega **solo la
pública** (32 bytes en base64). Elemental lo hace con
`manage.py generar_llave_cuadratura --salida /ruta/segura/elemental.pem`.

```bash
set -a; source .env; set +a
.venv/bin/python manage.py create_api_client \
  --name "Plataforma Elemental" --origin-system ELEMENTAL \
  --organization <UUID de la organización en Cuadratura> \
  --public-key <llave pública en base64> --expires-days 365
```

- El token se imprime **una sola vez**. Entréguelo por un canal seguro y guárdelo en el
  gestor de secretos o en las variables de entorno del sistema cliente. Nunca va en
  Git, documentos ni tickets.
- **Rotar el token:** `manage.py rotate_api_client_token --origin-system ELEMENTAL`.
  El token anterior sigue válido 24 h para cambiarlo sin cortar el servicio. Si fue
  comprometido, use `--grace-hours 0`.
- **Cambiar la llave pública:** `manage.py set_api_client_public_key`.
- **Habilitar o deshabilitar una organización:**
  `manage.py link_api_client_organization --origin-system X --organization UUID [--unlink]`.
- Desde `/admin/` solo se puede desactivar el cliente. Cada cambio hecho por comando
  queda en la auditoría de la organización.

## 1b. Firmar cada request

Además del token, cada request lleva tres encabezados:

| Encabezado | Valor |
|---|---|
| `X-Cuadratura-Timestamp` | Segundos Unix actuales (reloj sincronizado; ventana ±300 s) |
| `X-Cuadratura-Nonce` | 16 a 64 caracteres `[A-Za-z0-9_-]`, único por request |
| `X-Cuadratura-Signature` | Base64 de la firma Ed25519 del mensaje |

El mensaje es UTF-8:
`MÉTODO\nRUTA_CON_QUERY\nTIMESTAMP\nNONCE\nSHA256_HEX_DEL_CUERPO`. Por ejemplo,
`POST\n/api/v1/organizations/…/periods/2026-09/batches/\n1791234567\nabc…\n9f86d…`.
Un GET sin cuerpo usa el SHA-256 de la cadena vacía.

Ejemplo en Python con `cryptography`:

```python
mensaje = "\n".join([metodo, ruta, str(int(time.time())), nonce, hashlib.sha256(cuerpo).hexdigest()])
firma = base64.b64encode(llave_privada.sign(mensaje.encode())).decode()
```

La firma, el nonce y el hash del cuerpo quedan guardados con el lote como evidencia de
origen.

## 2. Reconocer la API (sistema cliente)

`GET /api/v1/` sin token describe la API. Con `Authorization: Bearer <token>` agrega:

```json
{"client": {"name": "Plataforma Elemental", "origin_system": "ELEMENTAL"},
 "organizations": [{"id": "…uuid…", "tax_id": "77.111.222-3", "legal_name": "Taller Ficticio SpA"}]}
```

El cliente busca su organización destino por RUT y usa su `id` en las rutas.

## 3. Enviar un lote

`POST /api/v1/organizations/{id}/periods/{AAAA-MM}/batches/` con
`Content-Type: application/json` y un documento `cuadratura-operations-v1`:

```json
{
  "contract_version": "cuadratura-operations-v1",
  "batch_id": "llave-de-idempotencia-del-emisor",
  "generated_at": "2026-10-01T09:00:00-03:00",
  "period": "2026-09",
  "taxpayer": {"tax_id": "77.111.222-3", "legal_name": "Taller Ficticio SpA"},
  "source": {"organization_id": "org:1", "name": "Taller Ficticio"},
  "operations": [{
    "external_id": "op:1", "operation_date": "2026-09-03", "service_period": "2026-09",
    "detail": "Taller ficticio", "customer_name": "Persona Ficticia",
    "tax": {"classification": "TAXABLE", "net": 42017, "vat": 7983, "total": 50000},
    "payments": [{"external_id": "pay:1", "payment_date": "2026-09-03", "amount": 50000, "reference": "REF-1"}]
  }],
  "excluded_records": [{"external_id": "pay:9", "reasons": ["payment_reversed"]}],
  "summary": {"operations": 1, "payments": 1, "total_amount": 50000}
}
```

**Reglas del documento:**
- Montos en pesos enteros, con `net + vat = total` y `vat = 0` si es `EXEMPT`.
- La suma de los pagos debe ser igual a `tax.total`.
- `period` debe coincidir con el de la URL.

**Respuestas:**
- `201`: lote nuevo.
- `200`: el mismo contenido ya se había recibido con ese `batch_id`.
- En ambos casos el cuerpo trae el acuse en `batch`: `status`, `status_meaning`,
  `counts`, `totals`, `errors`, `rows` con el estado y los mensajes por operación, y
  `links.self` y `links.review`.

| `status` | Significado |
|---|---|
| `VALIDATED` | Válido; espera que una persona lo confirme en Cuadratura. |
| `BLOCKED` | Tiene errores o conflictos; corrija y reenvíe (se puede reusar `batch_id`). |
| `COMMITTED` | Confirmado; ventas y pagos creados con el `origin_system` del cliente. |

**Errores:** siempre `{"error": {"code", "message", "details"}}`.

| HTTP | `code` | Causa |
|---|---|---|
| 401 | `authentication_required` / `invalid_token` / `expired_token` | Falta el token, no es válido, el cliente está inactivo o el token venció. |
| 401 | `signature_required` / `invalid_signature` / `stale_request` / `replayed_request` | El cliente no tiene llave registrada, la firma es inválida, la marca de tiempo está fuera de la ventana o el nonce ya se usó. |
| 403 | `https_required` | Se llamó por HTTP. |
| 429 | `rate_limited` / `too_many_failures` | Se superó el límite por cliente, o la IP acumuló demasiados fallos. Respete `Retry-After`. |
| 403 | `organization_not_allowed` | La organización no está vinculada al cliente o está inactiva. |
| 400 | `invalid_document` / `invalid_period` | JSON o contrato inválido. |
| 409 | `batch_id_conflict` | `batch_id` reutilizado con otro contenido. |
| 409 | `period_already_submitted` | Ya hay un lote activo (en revisión o confirmado) de este origen para el período. |
| 409 | `period_closed` | El período tiene un cierre vigente en Cuadratura. |
| 413 / 415 | `payload_too_large` / `unsupported_media_type` | Más de 2 MiB, o un cuerpo que no es JSON. |

## 4. Consultar el estado

`GET /api/v1/organizations/{id}/periods/{AAAA-MM}/batches/{batch_id_cuadratura}/`
devuelve el mismo acuse. Un cliente solo ve los lotes de su propio origen.

## Límites actuales

- La API nunca confirma lotes, ni corrige o anula operaciones ya confirmadas.
- **Un lote activo por período y origen:** no hay correcciones por API.
- **Frecuencia:** el código limita requests por cliente y bloquea IP con fallos
  repetidos. La primera barrera contra volumen, el TLS y la lista de IP permitidas
  siguen siendo del proxy; ver el [checklist de producción](seguridad-produccion.md).

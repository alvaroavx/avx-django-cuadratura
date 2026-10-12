# ADR 0003: modelos preparados pero inactivos

Estado: propuesto, no implementado.

Los futuros modelos serán UUID y tenant-scoped cuando corresponda:

- `DigitalCertificateCredential`: organización, referencia opaca al secreto externo, huella, vigencia y estado; nunca bytes ni contraseña.
- `FolioAuthorization`: organización, tipo DTE, rango, vigencia, huella del CAF y referencia cifrada externa.
- `FolioReservation`: autorización, folio único, estado, operación, timestamps y lock/version.
- `ApiClient`: identidad técnica, digest de credencial, estado y scopes fijos.
- `ApiClientOrganization`: cliente, organización y capacidades explícitas.
- `IdempotencyRecord`: organización/cliente, clave, fingerprint, estado, respuesta estable y expiración.

No se agregan tablas hasta aprobar el contrato API o el spike SII; así se evita convertir hipótesis en esquema persistente.

## Verificación contra el código (2026-10-12)

Sigue sin implementarse: `integrations/` no tiene modelos ni migraciones. La recepción `elemental-cuadratura-v1` se implementó como carga de archivo por una persona autorizada, sin `ApiClient`, `ApiClientOrganization` ni `IdempotencyRecord`. Su idempotencia usa las restricciones únicas `(organization, origin_system, external_id)` de `Sale` y `Payment`, junto con el SHA-256 del archivo por organización y período en `ImportBatch`. Estos modelos siguen siendo una propuesta para cuando exista una API.

Actualización 2026-10-12: `ApiClient` y `ApiClientOrganization` se implementaron con la API v1 ([ADR 0005](0005-api-v1.md)). No hay scopes: el vínculo con la organización habilita el envío de lotes. `IdempotencyRecord` no se creó, porque la idempotencia usa `batch_id` y la huella en `ImportBatch.source_metadata`. Los modelos de certificado y folios siguen sin implementarse.

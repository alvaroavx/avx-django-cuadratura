# Arquitectura del primer corte

Cuadratura es un monolito modular. Las vistas resuelven la organización desde el UUID de la URL mediante `authorized_organization`; nunca aceptan una organización desde un formulario. Después delegan reglas de negocio a servicios explícitos con `transaction.atomic`. Los modelos conservan esquema y restricciones, sin llamadas externas, reglas tributarias en `save()`, ni señales.

## Decisiones del dominio

- UUID para toda identidad de dominio.
- CLP como enteros positivos; no se usa `float`.
- IVA inicial 19% mediante `calculate_tax_preview`. Para un total bruto afecto se redondea `total / 1,19`; el IVA es la diferencia exacta. Una operación exenta tiene IVA cero.
- Operación, pago, emisión tributaria, registro y conciliación tienen campos temporales distintos.
- La captura crea `Sale`, `SaleLine` y `Payment` en una transacción. La llave de doble envío se guarda como `(organization, origin_system, external_id)` único.
- Una captura manual cuyo pago coincide en organización, fecha de pago, monto y referencia de transferencia con un `Payment` existente marca la nueva venta como `POSSIBLE_DUPLICATE`; no la descarta silenciosamente. Sin referencia no se evalúa la coincidencia.
- Una boleta manual aceptada copia los importes preliminares de la venta, exige DTE habilitado y tipo coherente con la clasificación (39 afecta, 41 exenta), deja la venta `DOCUMENTED` y la marca `RECONCILED` si la suma de pagos iguala el total o `AMOUNT_DIFFERENCE` si no. Esto es carga de un documento conocido, nunca emisión.
- PostgreSQL (triggers de `audit/migrations/0002_critical_append_only.py` e `imports/migrations/0002_confirmed_imports_append_only.py`) impide actualizar una boleta aceptada y eliminar ventas, pagos, boletas, cierres, auditorías, lotes de importación confirmados y sus filas. Las actualizaciones de ventas, pagos, cierres y lotes no están bloqueadas en base de datos. Las correcciones futuras deberán crear su propio flujo auditado.
- Un período cerrado bloquea nueva captura, carga de boletas manuales e importaciones. La comprobación usa el período de la URL, no la fecha de la venta. Cerrar se rechaza si alguna venta del período (por `operation_date`) no está `RECONCILED`; esto incluye las ventas históricas `MISSING_PAYMENT_DATA`. Reabrir requiere rol, motivo (mínimo 5 caracteres) y evento de auditoría.
- La importación histórica XLSX/CSV es un flujo de dos pasos: el preview persiste lote/filas y archivo privado, pero no registros financieros; el commit bloquea el lote y crea solo filas `NEW` en una transacción. En XLSX se selecciona la hoja cuyo metadato `Periodo` coincide con el período activo.
- Una fila histórica crea `Sale + SaleLine + ElectronicReceipt` aceptada, nunca `Payment`, y usa `MISSING_PAYMENT_DATA` hasta completar datos reales del pago. Tanto CSV como XLSX guardan la venta con `origin_system=CASHBOOK_CSV_V1` y la huella de la fila como `external_id`; el RUT emisor histórico se guarda en `ElectronicReceipt.signer_name`.
- `payments.services.register_historical_receipt_payment` puede agregar después un `Payment` a una boleta aceptada si el monto coincide exactamente, y deja la venta `RECONCILED`. Es idempotente para un pago idéntico y registra `payment.historical_matched`. No tiene vista, comando ni pruebas en el repositorio; se usó para la carga descrita en [finanzas-elementos-import.md](finanzas-elementos-import.md).

## Estados

Se modelaron literalmente los estados solicitados para venta, boleta, conciliación y período. `validate_transition` (`sales/services.py`) define grafos explícitos, pero hoy solo lo ejercitan las pruebas: los servicios asignan estados directamente. `MonthlyClose` usa en la práctica solo `CLOSED` y `REOPENED`; `OPEN`, `HAS_EXCEPTIONS` y `READY_TO_CLOSE` existen en el modelo sin flujo que los asigne. En el futuro, un timeout desde `SUBMITTING` solo puede pasar a `UNCERTAIN`; desde allí se consulta antes de aceptar o rechazar y no se reserva/emite otro folio.

## Autorización

`PLATFORM_ADMIN` es global en `User`; un superusuario también se considera administrador de plataforma. Los roles de organización (`ORGANIZATION_ADMIN`, `ACCOUNTANT`, `OPERATOR`, `VIEWER`) están en una membresía única por usuario y organización. No existe editor genérico de permisos. Las capacidades viven en `organizations/access.py`: lectura para todos los roles; captura (`WRITE_ROLES`) para administrador, contadora/or y operador/a; importación, cierre, reapertura y vista de auditoría (`IMPORT_ROLES`/`CLOSE_ROLES`) para administrador y contadora/or; membresías e invitaciones (`ADMIN_ROLES`) solo para administrador de organización. Crear o editar contribuyentes y el alta controlada de usuarios son exclusivos del administrador de plataforma. La navegación se oculta según rol y el servidor vuelve a comprobar cada acción.

## Límites deliberados

No hay tareas asíncronas, SPA, microservicios ni emisión SII. La única API es la de recepción de lotes (ver [API v1](#api-v1)). Las invitaciones se crean con digest SHA-256 y caducidad, pero el transporte por correo y la pantalla de aceptación son trabajo posterior. El administrador de plataforma dispone además de alta controlada: crea usuario y membresía en una transacción, guarda la contraseña inicial con el hasher de Django y no la registra en auditoría.

## API v1

`integrations.api` expone `/api/v1/` ([ADR 0005](adr/0005-api-v1.md), [guía](api-v1.md)). El documento `cuadratura-operations-v1` se valida en `imports/operations_v1.py`. Produce filas normalizadas con la misma forma que Elemental v1, así que la clasificación (`classify_elemental`) y la confirmación (`commit_batch`) son compartidas y ahora reciben el `origin_system` del cliente. El lote guarda en `source_metadata` el origen, el `batch_id` y la huella del contenido; con eso se resuelve la idempotencia sin tablas nuevas. Un origen admite a lo sumo un lote activo (en revisión o confirmado) por período: otro `batch_id` responde 409 `period_already_submitted`. La autenticación, la firma y los límites viven en `integrations/security.py` ([ADR 0006](adr/0006-seguridad-api.md)). El autor del lote es el usuario técnico del cliente; quien confirma es una persona con `IMPORT_ROLES`. En la confirmación, `observations` registra «Período de servicio informado por {origen}» cuando viene `service_period`.

## Recepción Elemental v1

`imports.elemental_v1` valida y normaliza el contrato `elemental-cuadratura-v1`; `imports.services` persiste la previsualización y confirma. Esta separación permite reemplazar el archivo por una API sin reimplementar clasificación, idempotencia ni escritura financiera.

Una operación Elemental crea una `Sale` `READY` con `reconciliation_status=RECONCILED`, una `SaleLine`, uno o varios `Payment` y ninguna `ElectronicReceipt`. `Sale` y `Payment` guardan `origin_system=ELEMENTAL` y su identificador externo; `beneficiary.display_name` se copia a `Sale.customer_name`, `service_period` queda como texto en `observations` y `payments[].reference` en `Payment.transfer_reference`. Restricciones únicas de base de datos y bloqueo de la organización serializan confirmaciones concurrentes. Si otra confirmación ya creó la misma operación idéntica, la fila pasa a `ALREADY_IMPORTED` sin error; si cambió, la confirmación completa se revierte.

Como la venta queda `RECONCILED` sin boleta, no aparece en la hoja `Excepciones` ni bloquea el cierre, pero el panel mensual la cuenta como pendiente mientras no esté `DOCUMENTED`. La venta se ubica en el mes de `operation_date`, que puede ser anterior al `selection.period` del archivo. El bloqueo por período cerrado solo evalúa `selection.period`.

Un identificador existente idéntico es no-op. Se comparan fecha de operación, detalle, clasificación, montos y, por pago, identificador, fecha y monto (no la referencia ni el nombre). Contenido distinto, pago externo ya existente sin su operación o coincidencia de `operation_date` y `total_amount` con una venta que no proviene de Elemental es conflicto; entre ventas Elemental solo decide el identificador. La coincidencia con ventas no Elemental se evalúa en la previsualización y no se repite al confirmar. No se sobrescribe una venta documentada y nunca se enlaza por nombre, fecha y monto.

Contrato y ejemplo ficticio: [docs/contracts](contracts/).

### Qué valida realmente el receptor

El receptor no ejecuta el JSON Schema; valida en código (`imports/elemental_v1.py`). Diferencias con `elemental-cuadratura-v1.schema.json`:

- Exige `contract_version`, `origin_system=ELEMENTAL`, `batch_id` (texto de hasta 64 caracteres, sin exigir hexadecimal), `generated_at` ISO, `selection.period`, `source_organization.external_id/name`, `expected_taxpayer.tax_id/legal_name` y `operations` (lista de hasta 5000).
- No exige ni valida `selection.timezone`, `selection.criterion`, `concept`, `plan`, `discipline`, `buyer`, `beneficiary.external_id`, `payments[].method`, `pending_records[].entity_type` ni `summary.operations/payments/pending`. `pending_records` y `payments[].reference` son opcionales. Se ignoran campos adicionales (el esquema declara `additionalProperties: false`).
- `tax.net` debe ser mayor que cero (el esquema admite 0); `tax.vat` debe ser cero si es `EXEMPT`; `net + vat = total`; la suma de pagos debe igualar `tax.total`; cada pago debe ser `CONFIRMED`; los identificadores de operación y de pago no se repiten dentro del archivo.
- `summary.total_payments` debe igualar la suma de totales de las operaciones válidas; si difiere, el lote queda bloqueado.
- No comprueba que `payment_date` pertenezca a `selection.period` ni que `operation_date` esté en un período abierto.
- `pending_records` se muestran como filas `IGNORED` («Pendientes informados por Elemental») y no crean registros.
- Idempotencia de archivo: un archivo con el mismo SHA-256 para la misma organización y período devuelve el lote existente. `batch_id` solo se conserva en `ImportBatch.source_metadata` y no participa en la idempotencia.

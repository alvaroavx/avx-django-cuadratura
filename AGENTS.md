# AGENTS.md

## Propósito

Cuadratura es un backoffice Django multiempresa para ventas, pagos, boletas manuales, importación histórica, conciliación y cierres. No integra ni emite ante SII: el gateway actual falla de forma cerrada.

## Antes de trabajar

Lee `README.md`, `docs/README.md`, `docs/architecture.md`, `docs/security.md`, `docs/monthly-book.md` y los ADR. Verifica código y tests antes de cambiar comportamiento sensible.

## Directorios importantes

- `organizations/`: tenants, membresías y autorización por organización.
- `sales/`, `payments/`, `documents/`: operación financiera, DTE y conciliación.
- `imports/`: preview/commit de XLSX/CSV histórico y JSON `elemental-cuadratura-v1`, más archivo privado. El contrato está en `docs/contracts/`; las diferencias entre esquema y validación real, en `docs/architecture.md`.
- `reports/`: libro provisional, exportación de boletas, cierre, reapertura y vista de auditoría.
- `integrations/`: reservado, sin modelos (ADR-0003).
- `audit/`: eventos append-only; no registrar referencias de pago ni secretos.
- `sii/`: contrato deshabilitado, no emisión real.

## Invariantes

- La organización procede del UUID de URL y la autorización servidor se resuelve con `authorized_organization`; no aceptar tenant desde formularios.
- Montos CLP son enteros; operaciones compuestas usan servicios transaccionales.
- Períodos cerrados bloquean captura; reapertura exige permiso, motivo y auditoría.
- No elimines ni actualices entidades que PostgreSQL protege como append-only.

## Validación y seguridad

Las pruebas requieren PostgreSQL y un rol con `CREATEDB`, o un clúster desechable. Ejecuta los comandos de `README.md`, que también documenta la prueba que hoy falla; revisa aislamiento multiempresa, idempotencia, auditoría e importaciones. Nunca agregues secretos, CAF, certificados o llaves privadas al repositorio, logs o fixtures.

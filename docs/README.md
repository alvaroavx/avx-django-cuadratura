# Documentación IA First — Cuadratura

Última revisión documental: 2026-10-12 (auditoría contra el código). Estado: reconstruido desde el repositorio; la documentación orienta, pero el código y las restricciones PostgreSQL vigentes son la fuente final de verdad.

| Objetivo | Documentos |
|---|---|
| Entender producto y reglas financieras | [README raíz](../README.md) → [arquitectura](architecture.md) → [libro mensual](monthly-book.md) |
| Revisar aislamiento y datos sensibles | [seguridad](security.md) → ADR de `docs/adr/` |
| Modificar importaciones | ADR-0004, `imports/`, sus parser/services/tests y el contrato de archivo privado |
| Recibir datos de Plataforma Elemental | [arquitectura § Recepción Elemental v1](architecture.md#recepción-elemental-v1), [contrato y ejemplo](contracts/), `imports/elemental_v1.py`, `imports/tests/test_elemental_v1.py` |
| Modificar cierre o exportación | [libro mensual](monthly-book.md), `reports/`, `static/js/receipt-export.js`, `audit/` y pruebas de reportes |
| Revisar pagos de alumnos vinculados y honorarios pendientes | [importación de Finanzas Elementos](finanzas-elementos-import.md) |
| Preparar ejecución local | [README raíz](../README.md), `.env.example`, `compose.yaml`, `config/settings.py` |

## Arquitectura verificable

Monolito modular Django server-rendered con PostgreSQL. Las vistas obtienen organización por UUID de ruta y delegan operaciones financieras a servicios transaccionales. Los modelos y migraciones conservan restricciones de dinero, estados, idempotencia e inmutabilidad; la autorización se vuelve a comprobar en servidor. No hay SPA, API pública, workers, comandos de management propios ni emisión SII real. Elemental entrega datos mediante un archivo JSON cargado manualmente.

## Cobertura documental existente

- `architecture.md`: decisiones de dominio, estados, transacciones, roles, límites del primer corte y recepción Elemental v1, incluida su diferencia con el esquema.
- `security.md`: aislamiento tenant, auditoría, límites de carga, admin de Django y secretos.
- `monthly-book.md`: contrato y límites de exportación/cierre mensual y exportación interactiva de boletas.
- `finanzas-elementos-import.md`: carga puntual de pagos de alumnos y qué parte quedó versionada.
- `ui-direction.md`: tokens y criterios visuales (coinciden con `static/css/app.css`).
- `contracts/`: esquema JSON y ejemplo ficticio de `elemental-cuadratura-v1` (copia idéntica a la del workspace padre).
- `adr/`: decisiones sobre monolito, SII, integraciones e importación versionada; cada ADR termina con una verificación contra el código.

## Límites y precauciones

Infraestructura productiva, TLS, backups, retención, monitoreo y aceptación contable final no están certificados por el repositorio. Los documentos no autorizan migraciones, despliegues ni acceso a datos reales. Cualquier cambio funcional debe actualizar esta documentación y la evidencia específica afectada.

Estado de pruebas al 2026-10-12: 57 de 58 pasan; ver la sección Pruebas del [README raíz](../README.md#pruebas).

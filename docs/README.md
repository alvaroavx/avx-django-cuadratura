# Documentación IA First — Cuadratura

Última revisión documental: 2026-09-10. Estado: reconstruido desde el repositorio; la documentación orienta, pero el código y las restricciones PostgreSQL vigentes son la fuente final de verdad.

| Objetivo | Documentos |
|---|---|
| Entender producto y reglas financieras | [README raíz](../README.md) → [arquitectura](architecture.md) → [libro mensual](monthly-book.md) |
| Revisar aislamiento y datos sensibles | [seguridad](security.md) → ADR de `docs/adr/` |
| Modificar importaciones | ADR-0004, `imports/`, sus parser/services/tests y el contrato de archivo privado |
| Modificar cierre o exportación | [libro mensual](monthly-book.md), `reports/`, `audit/` y pruebas de reportes |
| Preparar ejecución local | [README raíz](../README.md), `.env.example`, `compose.yaml`, `config/settings.py` |

## Arquitectura verificable

Monolito modular Django server-rendered con PostgreSQL. Las vistas obtienen organización por UUID de ruta y delegan operaciones financieras a servicios transaccionales. Los modelos y migraciones conservan restricciones de dinero, estados, idempotencia e inmutabilidad; la autorización se vuelve a comprobar en servidor. No hay SPA, API pública, workers ni emisión SII real.

## Cobertura documental existente

- `architecture.md`: decisiones de dominio, estados, transacciones y límites del primer corte.
- `security.md`: aislamiento tenant, auditoría, cargas CSV y secretos.
- `monthly-book.md`: contrato y límites de exportación/cierre mensual.
- `adr/`: decisiones confirmadas sobre monolito, SII, integraciones e importación versionada.

## Límites y precauciones

Infraestructura productiva, TLS, backups, retención, monitoreo y aceptación contable final no están certificados por el repositorio. Los documentos no autorizan migraciones, despliegues ni acceso a datos reales. Cualquier cambio funcional debe actualizar esta documentación y la evidencia específica afectada.

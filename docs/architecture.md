# Arquitectura del primer corte

Cuadratura es un monolito modular. Las vistas resuelven la organización desde el UUID de la URL mediante `authorized_organization`; nunca aceptan una organización desde un formulario. Después delegan reglas de negocio a servicios explícitos con `transaction.atomic`. Los modelos conservan esquema y restricciones, sin llamadas externas, reglas tributarias en `save()`, ni señales.

## Decisiones del dominio

- UUID para toda identidad de dominio.
- CLP como enteros positivos; no se usa `float`.
- IVA inicial 19% mediante `calculate_tax_preview`. Para un total bruto afecto se redondea `total / 1,19`; el IVA es la diferencia exacta. Una operación exenta tiene IVA cero.
- Operación, pago, emisión tributaria, registro y conciliación tienen campos temporales distintos.
- La captura crea `Sale`, `SaleLine` y `Payment` en una transacción. La llave de doble envío se guarda como `(organization, origin_system, external_id)` único.
- Un mismo monto, fecha, referencia y organización marca la nueva venta como posible duplicado; no la descarta silenciosamente.
- Una boleta manual aceptada copia los importes preliminares de la venta y luego concilia pago contra documento. Esto es carga de un documento conocido, nunca emisión.
- PostgreSQL impide actualizar una boleta aceptada y eliminar ventas, pagos, boletas, cierres o auditorías. Las correcciones futuras deberán crear su propio flujo auditado.
- Un período cerrado bloquea nueva captura. Reabrir requiere rol, motivo y evento de auditoría.
- La importación histórica XLSX/CSV es un flujo de dos pasos: el preview persiste lote/filas y archivo privado, pero no registros financieros; el commit bloquea el lote y crea solo filas `NEW` en una transacción. En XLSX se selecciona la hoja cuyo metadato `Periodo` coincide con el período activo.
- Una fila histórica crea `Sale + SaleLine + ElectronicReceipt` aceptada, nunca `Payment`, y usa `MISSING_PAYMENT_DATA` hasta completar datos reales del pago.

## Estados

Se modelaron literalmente los estados solicitados para venta, boleta, conciliación y período. `validate_transition` mantiene grafos explícitos. En el futuro, un timeout desde `SUBMITTING` solo puede pasar a `UNCERTAIN`; desde allí se consulta antes de aceptar o rechazar y no se reserva/emite otro folio.

## Autorización

`PLATFORM_ADMIN` es global en `User`. Los roles de organización (`ORGANIZATION_ADMIN`, `ACCOUNTANT`, `OPERATOR`, `VIEWER`) están en una membresía única por usuario y organización. No existe editor genérico de permisos. La navegación se oculta según rol y el servidor vuelve a comprobar cada acción.

## Límites deliberados

No hay API, tareas asíncronas, SPA, microservicios ni emisión SII. Las invitaciones se crean con digest SHA-256 y caducidad, pero el transporte por correo y la pantalla de aceptación son trabajo posterior. El administrador de plataforma dispone además de alta controlada: crea usuario y membresía en una transacción, guarda la contraseña inicial con el hasher de Django y no la registra en auditoría.
# Recepción Elemental v1

`imports.elemental_v1` valida y normaliza el contrato `elemental-cuadratura-v1`; `imports.services` persiste la previsualización y confirma. Esta separación permite reemplazar el archivo por una API sin reimplementar clasificación, idempotencia ni escritura financiera.

Una operación Elemental crea una `Sale` `READY`, uno o varios `Payment` y ninguna `ElectronicReceipt`. `Sale` y `Payment` guardan `origin_system=ELEMENTAL` y su identificador externo. Restricciones únicas de base de datos y bloqueo de la organización serializan confirmaciones concurrentes.

Un identificador existente idéntico es no-op. Contenido distinto, pago externo huérfano o coincidencia de fecha y monto con una venta que no proviene de Elemental es conflicto; entre ventas Elemental solo decide el identificador. No se sobrescribe una venta documentada y nunca se enlaza por nombre, fecha y monto.

Contrato y ejemplo ficticio: [docs/contracts](contracts/).

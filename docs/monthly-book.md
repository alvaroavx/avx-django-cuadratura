# Libro mensual provisional

La exportación crea dos hojas y su hoja principal usa el mismo contrato admitido para importar:

- `<Mes> <Año>`: metadatos de RUT, razón social y período; luego correlativo, tipo de operación, folio, tipo de documento, RUT emisor, clasificación, fecha, detalle, neto, IVA y total, una fila `Total` y las líneas `IVA débito fiscal`, `Retención segunda categoría` y `PPM`. Incluye solo boletas `ACCEPTED` con fecha tributaria en el período y puede volver a cargarse como XLSX en ese mismo período. `Tipo Documento` siempre dice «Boleta Electrónica»; la columna `Rut Emisor` contiene `signer_name` o, si falta, `issuer_name` de la boleta (en filas importadas, el valor histórico de esa columna), no el RUT del contribuyente.
- `Excepciones`: ventas con `operation_date` en el período cuya conciliación no está `RECONCILED`. Rechazadas, inciertas y pendientes nunca se mezclan con el libro.

La descarga provisional (`.../exportar/`) está disponible para cualquier rol con lectura. El cierre (`.../cerrar/`) se rechaza si la hoja `Excepciones` tiene alguna fila, por ejemplo ventas históricas `MISSING_PAYMENT_DATA`, o si ya existe un cierre `CLOSED` para el período. Las ventas Elemental quedan `RECONCILED` sin boleta, de modo que no figuran en el libro ni en `Excepciones`.

Retención de segunda categoría y PPM son entradas manuales del cierre y aparecen como tales. No se derivan de boletas. El cierre almacena organización, primer día del período, versión, fecha/usuario, archivo (`media/monthly_books/AAAA/MM/`), SHA-256, totales y estado. Reabrir cambia el cierre vigente a `REOPENED`; un nuevo cierre crea la versión siguiente.

La planilla histórica usa hojas mensuales con once columnas base: correlativo, tipo de operación, número/tipo de documento, RUT emisor, afecta/no afecta, fecha, detalle, neto, IVA y total. La exportación conserva ese contrato, normaliza montos a CLP enteros y escribe RUT, razón social y período en la cabecera. No replica fórmulas históricas inconsistentes: exporta valores canónicos donde `neto + IVA = total`. El archivo fuente queda fuera de Git porque contiene datos personales.

Pendiente para declarar conformidad definitiva:

1. Confirmar con la contadora si requiere conservar fórmulas o estilos adicionales además del contrato de columnas ya soportado.
2. Confirmar semántica y obligatoriedad del RUT emisor histórico.
3. Crear una prueba dorada anonimizada y versionable; la planilla personal original permanece fuera de Git.

## Exportación interactiva de boletas registradas

La pantalla mensual permite abrir **Exportar a Excel** y revisar las boletas
aceptadas del contribuyente y período activos (vista previa JSON en
`.../boletas/exportacion/` y descarga en `.../boletas/exportacion.xlsx`, hoja
`Boletas`, para cualquier rol con lectura). La grilla permite seleccionar y
copiar rangos tabulados, copiar el conjunto completo con o sin encabezados y
descargar las mismas filas como XLSX. El filtro de excepciones activo en la
pantalla se envía a la exportación y nunca se exporta solo la porción visible de
la tabla.

El filtro se aplica sobre las boletas aceptadas: `pending` deja las aceptadas
cuya venta no está `DOCUMENTED` e `historical_incomplete` las de ventas
`MISSING_PAYMENT_DATA`. Como la base son solo boletas aceptadas, `rejected` y
`uncertain` siempre devuelven cero filas (`reports/services.py`,
`receipt_export_queryset`).

Esta exportación contiene una fila por `ElectronicReceipt` aceptada, ordenada por
fecha tributaria, tipo, folio e identificador. `Fecha de Operación` corresponde a
`tax_issue_date`, no a la creación o importación del registro. `Rut Emisor` es el
RUT de la organización activa. Las descripciones de varias líneas se consolidan
en una celda y los montos provienen de la boleta, por lo que no se multiplican por
líneas ni pagos.

Boletas rechazadas, inciertas, anuladas o todavía en trámite no se presentan como
ingresos válidos. La vista informa cuántos documentos del período quedaron fuera.
Copiar o descargar es una operación de lectura: no modifica documentos, no emite
ante el SII y no cierra el período.

## Importación desde Elemental

La pantalla Importación acepta JSON `elemental-cuadratura-v1` además de XLSX y CSV. Comprueba versión, UTF-8, tamaño máximo de 2 MiB, hasta 5000 operaciones, estructura, RUT destino, que `selection.period` sea el período activo, tipos, longitudes, montos, la suma de pagos por operación y `summary.total_payments`. La previsualización separa nuevas, idénticas, conflictos, errores y pendientes declarados por Elemental. La confirmación es atómica y no cierra el período. Las operaciones importadas no generan boletas, por lo que no aparecen en este libro ni en la exportación de boletas hasta que se registre una boleta manual. Detalle de validaciones y diferencias con el esquema: [arquitectura](architecture.md#qué-valida-realmente-el-receptor).

# Libro mensual provisional

La exportación crea dos hojas y su hoja principal usa el mismo contrato admitido para importar:

- `<Mes> <Año>`: metadatos de RUT, razón social y período; luego correlativo, tipo de operación, folio, tipo de documento, RUT emisor, clasificación, fecha, detalle, neto, IVA y total. Incluye solo boletas `ACCEPTED` y puede volver a cargarse como XLSX en ese mismo período.
- `Excepciones`: ventas cuya conciliación no está `RECONCILED`. Rechazadas, inciertas y pendientes nunca se mezclan con el libro.

Retención de segunda categoría y PPM son entradas manuales del cierre y aparecen como tales. No se derivan de boletas. El cierre almacena organización, primer día del período, versión, fecha/usuario, archivo, SHA-256, totales y estado.

La planilla histórica usa hojas mensuales con once columnas base: correlativo, tipo de operación, número/tipo de documento, RUT emisor, afecta/no afecta, fecha, detalle, neto, IVA y total. La exportación conserva ese contrato, normaliza montos a CLP enteros y escribe RUT, razón social y período en la cabecera. No replica fórmulas históricas inconsistentes: exporta valores canónicos donde `neto + IVA = total`. El archivo fuente queda fuera de Git porque contiene datos personales.

Pendiente para declarar conformidad definitiva:

1. Confirmar con la contadora si requiere conservar fórmulas o estilos adicionales además del contrato de columnas ya soportado.
2. Confirmar semántica y obligatoriedad del RUT emisor histórico.
3. Crear una prueba dorada anonimizada y versionable; la planilla personal original permanece fuera de Git.

## Exportación interactiva de boletas registradas

La pantalla mensual permite abrir **Exportar a Excel** y revisar las boletas
aceptadas del contribuyente y período activos. La grilla permite seleccionar y
copiar rangos tabulados, copiar el conjunto completo con o sin encabezados y
descargar las mismas filas como XLSX. Los filtros de excepciones de la pantalla
se conservan y nunca se exporta solo la porción visible de la tabla.

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

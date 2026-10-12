# ADR 0004: importación histórica XLSX/CSV versionada

Estado: aceptado.

Los formatos `cashbook_xlsx_v1` y `cashbook_csv_v1` reconocen metadatos, cabecera, operaciones y footer del libro histórico. En XLSX se procesa la hoja cuyo `Periodo` coincide con el período activo; las demás hojas se ignoran. No existe editor genérico de mapeos. Los parsers admiten montos canónicos y la inversión histórica de `Monto Neto`/`Monto Total`, conservando datos originales y normalizando a CLP enteros antes de persistir.

El preview no crea ventas, pagos ni boletas. El commit usa bloqueo de lote y `transaction.atomic`; filas idénticas son no-op, folios distintos son conflicto y cualquier conflicto/error bloquea todo. Las ventas importadas quedan documentadas con `MISSING_PAYMENT_DATA`, porque el CSV no prueba fecha ni referencia de pago. No se cierra el período ni se llama al SII.

Los archivos se almacenan de forma privada, con hash y procedencia. Los lotes confirmados y filas importadas no pueden eliminarse. Roles iniciales: administrador de plataforma, administrador de organización y contadora/or.

## Verificación contra el código (2026-10-12)

- CSV (`cashbook_csv_v1`): exige fila de totales y que coincida con la suma calculada; el período sale del metadato `Periodo`/`Período` de la cabecera.
- XLSX (`cashbook_xlsx_v1`): toma el período activo; si ninguna hoja o más de una tiene ese `Periodo`, el lote se bloquea. La fila de totales es opcional (solo genera advertencia) y no se contrasta con lo calculado. Una fila exenta con IVA se normaliza a IVA cero con advertencia. Se ignoran las filas cuyo `Tipo de Operación` no es «Ingreso».
- Conflictos: un folio repetido dentro del archivo, o un folio existente cuyos datos difieren (estado, fecha, montos, detalle o clasificación), es conflicto. Además, una fecha tributaria fuera del período o un DTE no habilitado para la organización es error.
- Ambos formatos crean ventas con `origin_system=CASHBOOK_CSV_V1`; la versión real del parser se conserva en `ImportBatch.parser_version`.
- El mismo flujo de preview/commit admite desde 2026-09-30 el contrato JSON `elemental-cuadratura-v1` (ver `docs/architecture.md`). Ese contrato no tiene ADR propio. Desde 2026-10-12 el mismo flujo recibe también `cuadratura-operations-v1` por la API ([ADR 0005](0005-api-v1.md)).

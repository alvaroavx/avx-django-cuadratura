# Evaluación de importación de Finanzas Elementos

Estado: importación de pagos de alumnos realizada desde el 27 de junio de 2025. Las demás secciones de la planilla quedan fuera de esta carga.

## Fuente y objetivo

`data/Finanzas Elementos.xlsx` contiene ingresos de alumnos, otros ingresos, gastos y pagos a profesores entre 2023 y 2026. El archivo original permanece fuera de Git porque contiene datos personales y referencias de transferencias.

El objetivo acordado no es conservar toda la historia. Las boletas aceptadas ya registradas en Cuadratura son el universo oficial. Se buscó el pago de alumno correspondiente a cada boleta. La planilla aporta evidencia histórica de pago, pero no reemplaza ni corrige documentos oficiales.

## Evidencia observada

- La primera fila con folio y fecha de boleta en la planilla es el folio 2 del 11 de marzo de 2025.
- La primera boleta aceptada actualmente disponible en Cuadratura tiene fecha 27 de junio de 2025.
- Se usó como corte la fecha tributaria de la primera boleta ya registrada en Cuadratura: 27 de junio de 2025. La fila del 11 de marzo de 2025 no se tomó como fuente legal ni se importó.
- Se contrastaron 191 boletas aceptadas desde el corte, por $5.313.100.
- Se encontraron 117 pagos con coincidencia única por tipo DTE, folio, fecha tributaria y monto. Suman $3.215.000 y quedaron vinculados a sus ventas.
- Una boleta tiene dos filas posibles con el mismo tipo, folio, fecha y monto. Se dejó sin pago por ambigüedad.
- Siete boletas tienen filas con el mismo tipo, folio y fecha, pero sus montos no coinciden. Se dejaron sin pago.
- En 66 boletas no se encontró una fila identificable en la fuente. Se dejaron sin pago.
- Otros ocho pagos de alumnos por $120.600 no tienen una boleta oficial identificable y se ignoraron, como se solicitó.
- No se importaron las secciones de profesores, gastos ni otros ingresos. La retención docente queda para una futura carga basada en información oficial de honorarios.
- El modelo `Payment` actual representa dinero recibido y exige una venta asociada. No sirve para registrar egresos a profesores sin mezclar conceptos opuestos.

## Criterio propuesto

1. Cada boleta oficial es el registro rector. El pago solo se incorpora si existe una única fila compatible por tipo DTE, folio, fecha tributaria y monto exacto.
2. La fecha de pago y la referencia de transferencia se conservan en el pago. Los nombres de alumnos de la planilla no se copian a la venta.
3. Las coincidencias importadas se registran con transacción, eventos de auditoría y hash de la fuente. Volver a procesar las mismas filas no duplica pagos.
4. Los casos ambiguos, con diferencia de monto o sin fila se mantienen sin pago. No se altera la boleta oficial.
5. Los pagos a profesores, sus retenciones, gastos y otros ingresos no se incluyen en esta carga.

## Próxima fuente

La siguiente carga queda a la espera del informe oficial del SII sobre boletas de honorarios emitidas. Ese informe permitirá asociar egresos de profesores y retenciones con evidencia oficial.

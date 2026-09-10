# ADR 0004: importación histórica CSV versionada

Estado: aceptado.

El formato `cashbook_csv_v1` reconoce metadatos, cabecera, operaciones y footer del libro histórico. No existe editor genérico de mapeos. El parser admite montos canónicos y la inversión histórica de `Monto Neto`/`Monto Total`, conservando datos originales y normalizando antes de persistir.

El preview no crea ventas, pagos ni boletas. El commit usa bloqueo de lote y `transaction.atomic`; filas idénticas son no-op, folios distintos son conflicto y cualquier conflicto/error bloquea todo. Las ventas importadas quedan documentadas con `MISSING_PAYMENT_DATA`, porque el CSV no prueba fecha ni referencia de pago. No se cierra el período ni se llama al SII.

Los archivos se almacenan de forma privada, con hash y procedencia. Los lotes confirmados y filas importadas no pueden eliminarse. Roles iniciales: administrador de plataforma, administrador de organización y contadora/or.


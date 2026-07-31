# Libro mensual provisional

La exportación crea dos hojas:

- `Libro provisional`: solo boletas `ACCEPTED`, con contribuyente, período, correlativo del reporte, operación, folio, DTE, emisor, firmante separado, clasificación, fecha de operación, detalle, neto, IVA, total y totales mensuales.
- `Excepciones`: ventas cuya conciliación no está `RECONCILED`. Rechazadas, inciertas y pendientes nunca se mezclan con el libro.

Retención de segunda categoría y PPM son entradas manuales del cierre y aparecen como tales. No se derivan de boletas. El cierre almacena organización, primer día del período, versión, fecha/usuario, archivo, SHA-256, totales y estado.

La planilla histórica disponible al cierre fue `docs/Libro Caja Espacio Elementos.xlsx`. Sus hojas mensuales usan once columnas base: correlativo, tipo de operación, número/tipo de documento, RUT emisor, afecta/no afecta, fecha, detalle, neto, IVA y total. La nueva exportación normaliza estos conceptos, agrega RUT/razón social/período, separa vendedor o firmante y no copia sus fórmulas históricas. El archivo fuente queda ignorado por Git porque contiene datos personales.

Pendiente para declarar conformidad definitiva:

1. Confirmar si el archivo aparecido en `docs/` reemplaza oficialmente a `local/reference/libro-caja-elementos.xlsx`.
2. Identificar y aprobar explícitamente un mes patrón corregido por la contadora.
3. Confirmar semántica y obligatoriedad del vendedor/firmante.
4. Mapear columnas normalizadas, orden, formatos y reglas de excepciones contra ese patrón.
5. Crear una prueba dorada anonimizada y versionable; la planilla personal original permanece fuera de Git.

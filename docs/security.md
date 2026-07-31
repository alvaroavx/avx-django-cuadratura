# Seguridad y aislamiento multiempresa

1. La organización se carga por UUID desde la ruta.
2. `authorized_organization` exige membresía activa y rol suficiente, salvo administrador global.
3. Cada consulta subordinada incluye `organization=org`; un UUID de venta de otro tenant responde 404.
4. Ningún formulario operativo contiene `organization`; un campo POST inyectado se ignora.
5. Todas las restricciones críticas de dinero y unicidad viven además en PostgreSQL.
6. Auditoría evita datos de pago, referencia, receptor y secretos; registra identificadores técnicos y metadatos mínimos.
7. El gateway deshabilitado usa un mensaje fijo y no refleja argumentos.

Las pruebas cubren manipulación de URL, POST, UUID subordinado, rol de solo lectura, doble envío concurrente y ausencia de la referencia de pago en auditoría. Antes de producción deben añadirse TLS, cookies seguras, proxy confiable, backup/restauración ensayada, retención de archivos, monitoreo, política de sesión, antivirus de cargas y revisión de dependencias.

Nunca se deben guardar certificado, contraseña, CAF, llave privada o llave maestra en Git, logs o texto plano. La futura llave maestra vivirá en un secret manager/HSM fuera de PostgreSQL.


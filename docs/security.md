# Seguridad y aislamiento multiempresa

1. La organización se carga por UUID desde la ruta.
2. `authorized_organization` exige membresía activa y rol suficiente, salvo administrador global.
3. Cada consulta subordinada incluye `organization=org`; un UUID de venta de otro tenant responde 404.
4. Ningún formulario operativo contiene `organization`; un campo POST inyectado se ignora.
5. Todas las restricciones críticas de dinero y unicidad viven además en PostgreSQL.
6. Auditoría evita referencias de transferencia, receptor y secretos; registra identificadores técnicos y metadatos mínimos. Excepciones conocidas: `payment.historical_matched` guarda fecha y monto del pago, folio y hash de la fuente; `month.reopened` guarda el motivo escrito por la persona.
7. El gateway deshabilitado usa un mensaje fijo y no refleja argumentos.

Las pruebas cubren manipulación de URL, POST, UUID subordinado, rol de solo lectura, doble envío concurrente y ausencia de la referencia de pago en auditoría.

El admin de Django (`/admin/`) registra todos los modelos y no aplica el aislamiento por organización: cualquier usuario `is_staff` con permisos de modelo ve y edita datos de todos los contribuyentes. Solo los triggers de PostgreSQL bloquean ahí eliminaciones y cambios a boletas aceptadas. `settings.py` no fija `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS ni proxy confiable; `DEBUG` es falso por defecto y `SECRET_KEY` tiene un valor inseguro de respaldo si falta la variable.

Antes de producción deben completarse los puntos del [checklist de seguridad](seguridad-produccion.md). La configuración ya exige `SECRET_KEY` fuera de DEBUG y usa cookies `Secure`; falta TLS, proxy confiable, backup/restauración ensayada, retención de archivos, monitoreo, política de sesión, antivirus de cargas y revisión de dependencias.

Las importaciones limitan el tamaño y la cantidad de filas: CSV hasta 2 MiB y 500 filas totales del archivo (incluidos metadatos, cabecera y totales); XLSX hasta 10 MiB, 500 operaciones en la hoja del período y 5000 filas técnicas bajo la cabecera; JSON Elemental hasta 2 MiB y 5000 operaciones. Validan extensión (`.csv`, `.xlsx`, `.json`), estructura, organización, período, clasificación y montos; el CSV además exige UTF-8 (con o sin BOM), rechaza bytes nulos y detecta `,` o `;`. Django además limita el cuerpo no-archivo a 3 MiB y guarda en memoria cargas de hasta 2 MiB. El archivo original queda bajo `media/private/imports` sin ruta web pública. Los lotes se identifican por SHA-256 dentro de cada organización y período, y no se registra contenido personal en logs. PostgreSQL impide eliminar lotes confirmados y sus filas; las actualizaciones no están bloqueadas por trigger. Las filas guardan en `ImportRow.original_data`/`normalized_data` el contenido del archivo, incluidos detalle, montos y, en Elemental, nombre visible del beneficiario y referencias de pago. Los textos con prefijos `=`, `+`, `-` o `@` se conservan como dato original, pero se neutralizan antes de exportarlos a XLSX.

Nunca se deben guardar certificado, contraseña, CAF, llave privada o llave maestra en Git, logs o texto plano. La futura llave maestra vivirá en un secret manager/HSM fuera de PostgreSQL.

## API v1

Diseño completo en [ADR 0006](adr/0006-seguridad-api.md); lo que falta para QA y
producción está en el [checklist](seguridad-produccion.md).

- **Segundo factor:** cada request se firma con Ed25519. Cuadratura solo guarda la
  llave pública, y se rechazan marcas de tiempo fuera de ±5 min y nonces repetidos.
  La firma queda como evidencia de origen en el lote.
- **Intentos fallidos:** todos quedan en `ApiAccessFailure` y en el log
  `cuadratura.api.security`, con IP, motivo y prefijo del token, nunca el secreto.
  Tras 10 fallos en 15 min la IP recibe 429.
- **Límites y vencimiento:** 60 requests por minuto por cliente; tokens que vencen
  (365 días) y rotación con 24 h de solapamiento.
- **Token:** cada cliente se autentica con un Bearer `cdr_<prefijo>_<secreto>` de 256 bits de entropía. Solo se guarda su SHA-256, se compara en tiempo constante y se muestra una vez al emitirlo o rotarlo. El admin no permite crear clientes ni ver tokens.
- **Usuario técnico:** cada cliente tiene uno, inactivo y sin contraseña utilizable, así que no puede entrar a la web.
- **Alcance:** un cliente solo opera sobre las organizaciones vinculadas y activas, y solo ve los lotes de su propio `origin_system`. El RUT del documento debe coincidir con la organización; si no, el lote queda bloqueado.
- **Sin confirmación por API:** la API nunca confirma lotes; la confirmación sigue exigiendo una persona con `IMPORT_ROLES`.
- **HTTPS:** fuera de DEBUG la API exige HTTPS (`API_REQUIRE_HTTPS`). Detrás de un
  proxy, active `DJANGO_TRUST_X_FORWARDED_PROTO` solo si el proxy reescribe ese
  encabezado. TLS, lista de IP permitidas y límite de volumen en el proxy: por
  configurar. No verificado.

## Integración Elemental

El nombre de origen no concede acceso. La carga y confirmación siguen `IMPORT_ROLES` y el aislamiento por organización; además el RUT declarado debe coincidir con el contribuyente activo. No se registran payloads completos en auditoría ni logs, y el contrato no transporta credenciales ni comprobantes. El archivo original permanece en almacenamiento privado y su contenido normalizado queda en las filas del lote (ver arriba). `source_organization` y `batch_id` no se validan contra ningún registro: solo se guardan como metadatos.

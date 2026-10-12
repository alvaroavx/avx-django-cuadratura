# ADR 0006: seguridad de la API v1

Estado: aceptado (2026-10-12). Decisor: Álvaro. Revisado por la mesa BPO: arquitecto y
jefe de proyecto.

## Contexto

Cuadratura quiere custodiar documentos tributarios y, más adelante, integrarse
directamente con el SII. La API v1 ([ADR 0005](0005-api-v1.md)) es su primera puerta
de entrada para otros sistemas y tiene que nacer con defensa en profundidad, no con
un solo secreto compartido.

## Decisión

**1. Dos factores por request.**
- **Token Bearer:** de 256 bits; solo se guarda su SHA-256 y se compara en tiempo constante.
- **Firma Ed25519:** firma `MÉTODO\nRUTA_CON_QUERY\nTIMESTAMP\nNONCE\nSHA256(cuerpo)`,
  con encabezados `X-Cuadratura-Timestamp`, `X-Cuadratura-Nonce` y
  `X-Cuadratura-Signature`.
  - Cuadratura solo conoce la llave pública; la privada nunca sale del cliente.
  - Se rechaza una marca de tiempo fuera de ±5 min o un nonce ya usado
    (`ApiRequestNonce`).
  - `API_REQUIRE_SIGNATURES` vale `true` por defecto fuera de DEBUG. Un cliente sin
    llave pública no puede llamar.

**2. Evidencia de origen.** La firma, la llave pública, el nonce y el hash del cuerpo
quedan en `ImportBatch.source_metadata["signature"]`. Sirven para demostrar después qué
sistema envió qué contenido.

**3. Ciclo de vida del token.**
- **Vencimiento:** 365 días por defecto (`API_TOKEN_DEFAULT_DAYS`).
- **Rotación con solapamiento:** el token anterior sigue válido 24 h
  (`API_TOKEN_ROTATION_GRACE_HOURS`). Con `--grace-hours 0` se corta de inmediato si
  fue comprometido.
- **Auditoría:** alta, rotación, cambio de llave y vínculos con organizaciones solo se
  hacen por comando, y cada uno queda en `AuditEvent`. El admin solo permite desactivar.

**4. Registro de intentos fallidos.**
- Todo rechazo queda en `ApiAccessFailure` y en el logger `cuadratura.api.security`:
  sin token, token inválido o vencido, firma inválida, request vencido o repetido,
  organización no habilitada, límite de frecuencia o falta de HTTPS.
- Se guarda IP, motivo, ruta, user-agent y el **prefijo** del token, nunca el secreto
  ni el cuerpo.
- `purge_api_security_records` aplica la retención (180 días por defecto).

**5. Límites de frecuencia en código.**
- **Por cliente:** 60 requests por minuto (`API_RATE_LIMIT_PER_MINUTE`), con un
  contador en PostgreSQL compartido entre procesos (`ApiRateCounter`).
- **Por IP:** se bloquea 15 min tras 10 fallos de autenticación
  (`API_AUTH_FAILURE_LIMIT` y `API_AUTH_FAILURE_WINDOW_MINUTES`). Una IP bloqueada ya
  no escribe filas nuevas.
- **Ambos** responden 429 con `Retry-After`.
- **El proxy sigue siendo la primera barrera** contra volumen. Este límite protege la
  lógica de negocio y deja traza.

**6. Transporte.**
- `API_REQUIRE_HTTPS` vale `true` por defecto fuera de DEBUG.
- `SECURE_PROXY_SSL_HEADER` solo se activa con `DJANGO_TRUST_X_FORWARDED_PROTO`, y
  solo si el proxy reescribe ese encabezado.
- Cookies `Secure` fuera de DEBUG, HSTS configurable y `SECRET_KEY` obligatoria fuera
  de DEBUG: el servidor no arranca sin ella.

**7. Integridad del período.** Un origen tiene a lo sumo un lote activo (en revisión
o confirmado) por período. Otro `batch_id` para el mismo período responde 409
`period_already_submitted` hasta que exista un flujo de corrección.

**8. Validación adicional.** Tope de `excluded_records` y `reasons` debe ser lista.

## Disenso registrado (mesa BPO)

El arquitecto prefería **mTLS o una lista de IP permitidas** en el proxy como segundo
factor. Su argumento: si se compromete el servidor de Elemental, el atacante obtiene
el token y la llave privada a la vez, y la firma no protege nada.

Se mantiene Ed25519 por tres razones:
- el dueño lo pidió explícitamente;
- protege contra la filtración aislada del token (logs, configuración, tickets);
- deja evidencia de no repudio útil para el producto tributario.

mTLS y la lista de IP permitidas quedan como **requisito de producción** en el
[checklist](../seguridad-produccion.md). No se excluyen entre sí.

## Consecuencias

- **Reloj:** el cliente debe tener el reloj sincronizado (NTP) y firmar la ruta tal
  como la recibe Django. Un proxy que reescriba prefijos rompe la firma.
- **Detrás de un proxy:** hay que configurar `API_CLIENT_IP_HEADER`. Si no, todas las
  llamadas comparten la IP del proxy, y un atacante podría bloquear al cliente legítimo
  (se puede desactivar con `API_AUTH_FAILURE_LIMIT=0`).
- **Dependencia nueva:** `cryptography`, que también se necesitará para la firma XML
  del SII.

## Verificación (2026-10-12)

- `integrations/tests.py` (`ApiV1SecurityTests`) cubre:
  - la firma como segundo factor, el replay y la evidencia guardada;
  - un cliente sin llave;
  - el registro de fallos sin secretos y el bloqueo por IP;
  - el límite por cliente;
  - el vencimiento y la rotación con solapamiento;
  - HTTPS obligatorio;
  - un lote activo por período;
  - una organización no habilitada.
- Suite: 77/77.
- Validado de punta a punta por HTTP contra la base local con «Taller Ficticio SpA»:
  - un request sin firma se rechaza y queda registrado;
  - un reenvío firmado devuelve el mismo lote;
  - un segundo lote del mismo período responde 409.
- No verificado en QA ni en producción.

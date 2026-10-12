# Seguridad para QA y producción — checklist de Cuadratura

Última revisión: 2026-10-12, con la revisión de la mesa BPO (arquitecto y jefe de
proyecto).

Este documento dice qué **debe estar hecho y comprobado** antes de que Cuadratura pase
a un servidor de QA o de producción. Cada punto se marca con evidencia (comando,
captura, acta), no con una declaración. Las etiquetas significan lo siguiente:
- **Implementado:** existe en el código.
- **Por configurar:** depende del servidor o de variables de entorno.
- **Por decidir:** requiere una decisión.
- **No verificado:** depende de normativa o de terceros que este repositorio no acredita.

## 0. Lo que ya trae el código

| Control | Dónde | Estado |
|---|---|---|
| Token Bearer de 256 bits, solo SHA-256 en BD, con vencimiento y rotación con solapamiento | `integrations/services.py` | Implementado |
| Firma Ed25519 por request, anti-replay y evidencia de origen en el lote | `integrations/security.py` | Implementado |
| Registro de intentos fallidos (sin secretos) y bloqueo por IP | `ApiAccessFailure` | Implementado |
| Límite de frecuencia por cliente, compartido entre procesos | `ApiRateCounter` | Implementado |
| HTTPS obligatorio en la API fuera de DEBUG | `API_REQUIRE_HTTPS` | Implementado |
| `SECRET_KEY` obligatoria, cookies `Secure`, HSTS y `LOGGING` | `config/settings.py` | Implementado; HSTS por configurar |
| La API solo crea lotes en revisión; confirma una persona | `imports/services.py` | Implementado |
| Alta, rotación, llave y vínculos auditados; admin solo desactiva | comandos de `integrations` | Implementado |

## 1. Antes de QA (bloqueante)

**Servidor y red**
- [ ] **HTTPS:** TLS 1.2 o superior terminado en el proxy (nginx o Caddy), con
      certificado válido. HTTP redirige a HTTPS. *Evidencia:* `curl -I http://…` → 301,
      y una prueba en SSL Labs o `testssl.sh`.
- [ ] **El proxy controla los encabezados de origen:**
  - reescribe `X-Forwarded-Proto` y `X-Real-IP` y descarta los que manda el cliente;
  - en Django: `DJANGO_TRUST_X_FORWARDED_PROTO=true` y `API_CLIENT_IP_HEADER=HTTP_X_REAL_IP`.
  - *Evidencia:* un request con `X-Real-IP` falso queda registrado con la IP real.
- [ ] **Límite de volumen en el proxy** (primera barrera; el límite del código es la
      segunda). Ejemplo nginx: `limit_req_zone $binary_remote_addr zone=api:10m rate=30r/m;`
      con `limit_req zone=api burst=10 nodelay;` en `location /api/`, más
      `client_max_body_size 3m`.
- [ ] **Lista de IP permitidas** en `location /api/v1/organizations/` con las IP de
      salida de Elemental (QA y producción). El descubrimiento `/api/v1/` puede quedar
      abierto.
- [ ] **Postgres sin exposición pública:** solo escucha en red privada; usuario con
      mínimo privilegio y sin `SUPERUSER`. Las pruebas usan un clúster aparte.

**Variables de entorno**
- [ ] **Django:** `DJANGO_DEBUG=false`, `DJANGO_SECRET_KEY` única de 50+ caracteres y
      `DJANGO_ALLOWED_HOSTS` exacto.
- [ ] **API:** `API_REQUIRE_HTTPS=true` y `API_REQUIRE_SIGNATURES=true` (son los valores
      por defecto fuera de DEBUG; dejarlos explícitos).
- [ ] **HSTS:** partir con `DJANGO_SECURE_HSTS_SECONDS=3600` y subir a `31536000` tras
      una semana sin incidentes.
- [ ] **Secretos fuera del repositorio:** en el gestor de secretos del hosting o en
      archivos con permisos 600 del usuario de servicio. Nunca en Git, tickets ni chat.

**Clientes de la API**
- [ ] **Llaves de Elemental:** Elemental genera su par con `generar_llave_cuadratura`
      en su servidor. La pública se registra con `create_api_client … --public-key` o
      `set_api_client_public_key`.
- [ ] **Token:** se emite con `--expires-days 365`, se entrega por un canal seguro y se
      carga solo en el entorno de Elemental.
- [ ] **Prueba de punta a punta en QA:** un request sin firma responde 401 y queda en
      `ApiAccessFailure`; un envío firmado queda `VALIDATED`; un reenvío devuelve el
      mismo lote.

**Aplicación**
- [ ] **Admin restringido:** `/admin/` no aísla organizaciones, así que solo deben
      entrar usuarios de plataforma. Restringirlo por IP o VPN en el proxy, o
      deshabilitarlo en producción. *Por decidir.*
- [ ] **Suite y migraciones:** suite completa en verde, más
      `makemigrations --check` y `manage.py check --deploy` sin advertencias críticas.
- [ ] **Datos de QA:** solo anonimizados o ficticios.

## 2. Antes de producción con datos reales (bloqueante)

- [ ] **Respaldos cifrados con restauración ensayada:** diarios, en otra ubicación,
      con retención definida. *Evidencia:* acta de una restauración completa a un
      servidor limpio.
- [ ] **Alertas sobre:**
  - picos de `ApiAccessFailure` (por ejemplo, más de 20 por hora o cualquier
    `invalid_signature`);
  - tokens que vencen en 30 días o menos;
  - lotes `BLOCKED`;
  - errores 5xx;
  - espacio en disco.
- [ ] **Logs centralizados**, con retención definida y sin datos personales en texto
      libre.
- [ ] **Retención:** `purge_api_security_records` programado (cron diario) y un plazo
      decidido para `ApiAccessFailure` (180 días por defecto; la IP es dato personal).
- [ ] **MFA (TOTP o WebAuthn)** para administradores de plataforma y para los roles que
      importan, confirman y cierran. *No implementado; requisito.*
- [ ] **Separación de funciones:** quien administra servidores y llaves no es quien
      confirma lotes ni cierra períodos. *Por decidir quién.*
- [ ] **Minimización de datos:** decidir si Cuadratura necesita el nombre del alumno
      (`customer_name`), que puede ser de un menor. Si no lo necesita, dejar de enviarlo
      desde Elemental. *Por decidir.*
- [ ] **Ley 19.628, y la Ley 21.719 cuando entre en vigencia:**
  - registro de tratamientos;
  - base de licitud;
  - procedimiento de notificación de brechas;
  - contrato de encargo con cada contribuyente cuyos datos procese Cuadratura.

  *No verificado: confirmar con un abogado la fecha de vigencia y las obligaciones de
  la Ley 21.719.*
- [ ] **Plan de respuesta a incidentes:**
  - rotar un token con `--grace-hours 0`;
  - reemplazar la llave pública;
  - desactivar el cliente;
  - bloquear la IP.

  Probado una vez como simulacro.
- [ ] **Dependencias:** `pip-audit` o equivalente en cada release, y actualización de
      Django y `cryptography` dentro de su rama de soporte.
- [ ] **Prueba de penetración:** al menos interna antes de abrir a terceros; externa
      antes de la fase de producto (ver la hoja de ruta del workspace).

## 3. Antes de integrarse con el SII (diseño, no implementar todavía)

*Requisitos No verificados: contrastarlos con el SII y con un asesor tributario.*

- **Custodia de llaves:** el certificado digital de cada contribuyente y la llave del
  CAF viven en un KMS o HSM, o como mínimo con cifrado de sobre (envelope encryption)
  mediante KMS. Nunca en la base de datos en claro ni en el `.env`. ADR 0003 ya lo
  anticipa.
- **Firma aislada:** la firma XMLDSig corre en un servicio o worker separado de la web,
  sin acceso desde el admin.
- **Folios:** asignación con restricciones transaccionales, sin reutilización, y
  estado `UNCERTAIN` ante un timeout del SII (ADR 0002).
- **Almacenamiento inmutable (WORM)** del XML emitido, el TrackID y los acuses, con
  retención legal. *Plazo a confirmar.*
- **Separación de funciones:** quien emite no administra llaves.
- **Certificación ante el SII:** set de pruebas, simulación, intercambio y muestras
  impresas en el ambiente de certificación antes de producción.

## Mantenimiento de este documento

Actualizar al cambiar un control. Cada casilla marcada debe enlazar su evidencia (acta
o captura sanitizada) en el registro del ambiente correspondiente, nunca en este repo.

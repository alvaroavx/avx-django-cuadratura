# Cuadratura

Backoffice web autónomo y multiempresa para registrar ventas, pagos, boletas manuales, conciliación y cierres mensuales. Es un sistema independiente: no comparte repositorio, base de datos, autenticación ni modelos con Plataforma Elemental.

## Guía humana

### Qué es, para qué sirve y quiénes lo usan

**Cuadratura** es un backoffice financiero multiempresa para ordenar el trabajo mensual de una organización: registrar operaciones, contrastar ventas y pagos, importar historia y cerrar un período con evidencia. Está dirigido a administradores de plataforma y a usuarios miembros de cada contribuyente con permisos definidos. Es independiente de Plataforma Elemental: no es su API, extensión ni repositorio compartido.

### Qué contiene y cómo trabaja

Contiene un monolito Django server-rendered, PostgreSQL, aplicaciones de cuentas, organizaciones, ventas, pagos, documentos, reportes, importaciones, auditoría e integración futura. Cada operación se ejecuta en el contexto de una organización y el servidor vuelve a comprobar autorización. Las importaciones (XLSX/CSV del libro de caja y JSON del contrato `elemental-cuadratura-v1`) se previsualizan antes de confirmarse; los cierres preservan versión, archivo y SHA-256. No hay SPA, API pública, worker ni emisión SII real; la recepción desde Elemental es por archivo cargado manualmente.

### Funcionalidades y tareas que resuelve

- Administrar usuarios, organizaciones, membresías y roles.
- Registrar ventas, pagos y documentos DTE 39/41 configurables.
- Importar información histórica mediante XLSX o CSV con previsualización y confirmación atómica.
- Importar operaciones y pagos confirmados desde Plataforma Elemental mediante un archivo JSON `elemental-cuadratura-v1` (sin API), con idempotencia por identificador externo y detección de conflictos.
- Conciliar operaciones, construir el libro mensual y exportar un XLSX provisional.
- Revisar, copiar y descargar en XLSX las boletas aceptadas del período (**Exportar a Excel**).
- Consultar los últimos 200 eventos de auditoría de la organización (roles de cierre).
- Cerrar y reabrir períodos con trazabilidad y auditoría append-only.
- Mantener un límite explícito para SII: el gateway falla de forma cerrada y no emite documentos reales.

### Trazabilidad humana

- **Solicitante:** no hay una solicitud ni una persona solicitante verificable en la historia o documentación versionada.
- **Desarrollo:** el primer commit disponible fue creado por **Álvaro Vargas Quezada**; el repositorio no contiene una atribución formal de todos los aportes posteriores.
- **Cuándo:** el primer registro Git disponible es del **31 de julio de 2026**. La fecha describe el inicio observable del repositorio, no una certificación de inicio del producto.

### Qué puede mejorar y oportunidades

Las oportunidades centrales son validar el libro mensual con la contraparte contable, sustituir la exportación XLSX provisional por un contrato aprobado y decidir si la integración SII será realmente necesaria. Para operar en producción faltan decisiones/evidencia sobre hosting, TLS, respaldos, retención, monitoreo y recuperación. La evolución debe conservar aislamiento por organización, inmutabilidad financiera y auditoría; vea [arquitectura](docs/architecture.md), [seguridad](docs/security.md), [libro mensual](docs/monthly-book.md) y los ADR.

## Estado del primer corte

Incluye Django server-rendered, usuario propio, organizaciones y membresías con roles fijos, captura manual transaccional, importación histórica XLSX/CSV con previsualización y commit atómico, importación de archivos JSON `elemental-cuadratura-v1`, DTE 39/41 configurables, conciliación básica, cierres versionados con archivo y SHA-256, reapertura auditada, exportación XLSX reimportable, exportación interactiva de boletas aceptadas y un gateway SII que falla de forma cerrada. **No existe emisión SII real ni API para Elemental**: Elemental entrega un archivo que una persona con rol de importación carga en la pantalla Importación.

También está montado el admin de Django en `/admin/`, que registra todos los modelos (incluidos ventas, pagos, boletas, cierres y auditoría) para usuarios `is_staff`. El admin no aplica el aislamiento por organización ni los servicios transaccionales; solo las restricciones y triggers de PostgreSQL siguen vigentes. No existen comandos de management propios: solo los de Django.

La exportación es provisional. La planilla de referencia se contrastó solo en estructura: sus columnas históricas coinciden con correlativo, operación, documento, emisor, clasificación, fecha, detalle y montos. No hay confirmación de cuál hoja constituye el mes patrón corregido por la contadora. Las planillas de trabajo se mantienen fuera de Git: `.gitignore` excluye `local/`, `docs/*.xlsx`, `docs/*.csv`, `data/*.xlsx`, `data/*.csv` y `data/*.png` (en la copia local revisada la referencia está en `data/`, no en `docs/`).

## Requisitos

- Python 3.14 (`pyproject.toml` exige `>=3.14,<3.15`)
- PostgreSQL 18 (`compose.yaml` usa `postgres:18.4`)
- Dependencias de ejecución en `requirements.txt`: Django 5.2.x, psycopg 3, openpyxl y WhiteNoise. `ruff` y `coverage` figuran solo como extra `dev` en `pyproject.toml` y no se instalan con `requirements.txt`.
- opcionalmente Docker Compose para levantar solo PostgreSQL

Variables de entorno leídas por `config/settings.py`: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` y `POSTGRES_DB/USER/PASSWORD/HOST/PORT`. `SII_GATEWAY` se lee en settings, pero ningún código lo consume todavía.

## Instalación local

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
docker compose up -d db
set -a; source .env; set +a
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

Si PostgreSQL ya existe, cree la base/usuario indicados en `.env` y omita Compose. El host inspeccionado no tenía Docker; `compose.yaml` queda como opción reproducible.

La primera organización, incluida Espacio Cultural y Deportivo Elementos SpA, se crea en **Nuevo contribuyente** después de iniciar sesión como `PLATFORM_ADMIN`/superusuario. No hay tenants en migraciones ni seeders.

### Acceso local y cambio de contraseña

La pantalla `/ingresar/` usa el **nombre de usuario**, no el correo electrónico. Si el acceso falla, compruebe primero que PostgreSQL esté iniciado; en una instalación local administrada por systemd:

```bash
systemctl start postgresql@18-main.service
```

Para cambiar la contraseña de una cuenta existente sin escribirla en el historial de la terminal ni compartirla con terceros:

```bash
set -a; source .env; set +a
.venv/bin/python manage.py changepassword NOMBRE_DE_USUARIO
```

El comando solicita la nueva contraseña dos veces sin mostrarla en pantalla. No agregue contraseñas al repositorio, archivos de documentación, logs ni fixtures.

## Pruebas

Las pruebas requieren PostgreSQL real; SQLite no es compatible ni está configurado. `manage.py test` crea una base `test_<POSTGRES_DB>`, por lo que el usuario de `.env` necesita permiso `CREATEDB`; si no lo tiene, use un clúster PostgreSQL 18 desechable y apunte `POSTGRES_HOST/PORT/USER` a él:

```bash
set -a; source .env; set +a
.venv/bin/python manage.py test -v 2
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
git diff --check
```

Estado verificado el 2026-10-12: `check` y `makemigrations --check --dry-run` pasan; la suite tiene 58 pruebas y 57 pasan. Falla `imports.tests.test_elemental_v1.ElementalV1ImportTests.test_competing_previews_confirm_only_once`, que todavía espera un `ValidationError` al confirmar una segunda previsualización idéntica; desde el commit `c1c7426` esa confirmación es idempotente y marca la fila como ya existente sin crear registros.

## Aplicaciones

- `accounts`: `User` UUID y rol global de plataforma.
- `organizations`: contribuyentes, membresías e invitaciones.
- `sales`, `payments`, `documents`: captura, dinero, DTE 39/41 y estados.
- `payments`: además de `Payment`, `payments.services.register_historical_receipt_payment` vincula un pago histórico a una boleta aceptada; no tiene vista, comando ni prueba en el repositorio.
- `reports`: exportación XLSX provisional, exportación interactiva de boletas, cierre, reapertura y vista de auditoría. El panel mensual vive en `sales`.
- `imports`: parsers XLSX/CSV versionados, receptor JSON `elemental-cuadratura-v1` (`imports/elemental_v1.py`), lotes privados, previsualización y confirmación.
- `sii`: contrato, adaptador deshabilitado, fake de pruebas y modelos `SiiProfile`/`SiiSubmissionAttempt` migrados pero sin uso en flujos.
- `audit`: eventos append-only.
- `integrations`: límite reservado para la futura API, sin modelos activos.

Consulte [arquitectura](docs/architecture.md), [seguridad multiempresa](docs/security.md), [criterio del libro](docs/monthly-book.md), [dirección visual](docs/ui-direction.md), [contrato Elemental v1](docs/contracts/) y los ADR en `docs/adr/`.

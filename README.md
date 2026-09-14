# Cuadratura

Backoffice web autónomo y multiempresa para registrar ventas, pagos, boletas manuales, conciliación y cierres mensuales. Es un sistema independiente: no comparte repositorio, base de datos, autenticación ni modelos con Plataforma Elemental.

## Guía humana

### Qué es, para qué sirve y quiénes lo usan

**Cuadratura** es un backoffice financiero multiempresa para ordenar el trabajo mensual de una organización: registrar operaciones, contrastar ventas y pagos, importar historia y cerrar un período con evidencia. Está dirigido a administradores de plataforma y a usuarios miembros de cada contribuyente con permisos definidos. Es independiente de Plataforma Elemental: no es su API, extensión ni repositorio compartido.

### Qué contiene y cómo trabaja

Contiene un monolito Django server-rendered, PostgreSQL, aplicaciones de cuentas, organizaciones, ventas, pagos, documentos, reportes, importaciones, auditoría e integración futura. Cada operación se ejecuta en el contexto de una organización y el servidor vuelve a comprobar autorización. Las importaciones CSV se previsualizan antes de confirmarse; los cierres preservan versión, archivo y SHA-256. No hay SPA, API pública, worker ni emisión SII real.

### Funcionalidades y tareas que resuelve

- Administrar usuarios, organizaciones, membresías y roles.
- Registrar ventas, pagos y documentos DTE 39/41 configurables.
- Importar información histórica mediante CSV con dry-run y confirmación atómica.
- Conciliar operaciones, construir el libro mensual y exportar un XLSX provisional.
- Cerrar y reabrir períodos con trazabilidad y auditoría append-only.
- Mantener un límite explícito para SII: el gateway falla de forma cerrada y no emite documentos reales.

### Trazabilidad humana

- **Solicitante:** no hay una solicitud ni una persona solicitante verificable en la historia o documentación versionada.
- **Desarrollo:** el primer commit disponible fue creado por **Álvaro Vargas Quezada**; el repositorio no contiene una atribución formal de todos los aportes posteriores.
- **Cuándo:** el primer registro Git disponible es del **31 de julio de 2026**. La fecha describe el inicio observable del repositorio, no una certificación de inicio del producto.

### Qué puede mejorar y oportunidades

Las oportunidades centrales son validar el libro mensual con la contraparte contable, sustituir la exportación XLSX provisional por un contrato aprobado y decidir si la integración SII será realmente necesaria. Para operar en producción faltan decisiones/evidencia sobre hosting, TLS, respaldos, retención, monitoreo y recuperación. La evolución debe conservar aislamiento por organización, inmutabilidad financiera y auditoría; vea [arquitectura](docs/architecture.md), [seguridad](docs/security.md), [libro mensual](docs/monthly-book.md) y los ADR.

## Estado del primer corte

Incluye Django server-rendered, usuario propio, organizaciones y membresías con roles fijos, captura manual transaccional, importación histórica CSV con dry-run y commit atómico, DTE 39/41 configurables, conciliación básica, cierres versionados con archivo y SHA-256, reapertura auditada, exportación XLSX provisional y un gateway SII que falla de forma cerrada. **No existe emisión SII real ni API para Elemental.**

La exportación es provisional. La referencia apareció durante la ejecución como `docs/Libro Caja Espacio Elementos.xlsx` (no en la ruta solicitada) y se contrastó solo en estructura: sus columnas históricas coinciden con correlativo, operación, documento, emisor, clasificación, fecha, detalle y montos. No hay confirmación de cuál hoja constituye el mes patrón corregido por la contadora. Tanto `local/` como `docs/*.xlsx` están ignorados por Git.

## Requisitos

- Python 3.14
- PostgreSQL 18
- opcionalmente Docker Compose para levantar solo PostgreSQL

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

## Pruebas

Las pruebas requieren PostgreSQL real; SQLite no es compatible ni está configurado:

```bash
set -a; source .env; set +a
.venv/bin/python manage.py test -v 2
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
git diff --check
```

## Aplicaciones

- `accounts`: `User` UUID y rol global de plataforma.
- `organizations`: contribuyentes, membresías e invitaciones.
- `sales`, `payments`, `documents`: captura, dinero, DTE 39/41 y estados.
- `reports`: espacio mensual, XLSX provisional, cierre y reapertura.
- `imports`: parser versionado, lotes privados, previsualización y confirmación histórica.
- `sii`: contrato, adaptador deshabilitado y fake de pruebas.
- `audit`: eventos append-only.
- `integrations`: límite reservado para la futura API, sin modelos activos.

Consulte [arquitectura](docs/architecture.md), [seguridad multiempresa](docs/security.md), [criterio del libro](docs/monthly-book.md), [dirección visual](docs/ui-direction.md) y los ADR en `docs/adr/`.

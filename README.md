# Cuadratura

Backoffice web autónomo y multiempresa para registrar ventas, pagos, boletas manuales, conciliación y cierres mensuales. Es un sistema independiente: no comparte repositorio, base de datos, autenticación ni modelos con Plataforma Elemental.

## Estado del primer corte

Incluye Django server-rendered, usuario propio, organizaciones y membresías con roles fijos, captura manual transaccional, DTE 39/41 configurables, conciliación básica, cierres versionados con archivo y SHA-256, reapertura auditada, exportación XLSX provisional y un gateway SII que falla de forma cerrada. **No existe emisión SII real ni API para Elemental.**

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
- `sii`: contrato, adaptador deshabilitado y fake de pruebas.
- `audit`: eventos append-only.
- `integrations`: límite reservado para la futura API, sin modelos activos.

Consulte [arquitectura](docs/architecture.md), [seguridad multiempresa](docs/security.md), [criterio del libro](docs/monthly-book.md) y los ADR en `docs/adr/`.

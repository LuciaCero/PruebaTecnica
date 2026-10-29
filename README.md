# ERP interno de compras

Aplicación para gestionar proveedores, catálogo de productos y pedidos de compra. Está construida con Django, Django Unfold y PostgreSQL; el flujo principal se resuelve desde el panel de administración.

## Funcionalidades

- Alta y gestión de proveedores y productos, con validación de CIF/NIF, referencias y precios.
- Pedidos con varias líneas, número automático y total calculado mediante el ORM.
- Flujo de estados `borrador → confirmado → recibido`, con cancelación y reglas de edición aplicadas en el servidor.
- Panel con indicadores y pedidos pendientes de recepción.
- Migraciones con datos de ejemplo para probar el panel desde el primer arranque.

## Requisitos

- Docker Desktop instalado y en ejecución.

## Puesta en marcha

Desde la raíz del repositorio, en PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec web python manage.py createsuperuser
```

La aplicación aplica las migraciones y arranca junto con PostgreSQL. Abre <http://localhost:8000/admin/> e inicia sesión con el superusuario creado.

## Comandos útiles

```powershell
# Estado y logs
docker compose ps
docker compose logs -f web

# Pruebas y comprobaciones
docker compose exec web python manage.py test purchasing
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run

# Migraciones y parada (conserva los datos)
docker compose exec web python manage.py migrate
docker compose down
```

## Estructura

- `fistex_erp/purchasing/models.py`: modelos y reglas de negocio.
- `fistex_erp/purchasing/admin.py`: administración, acciones e indicadores.
- `fistex_erp/purchasing/migrations/`: esquema y datos iniciales.
- `fistex_erp/purchasing/tests.py`: pruebas automatizadas.

## Configuración

Los valores de `.env.example` son únicamente para desarrollo local. Se pueden cambiar en `.env` antes de arrancar. Esta configuración usa `DEBUG=True`, credenciales de ejemplo y el servidor de desarrollo de Django; no debe utilizarse tal cual en producción.

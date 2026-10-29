# FistexPruebaTecnica

ERP interno de compras para gestionar proveedores, productos y pedidos. Usa Django, Unfold y PostgreSQL.

## Instalación

Necesitas Docker Desktop en ejecución. Desde la raíz del proyecto, en PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec web python manage.py createsuperuser
```

Docker inicia PostgreSQL, aplica las migraciones y arranca Django. También se cargan algunos datos de ejemplo. Después, entra en <http://localhost:8000/admin/> con el usuario que acabas de crear.

## Comandos útiles

```powershell
# Ver contenedores y logs
docker compose ps
docker compose logs -f web

# Ejecutar pruebas
docker compose exec web python manage.py test purchasing

# Aplicar o crear migraciones
docker compose exec web python manage.py migrate
docker compose exec web python manage.py makemigrations

# Parar (conserva los datos)
docker compose down
```

Los valores de `.env.example` son para uso local. Puedes cambiarlos en `.env` antes de iniciar el proyecto.

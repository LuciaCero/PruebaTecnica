# FistexPruebaTecnica

ERP interno para gestionar proveedores, productos y pedidos de compra con Django, Unfold y PostgreSQL.

## Inicio rápido (PowerShell)

Desde la raíz del repositorio, con Docker Desktop en ejecución:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec web python manage.py createsuperuser
```

Abre <http://localhost:8000/admin/> e inicia sesión con el usuario creado. Las migraciones se aplican al arrancar.

## Comandos útiles

```powershell
# Ver estado y logs
docker compose ps
docker compose logs -f web

# Ejecutar pruebas en PostgreSQL
docker compose exec web python manage.py test purchasing

# Aplicar migraciones o crear migraciones
docker compose exec web python manage.py migrate
docker compose exec web python manage.py makemigrations

# Parar servicios (conserva los datos)
docker compose down

# Parar y borrar también los datos de PostgreSQL
docker compose down -v
```

Configura las variables de entorno en `.env` antes de iniciar si necesitas cambiar los valores de `.env.example`.

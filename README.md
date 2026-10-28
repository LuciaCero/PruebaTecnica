# FistexPruebaTecnica
ERP interno para gestionar proveedores, productos y pedidos de compra.

## Arrancar en Docker Desktop (PowerShell)

Con Docker Desktop en ejecución, abre PowerShell en la raíz del repositorio:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

Abre <http://localhost:8000>. Las migraciones se aplican al iniciar.

Si quieres, puedes cambiar los valores de `.env` antes de iniciar.

Para crear un usuario administrador:

```powershell
docker compose exec web python manage.py createsuperuser
```

Para detener los servicios:

```powershell
docker compose down
```

Los datos de PostgreSQL se conservan. Para borrarlos también: `docker compose down -v`.

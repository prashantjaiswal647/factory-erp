# AI ERP System

Initial local development stack for an AI-powered ERP system.

## Local Services

- Web: `http://localhost:5173`
- API: `http://localhost:8000`
- PostgreSQL: `localhost:5432`
- pgAdmin: `http://localhost:5050`

## Run The Stack

```powershell
docker compose up -d --build
docker compose ps
```

Rebuild the stack after dependency or environment changes:

```powershell
docker compose up -d --build
```

## Authentication And RBAC

The API seeds one Owner and one Operator user on startup when the users do not already exist. Configure the credentials in your local `.env` file; do not commit that file.

Required auth environment variables:

- `JWT_SECRET_KEY`
- `DEFAULT_OWNER_USERNAME`
- `DEFAULT_OWNER_PASSWORD`
- `DEFAULT_OPERATOR_USERNAME`
- `DEFAULT_OPERATOR_PASSWORD`

Login endpoint:

```powershell
curl.exe -X POST http://localhost:8000/token -H "Content-Type: application/x-www-form-urlencoded" -d "username=<owner_username>&password=<owner_password>"
```

Owner-only API routes:

- `GET /report/profit-loss`
- `GET /api/admin/live-activity`
- `POST /api/admin/orders/{order_id}/revoke-discount`

## API Smoke Test

```powershell
curl http://localhost:8000/health
curl http://localhost:8000/inventory
curl.exe -X POST http://localhost:8000/inventory -H "Content-Type: application/json" -d "{\"raw_material_name\":\"Steel\",\"quantity\":100}"
```

## pgAdmin Connection

When adding a server in pgAdmin:

- Host name/address: `postgres`
- Port: `5432`
- Maintenance database: value of `POSTGRES_DB`
- Username: value of `POSTGRES_USER`
- Password: value of `POSTGRES_PASSWORD`

Default pgAdmin login:

- Email: `admin@example.com`
- Password: value of `PGADMIN_DEFAULT_PASSWORD`

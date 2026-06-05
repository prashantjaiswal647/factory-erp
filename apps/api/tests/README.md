# Backend Test Database Modes

The focused P0 isolation tests support two database modes.

## SQLite: Fast Unit Coverage

SQLite is the default and requires no services. Use it for fast feedback on
tenant ownership, row-data override protection, and helper behavior.

```powershell
cd apps/api
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m pytest tests/test_remaining_p0_isolation.py -v
```

## PostgreSQL: Transaction Verification

PostgreSQL is required to verify production-relevant transaction behavior,
including `with_for_update`, row locking, and PostgreSQL constraint semantics.

Use the isolated `docker-compose.validate.yml` Postgres service. It uses a
dedicated `ai_erp_validate` database on tmpfs; do not point these tests at a
development or production database.

```powershell
docker compose -p ai-erp-p0-tests -f docker-compose.validate.yml up -d postgres
docker compose -p ai-erp-p0-tests -f docker-compose.validate.yml run --rm --build `
  -e P0_ISOLATION_DATABASE_URL=postgresql://erp_validate:erp_validate_password@postgres:5432/ai_erp_validate `
  api python -B -m pytest tests/test_remaining_p0_isolation.py -v
docker compose -p ai-erp-p0-tests -f docker-compose.validate.yml down --remove-orphans
```

The test guard rejects PostgreSQL database names that do not contain `test` or
`validate`.

## Full Backend Suite

```powershell
cd apps/api
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m pytest tests/ -q
```

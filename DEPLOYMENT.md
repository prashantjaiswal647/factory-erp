# Munshi AI Deployment and Recovery Procedures

This guide provides absolute instructions for environment variables, secrets management, deployment workflows, and database recovery drills.

---

## 1. Secrets and Environment Variables

The following key configurations must be defined in the production environment (configured in the production host or custom `.env` file - never commit `.env` files to git).

| Variable Name | Description | Default Fallback Behavior |
| :--- | :--- | :--- |
| `JWT_SECRET_KEY` | Sign JSON Web Tokens | Required. Fails closed with `RuntimeError` if missing. |
| `SUPER_ADMIN_JWT_SECRET` | Sign Super Admin tokens | Required. Fails closed with `RuntimeError` if missing. |
| `N8N_API_KEY` | Authorize n8n inbound webhooks | Required. Returns `503 Service Unavailable` if missing. |
| `POSTGRES_PASSWORD` | DB Admin password | Local compose default fallback (unsafe in production). |
| `SUPER_ADMIN_EMAIL` | Admin login identifier | Configured at startup. |
| `SUPER_ADMIN_PASSWORD_HASH` | Bcrypt hash of Admin password | Verified during login attempt. |
| `GROQ_API_KEY` | Key for LLM queries | Optional. Falls back to mock or fails gracefully. |
| `OPENAI_API_KEY` | Key for audio notes transcription | Optional. |

### Secret Rotation Procedure

#### 1. JWT & Super Admin Secret Keys
Generate a new random 256-bit hexadecimal key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Update `JWT_SECRET_KEY` or `SUPER_ADMIN_JWT_SECRET` in `.env` / production manager, and restart the FastAPI service.

#### 2. Bcrypt Super Admin Password Hashes
Generate a new hash:
```bash
python -c "from passlib.context import CryptContext; pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto'); print(pwd_context.hash('your_new_password'))"
```
Update `SUPER_ADMIN_PASSWORD_HASH` in host variables.

---

## 2. Production Deployment Steps

Deployments target a VPS (e.g., Contabo or Hostinger) and are orchestrated via `./deploy.sh`.

### Verification Gate (CI/CD Checklist)
1. Ensure the working tree is clean (no uncommitted changes).
2. Execute validation script locally:
   ```bash
   ./validate-and-test.sh
   ```
3. Verify that `npm run build` succeeds on the frontend without TypeScript errors.

### Deployment Script Workflow (`deploy.sh`)
The production flow is sequential:
1. **Pre-flight Check:** Re-assert dirty git status.
2. **Database Backup:** Create a timestamped backup of PostgreSQL using:
   ```bash
   docker exec ai-erp-postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > storage/backups/pg_backup_$(date +%Y%m%d_%H%M%S).dump
   ```
3. **Database Migration:** Run Alembic migrations:
   ```bash
   docker compose run --rm api alembic upgrade head
   ```
4. **Rebuild Service Containers:** Re-create containers to pick up changes:
   ```bash
   docker compose up -d --build api web caddy
   ```
5. **Post-Deployment Verification:** Run a cURL request checking status code 200 on health endpoint:
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" https://munshiai.co.in/api/health
   ```

---

## 3. Disaster Recovery (DR) Restore Drill

A restore verification must be run periodically on a disposable test database. Do NOT drop or restore directly into the live production database.

### Restore Command Workflow
1. **Locate Backup:** Find the target `.dump` file inside `storage/backups/`.
2. **Launch Disposable Database:** Setup a temporary container or local DB instance.
3. **Run pg_restore:**
   ```bash
   pg_restore --no-owner -d dr_restore_check storage/backups/dr_contabo_restore_drill_YYYYMMDD_HHMMSS.dump
   ```
4. **Verification Queries:** Verify record integrity across critical tables:
   - Check tables: `factories`, `users`, `workers`, `machines`, `inventory`, `finished_goods_stock`.
   - Ensure the restored database is queryable and shows the latest expected Alembic migration revision.
5. **Cleanup:** Delete/drop the disposable restore database.

---
**Source Files Compressed:** `env-checklist.md`, `docs/disaster_recovery_drill_report.md`

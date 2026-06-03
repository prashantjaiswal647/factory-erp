# Munshi AI - Agent Operating Notes

Compact, high-signal operating context for AI agents and engineers working on Munshi AI. Read this file before any code change.

## 1. What This Is

- Multi-tenant ERP SaaS for manufacturing factories, focused first on paper cups/glass and machinery-based production.
- Frontend: React + Vite (`apps/web/`).
- Backend: FastAPI + SQLAlchemy + Alembic (`apps/api/`).
- Database: PostgreSQL 16.
- Infra: Docker Compose with API, web, Postgres, Redis, Caddy, n8n, and backup service.
- Production: `https://munshiai.co.in`; API: `https://munshiai.co.in/api`.

## 2. Monorepo Layout and Entrypoints

| Path | Purpose |
|---|---|
| `apps/api/main.py` | FastAPI app (`main:app`) |
| `apps/api/models.py` | SQLAlchemy model definitions |
| `apps/api/alembic.ini` | Alembic config; migrations live in `apps/api/alembic/versions/` |
| `apps/api/tests/` | Backend pytest suite |
| `apps/web/package.json` | Vite app; `npm run dev` on port 5173 |
| `apps/web/src/App.tsx` | Frontend route map |
| `apps/web/src/components/Layout.tsx` | Main authenticated layout and sidebar |
| `docker-compose.yml` | Production-like stack |
| `docker-compose.validate.yml` | Isolated validation stack |
| `deploy.sh` | Production deploy gate with backup and Alembic |
| `validate-and-test.sh` | Containerized validation gate |
| `.github/workflows/ci.yml` | GitHub CI. P0 fix applied: frontend validation must use `npm run build`, not a missing `npm run type-check` script. |
| `.github/workflows/deploy-ci.yml` | Runs `validate-and-test.sh`, then SSH deploys |

## 3. Current Production Readiness

Latest production-readiness estimate:

| Target stage | Current readiness |
|---|---:|
| First pilot factory | 75-80% |
| Sellable MVP | 65-70% |
| Production SaaS for 10 factories | 55-60% |
| Scalable SaaS for 100+ factories | 35-40% |

Interpretation:
- Munshi AI has a working SaaS foundation, but it is not yet clean production SaaS.
- P0 tasks must be fixed before pilot deployment.
- Do not add new features before P0 tasks are green unless the new work directly fixes a P0 production incident, tenant-isolation bug, security issue, or data-loss risk.

## 4. Current Launch Blockers

### P0 - Pilot Prerequisites
1. **GitHub CI mismatch**: fixed in code by using `npm run build` instead of missing `npm run type-check`.
2. **Global 500 error leakage**: fixed in code; browser clients must receive generic error text only.
3. **Local secret exposure risk**: env-handling checklist is documented; any exposed-looking local/API/test keys must be rotated by the operator before deployment.

### P1 - Fix Before Sellable MVP
4. **Bulk upload idempotency escape paths**: same-file re-upload must never crash with duplicate/integrity errors.
5. **Excel validation report UI incomplete**: frontend must render structured sheet/section/row/column corrections from backend validation reports.
6. **Frontend/backend RBAC drift**: daily-sequence and other protected routes must have aligned frontend guards and backend permissions.
7. **Sidebar internal route hardcoding**: UI sidebar/nav must never hardcode production URLs for internal routes such as `/operations`.
8. **Duplicate/overlapping models remain**: `Employee`/`Worker`, `FactoryExpense`/`ExpenseLog`, `FinalProductStock`/`FinishedGoodsStock`, and multiple machine setup models.
9. **Audit Trail UI incomplete**: daily sequence/activity logs need a practical owner-facing review/export UI.
10. **Disaster Recovery restore drill**: latest local drill passed on a disposable PostgreSQL container, but production readiness still requires recurring backup freshness checks and repeated restore drills.

### P2 - Fix Before Scale
11. **JWT localStorage risk**: normal app JWTs are still stored in client-side `localStorage`.
12. **Razorpay subscription automation pending**: subscription lifecycle needs robust webhook-driven automation.
13. **Monitoring stack pending**: uptime, logs, API errors, DB health, n8n health, disk, and backup freshness are not centralized.
14. **pgBouncer pending**: add PostgreSQL connection pooling before 10+ factories.
15. **Docker fallback credentials**: compose defaults still include local fallback DB credentials; production env must override them.

## 5. Current Execution Queue

Approved execution order:
1. Update `AGENTS.md` whenever the architecture, security posture, deployment flow, or production-readiness queue changes.
2. Complete and verify P0 fixes:
   - CI command fix: GitHub CI must use an existing frontend command, currently `npm run build`.
   - Generic 500 response: browser/API clients must never receive raw `str(exc)` internals.
   - `.env`/secret checklist: exposed-looking keys must be rotated and secret handling must be documented.
3. Complete P1 pilot fixes:
   - Bulk upload idempotency for every sheet.
   - Excel validation report UI.
   - Frontend/backend RBAC route alignment.
   - Sidebar absolute production URL cleanup for internal routes.
4. Perform and document Disaster Recovery restore drill.
5. Produce duplicate model cleanup plan using compatibility layers before destructive schema changes.
6. Build Audit Trail UI for activity/daily-sequence review.
7. Run Final Pilot Readiness Audit.
8. Pilot Factory Onboarding.
9. After pilot: Factory Health Score, Cost Per Cup Engine, Machine Downtime Module, Razorpay Automation, JWT Cookie Migration.
10. After 10+ factories: pgBouncer, Monitoring Stack, Enterprise Security.

## 6. Definition of Production Ready

Munshi AI is production-ready only when all of the following are true:
- All P0 launch blockers are fixed.
- `./validate-and-test.sh` passes.
- GitHub CI passes.
- Backend pytest passes.
- `npm run build` passes.
- Backup restore drill is completed and documented.
- Bulk upload same-file re-upload does not create duplicate crashes.
- Frontend and backend RBAC are aligned for every protected route.
- Global exception responses do not expose internal exception strings.
- Factory isolation tests cover high-risk read/update/delete/upload/export/invoice/payment routes.
- Production `.env` contains strong secrets and no placeholder/fallback credentials.

## 7. Testing Gate Before Every Commit

Before committing business logic changes:
1. Run the smallest affected backend/frontend test first.
2. Run backend pytest for backend/data/security changes.
3. Run `npm run build` for frontend/API contract changes.
4. Run `./validate-and-test.sh` before deployment or infrastructure changes.
5. Do not mark work complete if tests were skipped without stating why.

Backend:
```powershell
cd apps/api
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m pytest -q
```

Frontend:
```powershell
cd apps/web
npm run build
npx vitest run
```

Full container gate:
```bash
./validate-and-test.sh
```

Important CI note:
- `apps/web/package.json` does not define `type-check`.
- Use `npm run build` because it runs TypeScript compile before Vite build.
- Fix `.github/workflows/ci.yml` before pilot deployment.

## 8. Security Gate Before Production

Before production deploy:
- Rotate any exposed-looking local/API/test keys.
- Verify `.env` is not tracked and production secrets are not placeholders.
- Verify local `.env` values are not copied into chat, screenshots, reports, or support tickets.
- If a local/API/test key has appeared in any external transcript, rotate it before deployment.
- Keep a short env-handling checklist in the deployment notes: owner of secret, date rotated, target service, production value source, and rollback contact.
- Verify global exception responses are sanitized.
- Verify no JWT/API key/password/OTP/phone/email/customer PII is logged.
- Verify normal factory JWTs cannot access Super Admin APIs.
- Verify n8n/internal APIs require `X-N8N-API-KEY`.
- Verify CORS origins are explicit and production-safe.
- Verify backup is created before Alembic migration.

Security no-go rules:
- Do not weaken `factory_id` isolation anywhere.
- Do not add fallback cryptographic secrets.
- Do not return internal exception strings to browser clients.
- Do not log sensitive data.
- Do not bypass Super Admin controls for normal users.

## 9. Bulk Upload Rules

- Bulk upload same-file re-upload must never create a duplicate crash.
- Every bulk sheet should behave as deterministic upsert: insert if new, update if existing, scoped by `current_user.factory_id`.
- Spreadsheet-provided tenant/factory fields must never override authenticated `current_user.factory_id`.
- Duplicate/integrity errors should be converted into useful validation-report issues whenever possible.
- Excel validation UI must show exact sheet, section, row, column, bad value, and correction guidance.
- `row_type=SAMPLE` rows are never imported; only `row_type=ACTUAL` rows are processed.
- Raw Materials vertical sections must remain marker-driven, not fixed-position only.
- Finished Goods blank `packaging_size_name` must keep the fallback format: `{product_size_ml}ML - {variety_design}`.

## 10. UI/RBAC Route Alignment Rules

- Backend and frontend RBAC must always be aligned.
- If backend allows a role to read a route, the frontend route/sidebar should not hide or block it unless deliberately documented.
- If backend forbids a write/delete action, frontend buttons must be hidden or disabled for that role.
- UI sidebar/nav must never hardcode production URLs for internal app routes. Use router-relative paths such as `/operations`.
- `/munshi-control-room` must stay isolated from normal public/sidebar navigation.

## 11. Duplicate Model Migration Strategy

Duplicate/overlapping model families currently require careful consolidation:
- `Employee` and `Worker`
- `FactoryExpense` and `ExpenseLog`
- `FinalProductStock` and `FinishedGoodsStock`
- Multiple machine setup/configuration models

Rules:
- Do not use destructive migrations as the first step.
- Use compatibility views, service adapters, or read/write facades first.
- Add migration tests before changing schema.
- Preserve API contracts until frontend consumers are migrated.
- Preserve historical production data and auditability.

## 12. Disaster Recovery Rule

- Disaster Recovery restore drill is mandatory before production SaaS launch.
- A backup existing on disk is not enough; restore must be tested on a disposable database.
- Document backup file used, restore command, elapsed time, verification queries, and rollback decision tree.
- Production deploy must not proceed if pre-migration backup fails.
- Latest local drill status: passed using `pg_dump -Fc`, disposable PostgreSQL restore, key table count comparison, and API `/api/health` boot check against restored DB.
- Keep repeating this drill before major production milestones and after backup/deploy script changes.

## 13. Database and Migration Rules

- Never run `Base.metadata.create_all()` or runtime schema mutation in production startup/request handlers.
- Schema changes are Alembic only.
- Baseline revision: `20260603_0001_runtime_schema_baseline.py`.
- `deploy.sh` must create a timestamped `pg_dump -Fc` backup under `storage/backups/` before Alembic.
- Rollback strategy is restore from `.dump` backup, not destructive Alembic downgrade.

## 14. Deployment Rules

- `validate-and-test.sh` must pass before `deploy.sh`.
- `deploy.sh` aborts if the working tree has uncommitted changes.
- Production flow: backup -> Alembic -> recreate containers -> verify `/api/health`.
- Do not push directly to VPS without using `deploy.sh`; it handles env vars (`VITE_API_URL`, `CORS_ORIGINS`) and backup.

## 15. Multi-Tenant Rules

- Every business record and query must be scoped to `factory_id`.
- Normal users must never access another factory's data.
- Detail/update/delete routes must verify object ownership by `factory_id`.
- Bulk upload must attach `current_user.factory_id` server-side.
- Invoice/PDF/payment/outstanding/dashboard routes must filter by `factory_id`.
- Super Admin bypass is allowed only through explicit `/api/super-admin/*` routes and must be audit-logged.

## 16. Future Scale Roadmap

Follow this sequence unless a P0 incident overrides it.

### Phase 0 - Agent Context Foundation
1. AGENTS.md Update: keep this file accurate after every major architecture, security, migration, deployment, or workflow change.

### Phase 1 - Pre-Pilot Stabilization
2. P0 Launch Blockers: CI command fix, generic 500 response, and `.env`/secret checklist.
3. P1 Pilot Fixes: bulk upload idempotency, Excel validation report UI, RBAC route alignment, and sidebar absolute URL cleanup.
4. Disaster Recovery Drill.
5. Duplicate Model Cleanup Plan.
6. Audit Trail UI.
7. Final Pilot Readiness Audit.
8. Pilot Factory Onboarding.

### Phase 2 - After Pilot
11. Factory Health Score.
12. Cost Per Cup Engine.
13. Machine Downtime Module.
14. Razorpay Automation.
15. JWT Cookie Migration.

### Phase 3 - After 10+ Factories
16. pgBouncer.
17. Monitoring Stack.
18. Enterprise Security.

## 17. Environment

- Required local env vars: `JWT_SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `DEFAULT_OWNER_USERNAME`, `DEFAULT_OWNER_PASSWORD`, `DEFAULT_OPERATOR_USERNAME`, `DEFAULT_OPERATOR_PASSWORD`.
- The stack expects `.env` at repo root for `docker compose`.
- `.env` must never be committed.
- If a local secret appears in chat logs, screenshots, support tickets, or audit output, rotate it.

---
Referenced by `opencode.jsonc` instructions array.

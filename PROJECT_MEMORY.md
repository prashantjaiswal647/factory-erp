# Munshi AI Project Memory

Compact operating context for AI agents. Detailed rules live in `AGENTS.md`. Current state lives in `CURRENT_STATUS.md`.

## Project Purpose

Munshi AI is a multi-tenant ERP SaaS for manufacturing factories, with an embedded AI Factory Supervisor. Initial focus: paper cup/glass manufacturing and machinery-based production in the Indian SME segment. Strict tenant isolation through `factory_id`.

## Local Path

```
C:\Users\Prashant\OneDrive\Desktop\Coding Projects\ai-erp-system
```

## Production URLs

- Application: `https://munshiai.co.in`
- API: `https://munshiai.co.in/api`

## Vision

`ERP + AI Factory Supervisor`. The ERP is the system of record. The AI Supervisor is the daily reason the owner opens the app. The two halves are inseparable: data quality (ERP) enables trustworthy advice (AI).

## Tech Stack

- Frontend: React + Vite
- Backend: FastAPI
- ORM: SQLAlchemy
- Migrations: Alembic (sole schema authority)
- Database: PostgreSQL 16
- Cache: Redis
- Reverse proxy: Caddy
- Automation: n8n
- Infra: Docker Compose
- Testing: pytest, Vitest, containerized validation
- CI/CD: GitHub Actions + SSH-based production deployment

## Major Modules

### Backend (`apps/api/`)

- Auth + RBAC (`auth.py`)
- Factory and user management
- Staff and Worker (Worker canonical; Employee compat)
- Attendance, Advance Payment, Payroll, Hisab Settlement
- Production / Daily Production / Telemetry
- Machine, MachineOnboarding, MachineTemplate
- Inventory (Raw Material, Packaging)
- Finished Goods (FinishedGoodsStock canonical; FinalProductStock mirror via listener)
- Factory Expense (FactoryExpense canonical; ExpenseLog mirror via listener)
- Sales Orders, Invoices, Outstanding Bills, Payments
- Customers and Customer Activity
- Bulk Excel Onboarding (8 sub-tabs, single master workbook)
- Daily Sequence / Activity Log
- Operations and Dashboard
- Super Admin + Audit Log
- AI Agent (tool-calling LLM; seed for AI Supervisor)
- n8n Sync, Telegram Integration
- Invoice PDF Generation
- Subscription and Billing (Razorpay; webhook automation pending)

### Frontend (`apps/web/`)

- 27 pages, 13 components, 3 contexts (Auth, Upgrade, DataRefresh)
- Auth-gated routes, subscription-gated features
- Onboarding wizard, bulk upload section, dashboards
- Storefront, public pages, pricing, policy

## Current Readiness (2026-06-05)

  First pilot factory           75-80%
  Sellable MVP                  65-70%
  SaaS for 10 factories         55-60%
  SaaS for 100+ factories       35-40%

The foundation works. The pilot blockers (P0/P1 in `CURRENT_STATUS.md`) are the only barrier to the first paying customer. Post-pilot, the product priority is AI Supervisor V1.

## Current Cleanup Status

### Resolved / In Progress

- Worker is canonical; Employee remains as compat. Migration `20260605_0002` is in.
- Frontend CI uses `npm run build` (P0 fix landed).
- Global 500 responses do not expose internal exception strings (P0 fix landed).
- Secret-handling checklist is documented.

### Still Open

- FactoryExpense vs ExpenseLog and FinishedGoodsStock vs FinalProductStock: dual-write via listeners; not yet collapsed.
- Multiple machine setup/configuration models: not yet collapsed.
- 165 lines of inline DDL in `apps/api/schema_compat.py`: must move to Alembic (CURRENT_STATUS §3 P1.1).
- Bulk upload has no DB unique constraints (CURRENT_STATUS §3 P1.2 fixes workers + machines; P2.1 covers the rest).
- Daily Sequence / Audit Trail UI: P1, post-pilot.
- RBAC route alignment: P1, pre-pilot.
- Sidebar absolute URL cleanup: P1, pre-pilot.
- JWT localStorage: P2, post-pilot.

## Critical Safety Rules

- Never weaken `factory_id` isolation. Never trust client-supplied factory_id.
- Never drop legacy tables as the first consolidation step.
- Never add fallback cryptographic secrets.
- Never expose internal exception details or sensitive data to clients.
- Never allow spreadsheet tenant fields to override the authenticated factory.
- Schema changes are Alembic only. No `Base.metadata.create_all()` in production.
- Always create a `pg_dump -Fc` backup before production migrations.
- Roll back from `.dump`, not from destructive Alembic downgrades.
- Run `validate-and-test.sh` before deployment.
- The AI Supervisor's advice must be grounded in tenant-scoped data; never cross-tenant.

## Testing Gates

Backend:
```
cd apps/api
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m pytest -q
```

Frontend:
```
cd apps/web
npm run build
npx vitest run
```

Full validation:
```
./validate-and-test.sh
```

CI uses `npm run build` (not `type-check`); this is fixed in `.github/workflows/ci.yml`.

## Future Scale Work

### After pilot
- Razorpay subscription automation
- AI Factory Supervisor V1 (A1-A10)
- Cost Per Cup Engine
- Machine Downtime Module
- Factory Health Score
- Pricing tier expansion
- JWT cookie migration

### After 10+ factories
- pgBouncer
- Centralized monitoring
- Enterprise security
- Multi-factory AI benchmarking
- Supply chain integration

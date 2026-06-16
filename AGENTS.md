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
| `apps/api/services/cost_engine.py` | Factory-scoped deterministic daily cost totals and weighted CPC |
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
- A2.1 stores daily cost totals in paise and derives CPC dynamically; `/api/cost/*` must remain factory scoped.
- A2.2 stores deterministic variance snapshots, compares against prior completed-day weighted windows, and sends at most one cost-spike alert per factory/day.
- Successful A2.2 cost-spike sends create one structured `COST_SPIKE_DETECTED` ActivityLog and are visible to Super Admin through briefing observability.
- A2.3 computes one deterministic daily factory health snapshot at 23:58 IST from production, attendance, collections, inventory, and cost-control scores.
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

Cashfree payment rules:
- Owner plan purchases use Cashfree PG orders and hosted checkout.
- Browser return parameters never activate a subscription.
- Only a valid signed `PAYMENT_SUCCESS_WEBHOOK` with matching order, amount, currency, and unique Cashfree payment ID may activate a factory.
- Cashfree webhook endpoint: `/api/v1/payments/webhook/cashfree`.
- Required production variables: `CASHFREE_APP_ID`, `CASHFREE_SECRET_KEY`, `CASHFREE_ENV`, `CASHFREE_WEBHOOK_SECRET`, and `PUBLIC_API_ORIGIN`.

Security no-go rules:
- Do not weaken `factory_id` isolation anywhere.
- Do not add fallback cryptographic secrets.
- Do not return internal exception strings to browser clients.
- Do not log sensitive data.
- Do not bypass Super Admin controls for normal users.

Security hardening status:
- Authentication diagnostics use structured logging; production auth code must not use `AUTH DEBUG` or `print(...)`.
- Frontend auth accepts `access_token`, `token`, or `jwt` login response keys, persists the normalized token, and attaches it as `Authorization: Bearer <token>` to protected API requests.
- Subscription refresh must skip when no auth token exists; protected-route 401 responses clear auth and redirect to `/login` once.
- `/api/super-admin/login` is limited to 5 requests per client IP per 60 seconds.
- n8n, Telegram, and AI webhook ingress is limited to 60 requests per client IP per 60 seconds.
- Rate-limit overflow returns HTTP 429 before webhook business processing.

## 9. Bulk Upload Rules

- Bulk upload same-file re-upload must never create a duplicate crash.
- Phase 1 canonical onboarding identity uses nullable factory-scoped restore keys for customers, workers, machines, Blank/Bottom materials, and finished products.
- When a restore key is supplied it is authoritative. Fallback matching is normalized phone/GST/name context for customers, phone/name for workers, machine number/name for machines, and full size/variety/packaging identity for materials/SKUs.
- Blank `material_name` is descriptive only; production identity uses `variety`, `weight_per_bora_kg`, and `linked_bottom_size_mm`. Never infer Bottom MM from cup ML.
- Production SKU options must exclude incomplete Blank/Bottom/Box mappings.
- Every bulk sheet should behave as deterministic upsert: insert if new, update if existing, scoped by `current_user.factory_id`.
- Master onboarding upload is a full active-baseline sync: duplicate workbook rows use last-row-wins; referenced customers/workers/machines are archived then matching rows reactivated; standalone opening-stock rows are cleared and rebuilt only from explicit workbook rows.
- Production logging and onboarding metric helpers must never auto-create visible Blank/Bottom stock rows; missing mappings fail validation and visible inventory comes only from explicit stock entry or master workbook rows.
- Spreadsheet-provided tenant/factory fields must never override authenticated `current_user.factory_id`.
- Duplicate/integrity errors should be converted into useful validation-report issues whenever possible.
- Excel validation UI must show exact sheet, section, row, column, bad value, and correction guidance.
- `row_type=SAMPLE` rows are never imported; only `row_type=ACTUAL` rows are processed.
- Raw Materials vertical sections must remain marker-driven, not fixed-position only.
- Finished Goods blank `packaging_size_name` must keep the fallback format: `{product_size_ml}ML - {variety_design}`.
- Finished Goods carton mapping uses explicit `carton_type` matched to Box Stock `carton_type`; `packaging_size_name` is only the SKU variation label. Box Stock `size_for_finished_product` is the comma-separated allowlist for product sizes, and production deducts cartons only from that matched Box Stock row.
- Master onboarding Finished Goods rows are the visible inventory source of truth. Each explicit row receives a stable restore key when omitted; replacement upload deletes stale `FinalProductStock` and compatibility `FinishedGoodsStock` rows before rebuilding exactly from the sheet.
- Packaging metrics, machine mappings, production, and sales must never auto-create a visible finished-good SKU. Production and sales reject an unknown SKU; they may only update a SKU already created by onboarding or an explicit inventory action.

## 10. UI/RBAC Route Alignment Rules

- Backend and frontend RBAC must always be aligned.
- If backend allows a role to read a route, the frontend route/sidebar should not hide or block it unless deliberately documented.
- If backend forbids a write/delete action, frontend buttons must be hidden or disabled for that role.
- UI sidebar/nav must never hardcode production URLs for internal app routes. Use router-relative paths such as `/operations`.
- `/munshi-control-room` must stay isolated from normal public/sidebar navigation.
- Sales, invoices, and outstanding read routes allow Owner, Sub-Owner, and Supervisor; Collection War Room remains Owner-only in both frontend and backend.

## 11. Duplicate Model Migration Strategy

Duplicate/overlapping model families currently require careful consolidation:
- `Employee` and `Worker`
- `FactoryExpense` and `ExpenseLog`
- `FinalProductStock` and `FinishedGoodsStock`
- Multiple machine setup/configuration models

Current incremental status:
- `Worker` is canonical for new staff, attendance, advance-payment, production, and onboarding writes.
- `Employee` remains as a compatibility table. Attendance and advance-payment records retain `employee_id` while preferring/backfilling `worker_id` only for exact same-factory matches.
- Compatibility listeners remain active; do not remove `Employee` or its legacy foreign keys until production backfill and compatibility usage are verified over time.

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

## 12A. Invoice PDF Rule

- Sales invoices are generated server-side from authenticated, factory-scoped sales data.
- Canonical endpoints are `POST /api/invoices/from-sale/{sale_id}`, `GET /api/invoices`, and `GET /api/invoices/{invoice_id}/pdf`.
- Invoice generation is idempotent for a sale and uses the existing factory invoice counters.
- PDF generation uses local application data and ReportLab; Google Sheets is not required.
- GST mode, tax rate, payment method, and notes may be supplied when generating from an existing sale.

## 13. Database and Migration Rules

- Never run `Base.metadata.create_all()` or runtime schema mutation in production startup/request handlers.
- Schema changes are Alembic only.
- Migrations that add columns, tables, indexes, foreign keys, or constraints must inspect the live schema and skip objects that already exist so partially applied production deploys can resume safely.
- Baseline revision: `20260603_0001_runtime_schema_baseline.py`.
- `deploy.sh` must create a timestamped `pg_dump -Fc` backup under `storage/backups/` before Alembic.
- Rollback strategy is restore from `.dump` backup, not destructive Alembic downgrade.

## 13A. Master Backup and Restore

- Owner-only master backup APIs live under `/api/backup/master`.
- Export uses one XLSX sheet per factory data family and includes factory-scoped stable restore keys.
- Restore is validate-first and confirmation-only; staged uploads must never import during validation.
- Confirmed restore creates a pre-restore backup, runs transactionally, and must reject cross-factory metadata.
- The API runtime image must include `postgresql-client`; confirmed PostgreSQL restores call `pg_dump` before any mutation and abort clearly if that safety backup fails.
- Validation writes factory-scoped staged session metadata containing the original filename, validation status, fatal count, and sheet counts; confirmation must consume that exact validated session.
- Restore is snapshot-based: records absent from authoritative backup sheets are removed in dependency-safe order, and stock quantities are replaced with workbook values rather than added.
- A fatal restore error rolls back every database mutation and keeps the staged upload available for retry.
- Restore logs must include the session ID, filename, sheet/table, parsed rows, created/updated/deleted counts, and server-side traceback while client errors remain sanitized.
- Invoice history restore must not call sales creation paths or deduct finished-goods stock again.
- `master-backup-email-scheduler` sends separate owner emails for weekly backups on Sunday at 20:30 IST and monthly backups on day 1 at 08:30 IST.
- Scheduled delivery is deduplicated independently by factory, frequency, and period under the persistent `BACKUP_ROOT` volume; weekly and monthly files must never share one email.

## 13B. Go-Live Reset

- Owner-only go-live cleanup APIs live under `/api/admin/go-live-reset`; Supervisor and Sub Owner must never receive access.
- Reset always follows preview -> exact confirmation text -> pre-reset database backup -> one database transaction -> ActivityLog audit.
- Master onboarding records remain: factory, customers, workers, machines, material/packaging stock rows, and finished-goods SKU rows.
- Sales reset removes test invoices, deliveries, payments, allocations, invoice-linked ledger adjustments, recovery followups, and outstanding rows; only explicitly confirmed opening outstanding is recreated.
- Production reset is optional and removes production batches, compatibility daily production rows, and wastage rows.
- Invoice starts must update both `Factory.next_*_invoice_number` and the matching `FactorySettings.*_start_seq`.
- Inventory mode is explicit: keep current quantities, or reverse selected transaction effects using persisted sales/production consumption snapshots before deleting those transactions.

## 14. Deployment Rules

- `validate-and-test.sh` must pass before `deploy.sh`.
- `deploy.sh` aborts if the working tree has uncommitted changes.
- Production flow: backup -> Alembic -> recreate containers -> verify `/api/health`.
- Do not push directly to VPS without using `deploy.sh`; it handles env vars (`VITE_API_URL`, `CORS_ORIGINS`) and backup.
- Production Caddy container name is `factory-erp-caddy-1` (Docker Compose project-name prefix on the Hostinger VPS). Reload with `docker compose restart factory-erp-caddy-1` or recreate with `docker compose up -d --force-recreate caddy`. When adding a new `/api/*` route, the deploy must rebuild `api`, `web`, and `caddy` in that order so the new bundle is live before any request can hit the new Caddy config.
- Health check is `GET https://munshiai.co.in/api/health`. `curl -I` (HEAD) returns 405. Use `curl -s -o /dev/null -w "%{http_code}\n" https://munshiai.co.in/api/health` to assert 200. See `DECISIONS.md` #7 for the VITE_API_URL / redirect_slashes / Caddyfile routing contract.

## 15. Multi-Tenant Rules

- Every business record and query must be scoped to `factory_id`.
- Normal users must never access another factory's data.
- Detail/update/delete routes must verify object ownership by `factory_id`.
- Bulk upload must attach `current_user.factory_id` server-side.
- Invoice/PDF/payment/outstanding/dashboard routes must filter by `factory_id`.
- Super Admin bypass is allowed only through explicit `/api/super-admin/*` routes and must be audit-logged.

## 15A. Telegram Role Binding

- Telegram self-service bindings are user-level in `telegram_user_bindings`, scoped by both `factory_id` and `user_id`.
- Owner and Sub Owner may connect separate Telegram accounts within the same factory; Supervisor cannot access Telegram integration APIs.
- Owner-targeted alerts use active Owner user bindings first and fall back to legacy `factories.telegram_chat_id` for backward compatibility.
- Sub Owner bindings must never overwrite factory-level Telegram fields or receive Owner-originated action alerts.
- Activity alerts generated by Sub Owner or Supervisor are best-effort and must never roll back the underlying ERP transaction.

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
- Optional `BACKUP_ROOT` overrides master backup storage. Docker defaults to `/app/storage/backups`; directories are created only when a backup or restore staging operation runs.
- Scheduled backup email requires SMTP settings (`SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_HOST`, and optional port/TLS settings) and an active Owner email.
- The stack expects `.env` at repo root for `docker compose`.
- `.env` must never be committed.
- If a local secret appears in chat logs, screenshots, support tickets, or audit output, rotate it.

## 18. Wastage Intelligence

- `daily_wastage_snapshot` is the canonical daily deterministic wastage summary, unique by factory and date.
- Wastage calculations must prefer explicit `DailyProduction.wastage_kg`; fallback inference uses only the same factory's prior 30-day material-per-cup baseline.
- The onboarding fallback expected wastage is 2% until at least three usable historical production days exist.
- Wastage APIs, history, alerts, scheduler, and leaderboards must remain factory scoped.

## 18A. Production Material Consumption

- `BlankStock.weight_per_bora_kg` is optional during inventory setup but must be positive before bora-based production consumption.
- `DailyProduction` snapshots `blank_used_bora`, `blank_weight_per_bora_kg`, `blank_used_kg`, and `bottom_used_rolls`; historical consumption must not be derived from mutable current inventory settings.
- Production must validate available blank bora, blank kilograms, bottom rolls, bottom kilograms, and packaging boxes before mutating stock or flushing.

## 18A. Production Lifecycle

- `daily_productions.status` is the canonical lifecycle flag. Stock-effective states are `ACTIVE`, `pending_review`, and `verified`; non-effective states are `REJECTED` and `reversed`.
- Production entries are never hard-deleted for user mistakes. Reversal marks the original entry `reversed`, stores actor/time/reason, restores raw/carton stock, recalculates finished goods, and leaves audit history intact.
- Supervisors may create production and reverse only their own latest unverified entry within the configured 30-minute window. Owner/Sub-owner may verify production or reverse any unverified entry with a reason.
- Production save stores `stock_before_json` and `stock_after_json` for review panels, Daily Sequence, audit, and future Telegram actions.
- Shift production entry is batch-based: one `ProductionBatchWorkerLine` stores each worker's shared blank/bottom consumption, and child `ProductionBatchOutputLine` rows store multiple finished-good outputs for that worker.
- Each output creates a compatibility `DailyProduction` row; only the first output per worker carries explicit blank/bottom consumption, so raw material is never multiplied by output count.
- `POST /api/production/daily-batch` accepts `worker_cards[].outputs[]`, validates every worker/SKU/machine/carton mapping in the authenticated factory, and saves shift wastage once.
- Finished-goods stock calculations must include only `ACTIVE` production rows.
- Production history and worker summaries read `daily_productions` directly and remain factory scoped.
- Owner rejection requires a reason, records actor/timestamp, writes an ActivityLog, and reverses finished-goods impact through deterministic stock recalculation.
- Shift production batches are persisted in `production_batches` with worker detail in `production_batch_worker_lines`; each worker line also creates a compatibility `DailyProduction` row so existing worker summaries, briefing, costing, and historical reports remain intact.

## 19. Profit Intelligence

- `daily_profit_snapshot` is the canonical deterministic daily profitability summary, unique by factory and date.
- Revenue is actual same-day `SalesInvoice.total_amount`; outstanding future collections are never counted as revenue.
- Cost comes from the A2.1 paise breakdown. Wastage and collection gaps are risk signals only and must not be added again to total cost.
- No-revenue days return `Data not available` and must not trigger profit alerts.

## 20. Weekly Profit Digest

- Weekly digest reads existing daily snapshots only; it must never recompute cost, health, wastage, or profit.
- Reporting week is Monday through Sunday, delivered Sunday at 20:00 Asia/Kolkata.
- Weekly margin is weighted: total gross profit divided by total revenue. Never average daily margins.
- `weekly_digest_log` is unique by factory and week start and is the duplicate-send guard.

## 21. Factory Health History

- Health history APIs read `daily_factory_health_snapshot` only and remain factory scoped.
- Trend direction compares the current score with the available 7-day average using deterministic ±3 thresholds.
- Risk drilldown routes are Production `/production`, Attendance `/attendance`, Collections `/outstanding`, Inventory `/inventory`, and Cost `/cost-intelligence`.

## 22. Unified Alert Center

- `unified_alerts` is the canonical factory-scoped alert inbox.
- Dedupe is enforced by `(factory_id, dedupe_key)`; tenant IDs must never come from request payloads.
- Severity values are `INFO`, `WARNING`, and `CRITICAL`; status values are `OPEN`, `ACKNOWLEDGED`, and `RESOLVED`.
- Owner and Sub Owner may view and resolve alerts at `/alerts`.
- Critical alerts are sent immediately to active Owner Telegram bindings once per alert escalation.
- Morning briefings include the top three unresolved alerts; dashboards show the top five.

## 23. Invoice Intelligence

- Invoice numbers are allocated under factory/settings row locks and remain unique by `(factory_id, invoice_number)`.
- `InvoiceDocument` generation from a sale is idempotent; reprint and delivery actions never create a second invoice.
- GST invoices validate GSTIN shape and supported GST rates before any stock, ledger, or invoice write.
- Owner branding uses factory name, address, GSTIN, invoice prefix, and digital signature configuration.
- `invoice_delivery_logs` records download, reprint, Telegram, and email activity without changing invoice accounting data.
- Invoice PDFs and delivery/history endpoints must always verify `factory_id`.
- Authorized invoice signatures are stored in `factory_authorized_signatures`, unique by factory and role (`owner`, `sub_owner`, `supervisor`); image files live under `volumes/media/factory_signatures/{factory_id}/`.
- The API container must mount `./volumes/media:/app/volumes/media` so uploaded signatures remain available to ReportLab across container rebuilds.
- Invoice documents persist `generated_by_role`. PDF rendering uses that role's signature, falls back to the Owner signature, then renders only `Authorized Signatory` when no image exists.
- Signature uploads must remain factory scoped, image-validated, limited to 2 MB, and stored as file paths rather than base64 invoice payload data.

## 23A. Source-Aware Customer Ledger

- `outstanding_bills` is the canonical receivable source ledger; do not create a parallel balance table that double-counts it.
- Canonical source types are `opening_outstanding`, `invoice`, and `manual_adjustment`; legacy `opening_balance` rows remain readable and migrate in place.
- Opening outstanding is onboarding debt, never a generated invoice, and never changes stock.
- Opening outstanding edit/delete requires a reason, is audit logged, and delete is soft through `deleted_at`.
- Customer payments allocate in this order: opening outstanding, oldest invoice, manual adjustment, then other/newer receivables.
- `BillPayment` and `PaymentCollection.outstanding_bill_id` preserve source-level allocation history.
- Manual adjustments and payments never change stock. Only invoice creation and explicit invoice mistake reversal may change finished-goods stock.
- `/api/sales/outstanding` returns source labels, stock-impact flags, and source totals.
- `/api/sales/customers/{customer_id}/ledger` is the factory-scoped customer ledger timeline.

## 24. Telegram Nested ERP Menu

- `/menu` displays exactly four top-level inline buttons: Dekho, Kaam Karo, Alerts, and Settings.
- Read-only and action submenus use namespaced callback data and always include Back navigation.
- Menu state is stored per factory and Telegram user/chat through `TelegramActionSession`.
- Action placeholders must show Save, Edit, and Cancel confirmation buttons before any future business write.
- The current navigation phase performs no ERP business-table writes; legacy callbacks remain accepted for already-open Telegram messages.

## 24. AI Feature Vetting Rules

Before building any AI feature ask:

1. Will this help owner collect money?
2. Will this save owner time?
3. Will this prevent daily mistakes?

If all answers are NO:
Move feature to backlog.

Owner Value > Technical Complexity
Business Impact > Engineering Interest

## 25. Future Revenue Stream - WhatsApp Premium Add-on

- **Status**: Planned
- **Trigger**: After 5 active factories OR 30 days successful Telegram usage
- **Features**:
  - WhatsApp Daily Briefing
  - WhatsApp Invoice Delivery
  - WhatsApp Recovery Alerts
  - WhatsApp Collection Reminders
- **Pricing**: ₹299 + GST / month
- **Business Rule**: Telegram remains the default channel. WhatsApp is a paid convenience layer.

---
Referenced by `opencode.jsonc` instructions array.

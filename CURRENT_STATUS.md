# Munshi AI — Current Status

Snapshot date: 2026-06-05, after the foundation audit + bulk onboarding deep review + SLICE 0/1 prioritization + product roadmap review cycle. Detailed reasoning lives in session history; this file is the durable summary.

## 1. Current Technical Priority

Stabilize the Bulk Excel Onboarding module from M2 (functional but unstable) to M4 (hardened, pilot-ready). It is the single highest-leverage reliability work in the repo and the conversion funnel for every pilot factory's first 24 hours.

While this is in flight, do not start new feature work that does not directly fix a P0 production incident, tenant-isolation bug, security issue, or data-loss risk.

## 2. Current Product Priority

After P0/P1 stabilization, the priority sequence is:

  1. Razorpay subscription automation — revenue protection, 2-3 weeks.
  2. AI Factory Supervisor V1 (A1, A3, A4, A5) — morning briefing, downtime detection, outstanding alerts, low-stock alerts, 4-6 weeks.
  3. AI Factory Supervisor V1 (A2, A6-A10) — production vs target, cost per cup, attendance anomaly, owner Q&A, compliance prompts, suggestions, 4-6 weeks.
  4. Machine Downtime Module — structured product surface, 4 weeks.
  5. Factory Health Score — renewal conversations, 2-3 weeks.
  6. Pricing tier expansion (Starter / Growth / Optimization) — 1-2 weeks.
  7. Sales enablement assets — 1 week.

Vision: `ERP + AI Factory Supervisor`. The AI Supervisor is the daily reason the owner opens the app. The Cost Per Cup Engine is the long-term competitive moat.

## 3. P0/P1 Stabilization Plan

### P0 Immediate (~5 hours, today)

  P0.1  T1 — Cross-factory isolation test for bulk upload. AGENTS.md §6 production gate.
  P0.2  Lint rule: no bulk write path may omit current_user.factory_id scope.
  P0.3  Lint rule: no route may use literal factory_id from request body.
  P0.4  Lint rule: no Base.metadata.create_all in production startup.
  P0.5  T2 — Lock in the existing same-file reupload test in CI.
  P0.6  CI step: run the new lints and T1 on every PR.

### P1 Before Pilot (~2 days, this week)

  P1.1  Move all DDL in apps/api/schema_compat.py to a new Alembic revision (2026XXXX_0003_runtime_compat_consolidation). Make apply_runtime_compat_schema a no-op with deprecation warning.
  P1.2  Alembic revision 2026XXXX_0004_bulk_upload_uniqueness with:
          - uq_workers_factory_lower_name
          - uq_machines_factory_lower_name
  P1.3  Pre-migration dedupe script for workers and machines (dry-run + --apply).
  P1.4  Test: same-name concurrent uploads produce one row, no IntegrityError leaks to client.

### P2 After Pilot (defer; not blocking for 1-factory pilot)

  P2.1  C3-C7 unique indexes on blank_stock, bottom_stock, box_stock, plastic_stock, packaging_profiles.
  P2.2  C9, C10 CHECK constraints on stock tables and workers.
  P2.3  C8 verify finished_goods_stock.packaging_profile_id unique.
  P2.4  C12 bulk_upload_diffs table (paired with future savepoints).
  P2.5  T2-extended: idempotency tests for the 4 uncovered sub-tabs.
  P2.6  T3 concurrent upload test (multi-factory).
  P2.7  Per-sheet savepoints, Idempotency-Key header, sanitized IntegrityError, report UI, n8n outbox, audit trail UI, daily sequence UI.

### Total P0+P1 Effort

~22 hours, ~3 engineering days. Pilot can cut over once all P0 and P1 tasks are merged.

## 4. Post-Stabilization Build Order

Approximately 5 months of focused work after P0/P1 green:

  Build 1 — Razorpay subscription automation       2-3 weeks   revenue protection
  Build 2 — AI Supervisor V1 (A1, A3, A4, A5)     4-6 weeks   retention + moat
  Build 3 — AI Supervisor V1 (A2, A6-A10)         4-6 weeks   polish + query
  Build 4 — Machine Downtime Module               4 weeks     cost recovery
  Build 5 — Factory Health Score                  2-3 weeks   renewals
  Build 6 — Pricing tier expansion                1-2 weeks   tier-led growth
  Build 7 — Sales enablement assets               1 week      sales conversion

Deferred past this runway: pgBouncer, centralized monitoring, enterprise security, multi-factory benchmarking, cross-factory AI, supply chain integration. All become important at 10+ factories.

## 5. What Hermes Should Remember for Future Planning

  - The vision is `ERP + AI Factory Supervisor`, not ERP-with-a-chatbot. The AI Supervisor is the moat.
  - The persona is the Indian SME paper-cup/glass factory owner. They are the operator, often on a phone, often in Hindi. The product must meet them there.
  - `factory_id` isolation is a P0 production gate. Every bulk write, every list, every export, every PDF must scope to `current_user.factory_id`. Never trust a client-supplied factory_id.
  - The 165 lines of inline DDL in apps/api/schema_compat.py are a debt bomb. Alembic is the only schema authority.
  - Idempotency is enforced in two layers: SELECT-then-INSERT at the application layer, unique indexes at the DB layer. Pilot needs workers + machines DB-enforced. The rest can wait.
  - Bulk upload is the conversion funnel. The smoothness of the first 24 hours determines whether a pilot becomes a paying customer or churns.
  - Razorpay is currently manual. That is the first thing to automate post-stabilization.
  - The Cost Per Cup Engine is the customer's #1 long-term value driver and a competitive moat nobody else has for this vertical.
  - Items deferred to P2 are not forgotten; they are sequenced. Most become important at 5+ factories, urgent at 10+.
  - Production URL: https://munshiai.co.in (API at /api). Local repo at C:\Users\Prashant\OneDrive\Desktop\Coding Projects\ai-erp-system.
  - When asked to do something outside this priority list, check whether it fits "P0 production incident, tenant-isolation bug, security issue, or data-loss risk" before doing it.

## 6. Recently Resolved P0 Incidents (2026-06-05)

  - API base URL normalization / redirect loop fix: production inventory, onboarding, dashboard, and billing endpoints were returning `ERR_TOO_MANY_REDIRECTS` for every `/api/*` path. Root cause was a misconfigured `VITE_API_URL` that included the `/api` suffix, combined with FastAPI's default `redirect_slashes=True` and a Caddyfile that lacked explicit `reverse_proxy` blocks. Fixed in 4 files: `apps/web/src/lib/api.ts` (`getBaseURL` now strips a trailing `/api` defensively), `apps/api/main.py` (`FastAPI(redirect_slashes=False)`), `Caddyfile` (explicit `reverse_proxy` blocks with `header_up` and `encode gzip zstd`), `docker-compose.yml` (documentation comment on `VITE_API_URL`). Frontend `npm run build` passed. Hostinger VPS deploy pending. Codified as `DECISIONS.md` #7.
  - Open (separate frontend issue, not a routing fix): Recharts `width/height -1` warning is in a page outside the routing-fix inspection scope (likely `DashboardPage.tsx` or an analytics component). Track as its own ticket; fix in the file that hosts the chart.

# Munshi AI — Decisions

Durable record of architectural and product decisions. Each entry: Date, Decision, Reason, Alternatives Considered, Consequences. Detail and discussion live in session history and `AGENTS.md`; this file is the authoritative summary. Read it before proposing any change that would contradict a documented decision.

---

## 1. Worker canonical, Employee retained as compatibility

Date: 2026-06-05 (reaffirmed; original decision earlier, migration `20260605_0002` is in)

Decision
  Worker is the canonical table for staff, attendance, advance-payment, production, and onboarding writes. Employee remains as a compatibility table. Attendance and advance-payment records retain `employee_id` while preferring/backfilling `worker_id` only for exact same-factory matches. Compatibility listeners and legacy foreign keys remain active.

Reason
  New code needs a single source of truth. Employee has historical data, legacy foreign keys, and existing integrations. A destructive migration would risk production data, auditability, and the listener contract that downstream reports depend on. The compat layer preserves API contracts and historical data while letting new code move forward.

Alternatives considered
  (a) Drop Employee, migrate all data to Worker. Rejected: data loss, audit, and integration breakage.
  (b) Keep Employee as canonical, mirror to Worker. Rejected: Worker has the wider field set and is the natural fit for new features.
  (c) Keep both without a defined canonical. Rejected: dual-writes with no owner of truth invite drift.

Consequences
  Permanent dual-write overhead until deprecation. Drift risk if the listener misses a field. Two tables appear in any staff/attendance/payroll query. New writes must explicitly choose the canonical. Deprecation is gated on production backfill and compatibility-usage verification over time.

---

## 2. ERP + AI Factory Supervisor vision

Date: 2026-06-05

Decision
  Position Munshi AI as `ERP + AI Factory Supervisor`. The ERP is the system of record. The AI Supervisor is a persistent, proactive, multilingual advisor that gives the owner a daily reason to open the app. Both halves are the product; neither is a feature of the other.

Reason
  Pure ERP competes with Tally, Zoho, and SAP on commodity terms. A horizontal AI chatbot is not defensible. The intersection — vertical, persistent, multilingual, factory-data-grounded advice — is the moat. The Indian SME paper-cup/glass factory owner is the operator; they need both data and advice, and the product must combine them.

Alternatives considered
  (a) Pure ERP, AI as add-on later. Rejected: AI is the moat; without it, no defensibility.
  (b) Pure AI Assistant, partner with existing ERPs. Rejected: data quality and tenant isolation require first-party control.
  (c) AI Agent as optional paid add-on. Rejected: makes AI a feature instead of the product.
  (d) AI as a chatbot only (no proactive capabilities). Rejected: a chatbot is not the daily reason to open the app; a morning briefing is.

Consequences
  AI advice quality is bounded by ERP data quality. Any ERP improvement improves AI value automatically. The team must hold both halves accountable. Cost per cup is the unit of survival for the customer; it must be the most-tested, most-observed number in the system, and it must be surfaced in the AI morning briefing (capability A6).

---

## 3. Bulk Excel Onboarding stabilization before new features

Date: 2026-06-05

Decision
  The Bulk Excel Onboarding module must be stabilized from M2 to M4 before any new feature work that does not directly fix a P0 production incident, tenant-isolation bug, security issue, or data-loss risk. The full P0+P1 list lives in `CURRENT_STATUS.md` §3.

Reason
  Bulk upload is the conversion funnel for every pilot factory's first 24 hours. Today, same-file re-upload can crash on duplicate/integrity errors. `factory_id` isolation is not tested. The 165 lines of inline DDL in `apps/api/schema_compat.py` are a debt bomb. The cost of an unfixable onboarding bug at the first pilot is project credibility, not just data.

Alternatives considered
  (a) Stabilize in parallel with new features. Rejected: at ~3 engineering days, P0+P1 is small enough to do first; the new features are large enough to need undivided attention.
  (b) Defer stabilization until second pilot. Rejected: same-file re-upload crash is a P0 incident waiting to happen.
  (c) Stabilize in background while shipping new features. Rejected: an unfixable onboarding bug at pilot time is not recoverable through apologies.

Consequences
  A 3-day pause on net-new product work. Razorpay automation and AI Supervisor V1 are explicitly not started until P0+P1 is merged. Pilot cutover is gated on this. The stabilization deliverable is mechanical (lint rules + one isolation test + one Alembic move + two unique indexes) and has no product ambiguity.

---

## 4. Razorpay subscription automation before AI Supervisor V1

Date: 2026-06-05

Decision
  Razorpay subscription automation (BUILD-1 in `CURRENT_STATUS.md` §4) is the first post-stabilization build, ahead of AI Factory Supervisor V1.

Reason
  Razorpay is currently manual. The moment a pilot is live, every day a paid customer stays in "trial" because the webhook was not processed is a revenue leak. Every expired subscription that does not auto-dunning is churn. Razorpay automation protects revenue that already exists; AI Supervisor V1 protects revenue that is hoped for. Protect first, grow second.

Alternatives considered
  (a) AI Supervisor V1 first because it is the moat. Rejected: a moat does not pay rent.
  (b) Build both in parallel. Rejected: at 1-2 engineers, parallel builds split attention and ship neither well.
  (c) Defer Razorpay to month 6. Rejected: by then, the manual lifecycle will have leaked paid-but-still-in-trial cases and lost renewals.
  (d) Outsource billing to a third-party provider. Deferred until 10+ factories, when the integration cost amortizes.

Consequences
  AI Supervisor V1 starts in month 2-3 of the post-stabilization runway, not month 1. This is a deliberate delay on the highest-vision work in service of protecting existing revenue. Razorpay automation is reversible; manual subscription handling is not. The webhooks, dunning, and plan-limit enforcement become automated and observable; manual exceptions become a list with owners.

---

## 5. Cost Per Cup Engine as strategic moat

Date: 2026-06-05

Decision
  The Cost Per Cup Engine (today a thin calculator in `apps/api/routers/calculator.py` and partially surfaced in the UI) is positioned as a strategic competitive moat. It is elevated to a first-class product surface and the primary sales-enablement asset.

Reason
  Cost per cup is the unit of survival for the Indian SME paper-cup/glass factory. The customer optimizes their business around this number. No competitor (Tally, Zoho, SAP, MES) has a vertical-specific cost-per-cup engine for this industry. The number is the insight that justifies a 3x price over a spreadsheet, and it is the natural anchor for an "Optimization" plan tier.

Alternatives considered
  (a) Treat it as a feature inside the ERP, not a moat. Rejected: a feature is not defendable; a moat is.
  (b) Build a horizontal "factory P&L" instead. Rejected: too generic; SAP, Zoho, and the next AI entrant all do that.
  (c) Defer to post-Series-A. Rejected: the moat compounds with real customer data; building it now is the leverage.
  (d) Outsource the calculation to a third-party API. Rejected: the data is already in our DB and the calculation is domain-specific; an API adds latency and a privacy review.

Consequences
  The cost per cup calculation must be the most-tested, most-observed number in the system. AI Supervisor V1 surfaces it in the morning briefing (capability A6). Pricing tiers are anchored on it (Starter / Growth / Optimization). Sales conversations start with it. Any drift in the underlying material/labour/power data is a P0 incident.

---

## 6. factory_id isolation as non-negotiable architecture rule

Date: 2026-06-05

Decision
  `factory_id` isolation is the single most important architectural invariant. Every read, write, update, delete, upload, export, invoice, payment, and PDF must scope to `current_user.factory_id`. Client-supplied `factory_id` values are never honored. Spreadsheet-provided `factory_id` values are never honored. Super Admin bypass is allowed only through explicit `/api/super-admin/*` routes and is audit-logged.

Reason
  Munshi AI is multi-tenant SaaS. A single cross-tenant data leak is a P0 incident of the data-breach class, not just a bug. `AGENTS.md` §15 codifies this. The risk of a future contributor breaking it through convenience is high; the cost of any regression is also high. The invariant must be mechanically enforced, not by convention.

Alternatives considered
  (a) Trust developer discipline. Rejected: high regression risk, no enforcement.
  (b) PostgreSQL row-level security (RLS). Deferred: requires careful Alembic migration and adds a second authorization layer; revisit at 10+ factories.
  (c) Single-tenant architecture. Rejected: business model requires multi-tenant SaaS.
  (d) Schema-per-tenant. Rejected: operational cost is too high at 10+ factories and migration between factories becomes a project.

Consequences
  P0.1 (T1 isolation test) and P0.2/P0.3 (lint rules) in `CURRENT_STATUS.md` §3 are mandatory before pilot. Every new feature requires a `factory_id` scope test. Every bulk write requires an isolation assertion. The rule is enforced by CI, not by code review. The schema-compat listener pattern for Worker/Employee, ExpenseLog/FactoryExpense, and FinishedGoodsStock/FinalProductStock must never cross factory boundaries; this is verified by `tests/test_model_consolidation_sync.py`.

---

## 7. API base URL normalization / redirect loop fix

Date: 2026-06-05

Decision
  (a) `VITE_API_URL` must be the production origin only (e.g. `https://munshiai.co.in`). It must NEVER include the `/api` suffix. `apps/web/src/lib/api.ts getBaseURL()` strips a trailing `/api` defensively so older env values still work, but the canonical value is origin-only.
  (b) `apps/api/main.py` constructs the FastAPI app with `redirect_slashes=False`. Trailing-slash mismatches between frontend and backend return 404, never 307.
  (c) `Caddyfile` uses explicit `reverse_proxy` blocks with `header_up Host {host}`, `header_up X-Real-IP {remote_host}`, `header_up X-Forwarded-For {remote_host}`, `header_up X-Forwarded-Proto {scheme}` on BOTH upstreams (`api:8000` and `web:80`). The site block also includes `encode gzip zstd`.

Reason
  Production was systematically returning `ERR_TOO_MANY_REDIRECTS` for every `/api/*` path. Root cause was a `/api/api/...` double prefix caused by `VITE_API_URL` including the `/api` suffix, combined with FastAPI's default `redirect_slashes=True` issuing 307s that Caddy and the browser could not break out of. The fix is four small edits, but the rules it codifies prevent recurrence. A future operator who sets `VITE_API_URL=https://munshiai.co.in/api` will not reintroduce the bug because the `docker-compose.yml` comment documents the correct value AND `getBaseURL()` auto-normalizes legacy values. A future contributor who adds a new `/api/*` route will not create a redirect loop because `redirect_slashes=False` is global. A future contributor who touches the Caddyfile will not accidentally drop the explicit `reverse_proxy` block because the comment block above it documents why it is there.

Alternatives considered
  (a) Set `VITE_API_URL` correctly and rely on operator discipline. Rejected: silent regressions are inevitable; the `getBaseURL()` normalization is the safety net.
  (b) Keep `redirect_slashes=True` and align every frontend call to the exact backend route shape. Rejected: makes the frontend brittle to backend renames and adds a redirect round-trip on every cold call.
  (c) Use Caddy `handle_path` to strip `/api/*` prefix before forwarding. Rejected: FastAPI routes are registered under `/api/...` prefixes and changing this would require touching every router.
  (d) Move the API to a subdomain (e.g. `api.munshiai.co.in`) and drop Caddy `/api/*` routing entirely. Deferred to 10+ factories when the routing surface justifies the operational overhead.

Consequences
  `apps/web npm run build` is the deploy gate. `Caddyfile` and `apps/api/main.py` are the two files that must be touched together when adding a new `/api/*` route. The deploy must rebuild `api`, `web`, and `caddy` in that order so the new bundle is live before any request hits the new Caddy config. The actual production Caddy container name is `factory-erp-caddy-1` (Docker Compose project-name prefix); see `AGENTS.md` §14.

---

## 8. Universal AI Supervisor Strategy (4-Phase Path)

Date: 2026-06-06
NOTE: The original prompt for this decision called it "Entry #7" but `DECISIONS.md` already contained a 7th decision (the VITE_API_URL / Caddyfile routing fix from 2026-06-05). The new decision is therefore filed as Entry #8 to preserve the existing numbering.

Decision
  Munshi AI will evolve from a Paper Cup / Glass Factory ERP + AI Factory Supervisor into a Universal AI Supervisor across 4 sequential phases:

    PHASE A  Munshi Factory Supervisor                 (now → 6 months)
    PHASE B  Munshi Core extraction                   (6 → 18 months)
    PHASE C  One second industry template (Kirana)     (18 → 24 months)
    PHASE D  Munshi Studio (AI-driven template builder)  (24+ months)

  The phases are SEQUENTIAL, not parallel. We will not start Phase B before Phase A is producing revenue. We will not start Phase C before Phase B's Core extraction has shipped. We will not start Phase D before Phase C has at least one paying second-vertical customer.

Reason
  Three reasons drive the sequencing:

  R1  The Universal AI Supervisor vision is correct, but the engineering cost of doing all 4 phases in parallel is unaffordable at the current team size (1 founder + 1-2 collaborators). Each phase requires a distinct team composition, a distinct customer, and a distinct risk profile. Confusing them costs velocity.

  R2  The Core Engine as described in the Universal vision (Universal Business Ontology + AI Requirement Analyzer + Dynamic Schema Generator + Workflow Generator + Dashboard Generator + Agent Generator) does not yet exist. It must be EXTRACTED from the Factory app, not built greenfield. Extraction is a refactor-under-load exercise that requires the Factory app to be stable and well-instrumented. Phase A's job is to deliver that stability.

  R3  Templates are a SECOND product. Building a Kirana template before the Factory Supervisor is proven at scale produces a Kirana template that is not yet good. The cost of a bad second template (lost credibility, lost focus) is higher than the cost of a delayed second template. One template beyond paper-cup is the right ambition for Year 1 of Phase C, not 10.

Alternatives considered
  (a) Build all 6 layers of the Universal AI Supervisor in parallel with the Factory Supervisor. Rejected: spreads team too thin; the Universal work would be done by a team that does not yet understand the Factory domain; the result is a Universal system that is bad at Factory and bad at everything else.

  (b) Start with the AI Requirement Analyzer (Layer 2) and Dynamic Schema Generator (Layer 3) first, before the Factory Supervisor is finished. Rejected: the AI Requirement Analyzer is only as good as the templates it knows. With one template (Factory) in production, it can only generate Factory apps. It is not Universal yet. Building Layer 2 before Layer 1 (Ontology) and Layer 6 (Agent) is premature.

  (c) Build 5 industry templates in Year 1 (Kirana, Medical, Restaurant, Gym, Warehouse). Rejected: the team is too small; the templates will be thin; the customer value will be poor. 1 well-executed template (Kirana) is worth 5 mediocre ones.

  (d) Outsource the Universal work to an external team. Rejected: the moat IS the vertical knowledge + the customer data. An external team does not have either. They would build a generic system that competes with every horizontal SaaS in the world.

  (e) Acquire a second vertical (buy a Kirana POS company). Rejected: capital, integration, and cultural risk. We can build a Kirana template in 6 months for 1/10th the cost of an acquisition.

  (f) Skip Phase C and go directly from Core extraction (B) to Studio (D). Rejected: Phase C is the empirical test of whether the Core actually supports being templated. Skipping it means we discover Core limitations in production, not in development. The cost of discovering in production is much higher.

Consequences
  C1  Universal AI Supervisor timeline is 24+ months, not 6-12. Any investor pitch or team commitment must reflect this.

  C2  Phase A work (BUILD-1 through BUILD-7 + the 6-month roadmap in `MUNSHI_6_MONTH_ROADMAP.md`) is the only funded runway for the next 6 months. Phase B planning begins in Month 4 (whiteboard) and execution begins in Month 7 at earliest.

  C3  The team composition changes at each phase. Phase A = founder + 1-2 senior engineers. Phase B = founder + 1 senior engineer + 1 platform engineer. Phase C = founder + 1 senior + 1 platform + 1 industry specialist. Phase D = founder + 1 senior + 1 platform + 1 industry + 1 AI/ML engineer. Hire ahead of the phase, not during it.

  C4  The "10 industry templates" claim in any marketing or pitch deck must be downgraded. The accurate claim is "1 industry in production, 1 industry in design, 1 industry in roadmap, Universal OS in concept".

  C5  Phase D (Munshi Studio) is a separate product with separate pricing. It is not a feature of Munshi Factory. Do not conflate.

  C6  The Core Engine extraction (Phase B) is the highest-risk engineering work in the entire roadmap. It is a refactor under live load. Budget a 3-month feature freeze for the Factory app during the heart of the extraction.

  C7  The Moat capabilities identified in `AI_SUPERVISOR_V1.md` (Cost Intelligence, Production Intelligence, Morning Briefing) must remain the top priority through Phase A. They are the only way Phase A graduates to Phase B with credibility.

  C8  The team must resist the temptation to "skip ahead" to the Universal vision when a customer asks for it. The honest answer is "yes, we are building toward that, and the fastest path is to nail the Factory Supervisor first".

  C9  `AI_SUPERVISOR_V1.md` is the authoritative spec for the 10 capabilities. `AREAS.md` is the authoritative map for the 22 areas. `MUNSHI_6_MONTH_ROADMAP.md` is the authoritative 6-month plan. These three documents together with this decision form the durable Phase A specification.

Risks
  R1  Phase A drags on (no paying customers by Month 6) and the team runs out of money before Phase B. Mitigation: 3 paying pilots by Month 6 is a non-negotiable gate. If not hit, raise or reduce scope.

  R2  The Core extraction in Phase B reveals more coupling than expected, and the refactor takes 12+ months instead of 6. Mitigation: identify the coupling in Month 5 (whiteboard), not Month 7. If the coupling is too deep, extend Phase A or pivot to a different second template.

  R3  The chosen second template (Kirana) is not a good second choice. The data model may not transfer cleanly. Mitigation: validate the Kirana fit in Month 5 (architecture review) before committing to Phase C.

  R4  The AI Studio (Phase D) requires ML and AI capabilities we have not yet built (RAG, prompt versioning, eval suite, multilingual). These must be built in Phase A as part of the AI Brain area. If they are not, Phase D is blocked.

  R5  A competitor launches a Universal AI Supervisor for Indian SMBs before we get to Phase D. Mitigation: the competitor has to have built the vertical moat first. We will have it. The race is not "who is first to claim Universal" but "who has the vertical credibility to make Universal real". We are 6-12 months ahead on Factory vertical credibility.

  R6  Founder (Prashant) is the bottleneck. He is the architect, the lead engineer, the sales lead, and the customer success lead. Phase A tolerates this. Phase B does not. Hire #2 (senior engineer) must be done by Month 2.

Execution Order
  1.  Phase A: months 1-6 (see `MUNSHI_6_MONTH_ROADMAP.md`).
  2.  Phase B planning: months 4-6 (whiteboard, no code).
  3.  Phase B execution: months 7-18.
  4.  Phase C planning: months 16-18 (architecture review).
  5.  Phase C execution: months 19-24.
  6.  Phase D planning: months 22-24.
  7.  Phase D execution: months 25+.

  Kill criteria for advancing a phase:
    - Phase A → B: 3 paying pilots, NRR > 100%, 7 of 10 AI capabilities in production.
    - Phase B → C: Core extraction green for 30 days in production, "How to add a template" doc validated by 1 second engineer, second-vertical data model fits in Core abstractions.
    - Phase C → D: 1 paying second-vertical customer, second-vertical monthly retention > 80%, Universal Business Ontology expressed in code.

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

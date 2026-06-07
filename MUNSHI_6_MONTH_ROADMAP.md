# Munshi AI — 6-Month Execution Roadmap

Snapshot date: 2026-06-06
Goal: from ~48% vision completion / ~75% pilot readiness to
      Production+ readiness for 3 paying pilot customers.
Audience: founder, team, investors, advisors.
Total runway: 6 months, 6 parallel tracks, single engineer
              (Prashant) + 1-2 collaborators.

Assumptions
  M1 = July 2026 (relative to current 2026-06-06).
  P0/P1 Bulk Onboarding stabilization completes in M1 W1.
  First pilot factory is in onboarding by M1 W3.
  Cashfree credentials + sandbox are available by M1 W1.
  One additional engineer joins in M2 (assumption).
  One AI engineer joins in M3 (assumption).

================================================================
MONTH 1 — Stabilize + Pilot 1 Cutover + Razorpay Foundation
================================================================

Objectives
  - Complete Bulk Onboarding P0/P1 (the 22-hour plan).
  - Cut over the first pilot factory.
  - Stand up the Payments abstraction (Phase 1 of 8-phase
    design).
  - Begin webhook processing (Phase 2 of Payments).

Deliverables
  P0/P1 Bulk Onboarding
    T1 isolation test (P0.1)                       day 1
    3 lint rules (P0.2-P0.4)                       day 2
    T2 lock-in + CI step (P0.5-P0.6)               day 3
    schema_compat.py to Alembic (P1.1)             day 5
    workers + machines unique indexes (P1.2-P1.4)  day 7
  Pilot
    Pilot 1 onboarding                              day 8-14
    Bulk upload smoke test on non-pilot             day 14
    Pilot cutover                                   day 18-21
    Daily Production sanity check (manual)         day 22-25
  Payments (Phases 1-2 of 8-phase)
    apps/api/payments/ package (Phase 1)           day 10
    Webhook endpoint + idempotency (Phase 2)       day 14
  Closing
    End-of-month retrospective                      day 30

Risks
  R1  Pilot data has duplicates → P1.2 unique index fails.
      Mitigation: pre-migration dedupe script (P1.3) is
                  the precondition.
  R2  Cashfree sandbox credentials unavailable.
      Mitigation: defer webhook testing to M2; ship
                  Phase 1 only.
  R3  First pilot has data quality issues (handwritten
      register reality).
      Mitigation: P0 sanitization is in; bulk upload is
                  the funnel.
  R4  Prashant bandwidth. 22h of P0/P1 in week 1 plus
      pilot cutover in week 3 is tight solo.
      Mitigation: defer non-critical items to M2.

Dependencies
  Cashfree sandbox credentials (procure day 1).
  Pilot factory Owner availability (calendar day 1).
  1 additional engineer starts by M2 W1.

Success Criteria
  All P0/P1 CI steps green.
  Pilot factory uploaded master data via bulk upload
    without duplicate crash.
  Payments package importable; webhook endpoint accepts
    test event.
  Pilot Owner used dashboard at least once.

================================================================
MONTH 2 — Razorpay Automation + AI Supervisor V1 Foundation
================================================================

Objectives
  - Complete 8-phase Payments rollout (Phases 3-7).
  - Begin AI Supervisor V1 (Capabilities 1, 3, 4, 6).
  - Land Audit Trail UI (P1, pre-pilot prerequisite that
    slipped from M1).
  - Land RBAC route alignment + sidebar URL cleanup (P1).

Deliverables
  Payments (Phases 3-7 of 8-phase)
    Subscription state machine (Phase 3)            day 7
    Dunning engine (Phase 4)                        day 10
    Notification engine (Phase 5)                   day 14
    Super Admin payments views (Phase 6)            day 18
    Reconciliation worker (Phase 7)                 day 21
  AI Supervisor V1 foundation
    A1 Morning Briefing — schema + cron + Telegram   day 10
    A1 In-app card on /dashboard                     day 14
    A4 Inventory low-stock alerts                    day 18
    A6 Customer outstanding aging                   day 21
    A3 Production pace check (notification only)    day 24
  P1 cleanup
    Audit Trail UI (daily sequence review)          day 10
    RBAC route alignment                            day 14
    Sidebar absolute URL cleanup                    day 14
  Pilot
    Pilot data review with Owner                    day 7
    First subscription payment processed            day 14
    First dunning retry on a failed payment
      (synthetic)                                   day 21

Risks
  R1  Webhook reliability issue causes payment state
      drift.
      Mitigation: reconciliation worker catches within
                  24h.
  R2  Telegram bot rate limit (30 msg/s per bot).
      Mitigation: queue + backoff in Morning Briefing
                  cron.
  R3  AI engineer not yet hired → A1-A4 may slip.
      Mitigation: Prashant + generalist engineer cover;
                  defer A3.
  R4  Pilot Owner churns after 30 days.
      Mitigation: weekly check-in, usage analytics,
                  fast iteration.

Dependencies
  AI engineer starts M3 (so M2 AI work is on Prashant).
  Telegram bot token + rate-limit understanding.

Success Criteria
  First paid subscription auto-renewed without manual
    touch.
  One dunning cycle completed end-to-end.
  Morning Briefing fires daily at 7am for pilot factory.
  Low-stock alert fires correctly for one planted
    scenario.
  Pilot Owner opens app 5+ days in the month.

================================================================
MONTH 3 — AI Supervisor V1 Polish + Cost Intelligence +
          Pilot 2
================================================================

Objectives
  - Ship AI Supervisor V1 polish (Capabilities 2, 5, 10).
  - Surface Cost Per Cup Engine in the dashboard.
  - Onboard the second pilot factory.
  - Begin Factory Health Score instrumentation (app event
    log).

Deliverables
  AI Supervisor V1
    A2 Cost Intelligence — daily computation,
      dashboard widget                                day 7
    A2 Cost Intelligence — spike alert via Telegram   day 10
    A5 Worker Intelligence — anomaly detection        day 14
    A10 Conversational AI — chat UI in app,
      Hindi+English                                   day 18
    A10 Conversational AI — read-only tool schema
      locked                                          day 21
  Cost Per Cup Engine
    Elevate calculator to /cost-intelligence page     day 10
    Per-size cost breakdown chart                     day 14
    7-day and 30-day trend charts                     day 14
  Pilot 2
    Second pilot factory onboarding                    day 7-14
    Bulk upload on production-like data                day 14
    Cutover                                            day 18
  Factory Health Score foundation
    app_event log instrumentation
      (frontend + backend)                             day 14
    Health score SQL view                              day 21
  P2 (carryover)
    pg_dump verification before every deploy          ongoing
    Backup restore drill (repeat)                     day 28

Risks
  R1  Cost Intelligence math has a bug for multi-size
      production.
      Mitigation: write a test suite against the
                  calculator.
  R2  Conversational AI hallucinates a number.
      Mitigation: ground every response to a specific
                  SQL query.
  R3  Second pilot has data quality issues different
      from first.
      Mitigation: lessons-learned doc, bulk upload
                  template refined.
  R4  AI engineer is ramping up; productivity lower than
      expected.
      Mitigation: pair Prashant + AI engineer on the
                  chat surface.

Dependencies
  AI engineer onboarded.
  Production data from Pilot 1 for trend baselines.

Success Criteria
  Pilot 1 Owner checks cost-per-cup daily.
  Pilot 2 cutover with zero P0 incidents.
  Chat UI responds to 3 common questions correctly.
  Health score computed for both pilots (even if not
    surfaced).

================================================================
MONTH 4 — Pricing Tier Expansion + Machine Downtime
          Surface + DR Drill
================================================================

Objectives
  - Land 3-tier pricing (Starter / Growth / Optimization).
  - Build structured Machine Downtime product surface.
  - Begin Factory Health Score surface (Super Admin view).
  - DR drill on production DB.

Deliverables
  Pricing
    Define 3 tiers in /admin
      (Starter / Growth / Optimization)                day 3
    Pricing page updated                               day 5
    Feature gating per tier                            day 7
    Upgrade flow A/B test                              day 10
  Machine Downtime Module (BUILD-4)
    /machines page with downtime history               day 7
    Loss-in-rupee calculation                          day 10
    OEE per machine                                    day 14
    Downtime root-cause tags (manual)                  day 18
  Factory Health Score surface
    /super-admin/factories with health badges          day 14
    Weekly CSM digest                                  day 18
    Risk flag on score drop                            day 21
  Infrastructure
    DR restore drill on disposable production-clone    day 14
    Backup verification before every deploy            ongoing
  Pilot
    Pilot 1 + Pilot 2 weekly usage analytics review    weekly
    Churn risk review (silent owners)                  day 21

Risks
  R1  Pricing tier definition is wrong → upgrades don't
      convert.
      Mitigation: ship with manual override; iterate.
  R2  Downtime detection is unreliable → loss estimate
      is wrong.
      Mitigation: manual reconciliation as fallback
                  in V1.
  R3  Health score formula doesn't match CSM intuition.
      Mitigation: hand-tune weights with CSM for first
                  30 days.

Dependencies
  30 days of production data from Pilot 1 for health
    score baselines.
  CSM availability for health score tuning.

Success Criteria
  1 customer upgraded from Starter to Growth (or Growth
    to Optimization).
  Downtime loss-in-rupee is within 10% of manual
    calculation.
  DR restore drill succeeds.
  Health score visible to CSM for both pilots.

================================================================
MONTH 5 — Sales Enablement + Monitoring + Core Extraction
          Planning
================================================================

Objectives
  - Build sales enablement assets (Cost Per Cup demo,
    briefing demo).
  - Stand up centralized monitoring (Sentry + uptime +
    log aggregation).
  - Land retention playbook using Factory Health Score.
  - Begin Munshi Core extraction planning (whiteboard,
    no code yet).

Deliverables
  Sales enablement
    "Cost Per Cup in 60 seconds" demo video           day 5
    "Morning Briefing in 60 seconds" demo video       day 7
    Customer case study doc (Pilot 1, anonymized)     day 10
    Sales deck update                                  day 14
  Monitoring
    Sentry integration (frontend + backend)            day 7
    Uptime monitoring (UptimeRobot or Better Uptime)   day 7
    Centralized log aggregation (Loki or similar)      day 14
    API error rate dashboard                            day 14
    DB health dashboard (connections, locks, slow
      queries)                                          day 14
  Retention
    Renewal playbook using Factory Health Score        day 14
    Win-back email sequence for silent Owners          day 21
  Core extraction planning (no code)
    Identify vertical-agnostic vs vertical-specific
      code                                              day 14
    Write 1-page "How to add a template" doc           day 21
    Validate with a second engineer's review            day 28

Risks
  R1  Demo videos look amateur → don't close deals.
      Mitigation: hire freelance video editor; script
                  first.
  R2  Monitoring noise overwhelms the team.
      Mitigation: alert on signal, not on every error.
  R3  Core extraction planning reveals more coupling
      than expected.
      Mitigation: that's information, not failure.
                  Replan.

Dependencies
  At least one closed-won deal from new sales motion to
    anchor case study.
  Monitoring provider selection.

Success Criteria
  1 new factory customer closed using new sales assets.
  Onboarding time for new factory reduced by 25%
    (vs M1).
  Sentry catching real errors within 24h of occurrence.
  Core extraction plan reviewed and approved by 1 second
    engineer.

================================================================
MONTH 6 — Stabilize for Scale + Pilot 3 + Strategic Review
================================================================

Objectives
  - Onboard Pilot 3 (proves the playbook works for 3rd
    factory).
  - JWT cookie migration (P2 deferred for months).
  - Penetration test (security gate).
  - Strategic review: are we ready to start Phase B
    (Munshi Core)?

Deliverables
  Pilot 3
    Third factory onboarding                          day 7-14
    Cutover with refined playbook                     day 18
    Cohort comparison: usage vs Pilots 1+2            day 25
  Security
    JWT cookie migration                               day 14
    Penetration test engagement + remediation
      (day 14-25)                                      day 14-25
  Phase B readiness
    Strategic review with advisors                     day 21
    Decision: start Phase B (Core extraction) or
      extend Phase A
  Documentation
    AI_SUPERVISOR_V1.md updated to v1.1
      (post-M3 learnings)
    AREAS.md updated with current %                    day 25
    DECISIONS.md entries 8-10                          day 25

Risks
  R1  Pilot 3 has a different vertical (e.g., glass
      instead of paper cup) and reveals gaps in the
      data model.
      Mitigation: this is information. Adjust.
  R2  Penetration test finds P0 issues → blocks Phase B
      start.
      Mitigation: budget 1 month of remediation
                  post-pentest.
  R3  Strategic review concludes Munshi Core is
      premature.
      Mitigation: that's a valid outcome. Extend Phase A.

Dependencies
  2 healthy pilot customers willing to be case studies.
  Penetration test firm engaged.
  1-2 strategic advisors available for review.

Success Criteria
  3 paying pilot customers, all with active daily usage.
  Net revenue retention > 100% (no churn, some upgrade).
  Penetration test clean (no P0 findings).
  Strategic review decision: Phase B yes/no, with
    rationale.

================================================================
ROLL-UP BY TRACK
================================================================

TRACK 1 — Revenue (Payments + Subscription + Billing)
  M1: Phase 1-2 of Payments (package + webhook).
  M2: Phase 3-7 of Payments (state machine + dunning +
       notifications + super admin + reconciliation).
  M3: Phase 8 (production cutover).
  M4: Pricing tier expansion.
  M5: Renewal playbook + monitoring.
  M6: Stabilization + pentest.
  Outcome: end-to-end subscription lifecycle automated,
    3 tiers live.

TRACK 2 — Core ERP (Inventory + Production + Workers +
                CRM + Reporting)
  M1: Pilot 1 cutover (uses existing ERP, validates it).
  M2: Audit Trail UI + RBAC + sidebar cleanup.
  M3: Cost Per Cup Engine elevated to dashboard.
  M4: Downtime loss-in-rupee + OEE.
  M5: Usage analytics + case study.
  M6: Pilot 3 cutover with refined playbook.
  Outcome: ERP handles 3 paying customers with daily
    usage.

TRACK 3 — AI Supervisor (A1-A10)
  M2: A1 Morning Briefing, A3 notification, A4 low-stock,
       A6 outstanding (4 of 10).
  M3: A2 Cost Intelligence, A5 Worker, A10 Conversational
       (3 more, total 7 of 10).
  M4: A3 structured surface, A7 Payment Intelligence
       shipped with Payments, A8 Factory Health Score
       foundation (3 more, total 10 of 10).
  M5: A9 Predictive spec frozen; not built.
  M6: A1-A10 stabilized; feedback loops; eval suite.
  Outcome: 10 capabilities defined, 7 in production,
    3 in spec.

TRACK 4 — Infrastructure (Security + Testing + Monitoring
                          + Backups)
  M1: P0 isolation test + 3 lints + CI gate.
  M2: dunning + reconciliation.
  M3: DR drill.
  M4: DR drill on production clone.
  M5: Sentry + uptime + log aggregation + dashboards.
  M6: JWT cookie migration + pentest.
  Outcome: production-grade observability + security
    posture.

TRACK 5 — Pilot Success (Onboarding + Feedback + Usage +
                       Retention)
  M1: Pilot 1 cutover.
  M2: Weekly Owner check-in, usage analytics baseline.
  M3: Pilot 2 cutover; cohort comparison framework.
  M4: Health score visible to CSM; win-back sequence.
  M5: Case study from Pilot 1; sales assets.
  M6: Pilot 3 cutover; 3-customer retention report.
  Outcome: 3 paying pilots, NRR > 100%, 1 case study.

TRACK 6 — Future Platform (Munshi Core + Universal AI
                          Supervisor)
  M4: Identify vertical-agnostic vs specific code
       (no code).
  M5: 1-page "How to add a template" doc.
  M6: Strategic review: Phase B go/no-go.
  Outcome: decision and rationale, not code.

================================================================
RISK MATRIX (probability × impact)
================================================================

  Top 10 risks, ranked:

  R1   Pilot churn in first 30 days
       P: medium (3 pilots, 1 may churn) | I: high
       Mitigation: weekly check-in, fast iteration,
                   founder-led onboarding for first 3.

  R2   Cashfree webhook reliability
       P: medium (new integration) | I: high
       Mitigation: reconciliation worker catches within
                   24h.

  R3   AI engineer hire slips
       P: medium | I: high
       Mitigation: defer A5 and A9; keep A1-A4 on track.

  R4   Cost Per Cup math is wrong
       P: medium (multi-size allocation is subtle)
       I: high (this is the moat number)
       Mitigation: dedicated test suite + Pilot 1 Owner
                   validates manually for first 30 days.

  R5   Penetration test finds P0
       P: low-medium | I: high (blocks Phase B)
       Mitigation: budget remediation time in Month 7.

  R6   Prashant bandwidth (founder bottleneck)
       P: high | I: high
       Mitigation: hire 1-2 senior engineers M1-M2;
                   document architectural decisions
                   aggressively (this file).

  R7   Telegram API changes or rate limits
       P: low | I: medium
       Mitigation: in-app briefing is the fallback.

  R8   Cashfree credentials compromised
       P: low | I: high
       Mitigation: secret rotation cadence (M2).

  R9   Pilot data volume exceeds DB connection pool
       P: low (Postgres 16, but no pgBouncer) | I: high
       Mitigation: pgBouncer planned for Month 7-9.

  R10  Phase B decision is premature
       P: medium | I: low (strategic decision, not
                       failure)
       Mitigation: extend Phase A.

================================================================
END OF MUNSHI_6_MONTH_ROADMAP.md
================================================================

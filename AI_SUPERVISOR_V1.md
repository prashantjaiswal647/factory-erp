# Munshi AI — AI Supervisor V1 Specification

Snapshot date: 2026-06-06
Status: Draft, durable spec
Supersedes: A1-A10 framework from 2026-06-05 Chief Product Architect review
Source: AGENTS.md, PROJECT_MEMORY.md, CURRENT_STATUS.md, DECISIONS.md, archived Chief Product / Execution / Payments Architect reviews
Author: Chief AI Architect

This document is the canonical reference for the Munshi AI Supervisor. The 10 capabilities below are organized by intelligence domain. Each capability has 15 defined attributes. V1 / V2 / V3 scope is called out explicitly at the end. Moat analysis identifies which capabilities are uniquely defensible vs commoditizable.

Conventions
  P0    must ship in BUILD-2 or earlier
  P1    must ship in BUILD-3
  P2    ship in V2 (6-9 months after V1)
  P3    ship in V3 (12+ months)

================================================================
Capability 1: Morning Briefing
================================================================

1.  Capability Name
    Daily Morning Briefing (supersedes A1 in the 2026-06-05 framework)

2.  Business Objective
    Be the first thing the owner reads each morning. Replace 20-30
    minutes of mental assembly (Telegram messages, paper chits,
    memory) with a single 6-line Telegram push and a richer
    in-app card. Make Munshi the daily reason to open the app.

3.  User Persona
    Owner (primary, mobile-first, often Hindi, on phone at 6:30am).
    Operator (secondary, reads on shift start, prefers email).
    Accountant (tertiary, weekly digest mode).

4.  Inputs Required
    Yesterday: cups produced (DailyProduction), downtime hours
    (Telemetry), workers present (Attendance), sales booked
    (Sales), payments received (Payment), outstanding aging
    buckets (OutstandingBill).
    Today: open sales orders (Sales), planned production
    (DailyProduction plan), machines scheduled (MachineSchedule),
    workers scheduled (WorkerSchedule).
    Overnight: alert queue (union of A2-A9 events, last 14 hours).

5.  Outputs Generated
    6-line Telegram message in Hindi+English mix, one line per
    section (Production, Workers, Sales, Payments, Outstanding,
    Risks).
    In-app card on /dashboard with expandable detail per section.
    Voice note (Hindi TTS) for hands-free listening, on by
    default for Owners.
    Weekly digest variant for Accountants (Sunday 8pm).

6.  AI Reasoning Layer
    Template-based generation. Each section is a deterministic
    rollup of one or more data sources, not a free-form LLM call.
    Optional LLM step: rewrite the bullets in the owner's
    preferred tone/language, with 3-sentence max and a strict
    token budget. Structure is fixed; wording can vary.

7.  Required Data Sources
    DailyProduction, Telemetry, Attendance, Sales, Payment,
    OutstandingBill, WorkerSchedule, MachineSchedule, alert_queue.

8.  Required Database Objects
    Read-only joins across existing tables. One new table:
      morning_briefing_log (
        id, factory_id, briefing_date, generated_at,
        content_json jsonb, sent_channels jsonb,
        delivery_status, owner_locale
      )
    Idempotency: UNIQUE (factory_id, briefing_date).

9.  Required UI Surfaces
    /dashboard top card.
    Telegram bot push.
    Optional email to operator.
    Optional voice note (Hindi TTS).

10. Automation Opportunities
    Cron at 6:55am local (timezone stored on factory).
    Failure mode: if Telegram push fails, in-app card still
    surfaces. Retry 3x at 5-minute intervals.
    If all fail, alert sent to Super Admin with factory_id
    and reason.

11. Notifications
    Telegram (primary, 95% expected reach).
    In-app banner (primary, always).
    Email (secondary, operator).
    Voice (Hindi TTS, optional, default ON for Owners).

12. KPI Impact
    DAU +30-50% (target: owner opens app 5+ days/week).
    Retention -15-20% churn. Single biggest retention lever.
    Sales enablement: "see the briefing at 7am every day" is
    the headline demo.

13. Complexity
    M. Aggregation logic (medium), template engine (low),
    scheduled job (low), notification fan-out (medium),
    Hindi TTS integration (medium), Telegram bot reliability
    (medium-high).

14. Priority
    P0 within BUILD-2. Ship after Razorpay automation (BUILD-1)
    and before all other AI capabilities.

15. Current Status
    0% built. Spec frozen. Schema design pending. Telegram
    bot already exists (R9 in prior review) but is not
    briefing-aware. Hindi TTS provider not yet selected.

================================================================
Capability 2: Cost Intelligence
================================================================

1.  Capability Name
    Cost Intelligence (supersedes A6 — Cost per cup tracking)

2.  Business Objective
    Surface cost-per-cup as a first-class product metric. Make
    the owner able to answer "what is my cost per cup today,
    this week, this month, and why is it moving?" in 10 seconds.
    This is the unit of survival for the customer and the
    strategic moat for Munshi.

3.  User Persona
    Owner (primary, on phone, weekly check).
    Accountant (primary, daily check).
    Operator (secondary, alerts when cost spikes).

4.  Inputs Required
    Material consumption (raw material: blank, bottom reel,
    box, plastic, packing).
    Labour (attendance × wage rate, including overtime).
    Power (machine hours × kWh rate, estimated).
    Overhead allocation (configurable %).

5.  Outputs Generated
    Today's cost per cup (in paise, with comparison to 7-day
    and 30-day average).
    7-day trend chart.
    30-day trend chart.
    Per-size cost breakdown (210ml, 250ml, 350ml).
    Cost spike alert (today > 5% above 30-day avg).

6.  AI Reasoning Layer
    Deterministic calculation from existing data (no LLM for
    the math). LLM step: explain the spike in 2 sentences max,
    grounded to specific input data ("material cost up 4.2%
    on the 210ml line because blank stock price rose 6% this
    week — see the supplier note in /inventory").

7.  Required Data Sources
    DailyProduction (cups produced), Material consumption
    (raw material out), Attendance + Worker (labour cost),
    Telemetry (machine hours for power), factory_settings
    (overhead %, power rate).

8.  Required Database Objects
    Read-only joins across existing tables. One new table:
      cost_per_cup_daily (
        factory_id, date, size_ml,
        material_cost_paise, labour_cost_paise,
        power_cost_paise, overhead_cost_paise,
        total_cost_paise, cups_produced,
        computed_at
      )
    UNIQUE (factory_id, date, size_ml). Daily cron recomputes.

9.  Required UI Surfaces
    /dashboard card (today's cost per cup vs 30-day average).
    /cost-intelligence dedicated page (trends, per-size
    breakdown, spike explanation).
    Telegram push on spike.

10. Automation Opportunities
    Daily cron at 23:55 local.
    On spike (>5% above 30-day), generate Telegram push within
    15 minutes.
    Optional weekly summary email to Owner.

11. Notifications
    Telegram push on spike only (not daily — daily is in-app).
    Weekly email summary.

12. KPI Impact
    Sales enablement: "show me my cost per cup" is the demo.
    Customer expansion: unlocks the "Optimization" plan tier.
    Retention: makes the Owner depend on Munshi for the one
    number that matters.

13. Complexity
    M-L. Math is simple; per-size allocation, spike detection,
    and the LLM explanation are medium. ~3-4 weeks.

14. Priority
    P1 within BUILD-3. Ship after A1 (Morning Briefing) and
    A3 (Production Intelligence).

15. Current Status
    30% built. apps/api/routers/calculator.py exists. /calculator
    page exists. NOT surfaced in dashboard. NOT computed daily.
    NOT scoped per size. Spec is to elevate, not build greenfield.

================================================================
Capability 3: Production Intelligence
================================================================

1.  Capability Name
    Production Intelligence (supersedes A2 + A3 combined —
    Production vs target + Machine Downtime auto-detection)

2.  Business Objective
    Detect production-vs-target gaps in real time. Detect machine
    downtime automatically and quantify the loss. Reduce the
    "where are we vs plan?" anxiety that the owner carries.

3.  User Persona
    Owner (primary, on phone, real-time alerts).
    Operator (primary, on shop floor, real-time dashboard).
    Accountant (secondary, end-of-day summary).

4.  Inputs Required
    DailyProduction plan (cups planned per shift).
    DailyProduction actuals (cups produced, recorded per shift
    or per-hour via Telemetry).
    Machine Telemetry (status, last_heartbeat, hours_run).
    Machine target output (cups per hour, configured per machine).
    Cup price (for loss-in-rupee calculation).

5.  Outputs Generated
    Production pace alert (in-app banner + Telegram) when
    actual < 80% of pace at 60% of shift.
    Downtime alert (Telegram + in-app) with loss estimate
    (target_output × hours_lost × cup_price).
    End-of-day production summary in next-day Morning Briefing.

6.  AI Reasoning Layer
    Rule-based: threshold comparison.
    LLM step (optional): summarize the day's production story
    for the briefing ("Production was 12% below target; the
    250ml line lost 2 hours to a heater issue on the 250ml
    machine"). Bounded to 2 sentences.

7.  Required Data Sources
    DailyProduction, Telemetry, Machine (target_output_per_hour,
    cup_price, hourly_power_kwh), Sales (cup_price fallback).

8.  Required Database Objects
    Read existing tables. One new table:
      downtime_event (
        id, factory_id, machine_id,
        started_at, ended_at, duration_minutes,
        target_lost_cups, estimated_loss_inr,
        detection_method, acknowledged_at, acknowledged_by
      )
    Detection: telemetry gap (heartbeat > N min while
    status=Running) OR end-of-shift reconciliation.

9.  Required UI Surfaces
    /production page real-time dashboard.
    /machines page with downtime history.
    Telegram push on alert.
    In-app banner on alert.

10. Automation Opportunities
    Hourly check on production pace.
    Every-5-minute check on telemetry gaps.
    Auto-create downtime_event on detection.
    Auto-close on machine heartbeat resume.

11. Notifications
    Telegram push (downtime + pace breach).
    In-app banner.
    Daily summary in next-day Morning Briefing.

12. KPI Impact
    V2 in prior review: 1-2 hours per incident saved, ~1
    incident per week per factory.
    Revenue impact: enables the "Optimization" plan tier.
    Sales enablement: downtime cost in rupees is the most
    concrete number the customer sees.

13. Complexity
    L. Real-time telemetry processing is non-trivial. Heartbeat-
    based detection requires reliable time-series. ~4-5 weeks.

14. Priority
    P1 within BUILD-2 (downtime detection as a notification).
    Structured surface lands in BUILD-4.

15. Current Status
    40% built. DailyProduction exists. Telemetry exists.
    Downtime auto-detection NOT built. Cost-of-downtime
    calculation NOT built. Per-shift pace check NOT built.

================================================================
Capability 4: Inventory Intelligence
================================================================

1.  Capability Name
    Inventory Intelligence (supersedes A5)

2.  Business Objective
    Eliminate stockouts and overstock. Tell the owner "you
    will run out of blank stock in 2.3 days at current
    consumption" before it happens.

3.  User Persona
    Owner (primary, on phone, weekly check + alerts).
    Operator (primary, daily reorder review).
    Accountant (secondary, monthly valuation).

4.  Inputs Required
    Current stock levels (raw material + finished goods +
    packaging).
    Consumption rate (last 7-day, 30-day).
    Lead time per supplier (configured).
    Reorder point per item (configured, or auto-derived from
    consumption + lead time + safety stock).

5.  Outputs Generated
    Low-stock alert (Telegram + in-app) per item when stock
    <= reorder point.
    Critical-stock alert (Telegram, urgent) when stock
    <= 0.5 × reorder point.
    Days-of-stock estimate ("blank stock will last 2.3 days
    at current pace").
    Supplier pre-filled reorder suggestion.

6.  AI Reasoning Layer
    Rule-based: stock <= reorder_point.
    LLM step (optional, V2): explain unusual consumption
    ("blank stock consumption up 18% this week — correlate
    with 250ml line ramp-up"). Bounded to 2 sentences.

7.  Required Data Sources
    blank_stock, bottom_stock, box_stock, plastic_stock,
    packaging_profiles, finished_goods_stock,
    raw_material_consumption, supplier (configured lead times).

8.  Required Database Objects
    Read existing tables. Add columns:
      blank_stock.reorder_point (numeric)
      blank_stock.lead_time_days (int)
      ... same for the other stock tables.
    New table:
      low_stock_event (
        id, factory_id, item_type, item_id,
        stock_at_event, reorder_point, days_of_stock,
        sent_at, acknowledged_at
      )

9.  Required UI Surfaces
    /inventory page (already exists, redesign in progress).
    In-app banner on critical.
    Telegram push on critical only (low is in-app).

10. Automation Opportunities
    Hourly check on all stock items.
    Auto-create low_stock_event on threshold breach.
    Auto-deduplicate (don't fire same alert twice in 24h
    unless stock drops further).

11. Notifications
    Telegram push on critical only.
    In-app banner on low and critical.
    Daily digest to Operator.

12. KPI Impact
    V11 in prior review: 1 hour saved per stockout incident.
    Material waste reduction (early reorder avoids
    panic-buying at premium price).

13. Complexity
    M. Item-type heterogeneity is the main challenge
    (5+ stock tables). ~3-4 weeks.

14. Priority
    P1 within BUILD-2 (low-stock alerts as notification).
    Inventory redesign UX lands in parallel.

15. Current Status
    50% built. Stock tables exist. Consumption tracked.
    Reorder point NOT auto-computed. Telegram push NOT wired.
    Critical vs low distinction NOT made.

================================================================
Capability 5: Worker Intelligence
================================================================

1.  Capability Name
    Worker Intelligence (supersedes A7)

2.  Business Objective
    Surface worker patterns that affect production: attendance
    anomalies, overtime creep, advance payment concentration,
    skill-to-machine mismatch. Help the owner run a tighter
    workforce.

3.  User Persona
    Owner (primary, on phone, weekly review).
    Operator (primary, daily attendance review).
    HR/Accountant (secondary, payroll reconciliation).

4.  Inputs Required
    Attendance (last 14 days per worker).
    Advance payments (last 90 days per worker).
    Production output per worker (if tracked).
    Worker schedule. Wage rate.

5.  Outputs Generated
    Attendance anomaly alert (Telegram + in-app) when a
    worker has > 2 unexpected absences in 14 days.
    Overtime flag (in-app) when weekly hours > threshold.
    Advance payment concentration alert (in-app) when single
    worker has > 30% of total advance in last 90 days.
    Worker productivity summary (in-app, monthly).

6.  AI Reasoning Layer
    Rule-based: threshold comparisons.
    LLM step (optional, V2): "why is attendance dropping
    for worker X?" with 1-sentence possible cause
    ("may correlate with Diwali festival period in your
    region"). Bounded.

7.  Required Data Sources
    Attendance, AdvancePayment, Worker (wage rate, role,
    join_date), DailyProduction (worker_id if tracked).

8.  Required Database Objects
    Read existing tables. One new table:
      worker_alert (
        id, factory_id, worker_id, alert_type, severity,
        fired_at, context_json, acknowledged_at
      )

9.  Required UI Surfaces
    /staff page with worker cards.
    /staff/{id} detail with alert history.
    Telegram push on attendance anomaly only.

10. Automation Opportunities
    Daily check (1am local).
    Auto-aggregate 14-day attendance per worker.
    Auto-aggregate 90-day advance per worker.

11. Notifications
    Telegram push on attendance anomaly.
    In-app banners. Weekly digest to Owner.

12. KPI Impact
    V5 in prior review: 2-3 hours/week saved.
    Workforce stability (early flag prevents surprise
    resignations).

13. Complexity
    M. ~3 weeks.

14. Priority
    P2 within BUILD-3.

15. Current Status
    60% built. Attendance exists. Advance exists.
    Anomaly detection NOT built. Worker productivity not
    surfaced.

================================================================
Capability 6: Customer Intelligence
================================================================

1.  Capability Name
    Customer Intelligence (supersedes A4 — outstanding,
    expanded to credit, segments, churn risk)

2.  Business Objective
    Prevent revenue leakage from credit. Identify customers
    at risk of churn. Surface credit concentration risk.
    Help the owner make credit decisions faster.

3.  User Persona
    Owner (primary, weekly review).
    Accountant (primary, daily collection review).
    Sales/Operator (secondary, customer order review).

4.  Inputs Required
    Outstanding bills (age buckets, per customer).
    Payment history (on-time vs late, last 6 months).
    Order frequency (last 90 days). Order size trend.
    Credit limit (configured per customer, optional).

5.  Outputs Generated
    Outstanding aging digest (weekly, in-app + email).
    Critical outstanding alert (Telegram, daily) for bills
    > 60 days.
    One-tap "send reminder" action (Telegram inline button
    → triggers a templated WhatsApp/SMS to customer).
    Credit concentration alert (in-app) when single customer
    > 30% of total outstanding.
    Churn risk flag (in-app) when order frequency drops
    > 50% week-over-week.

6.  AI Reasoning Layer
    Rule-based: aging buckets, frequency comparisons.
    LLM step (V2, optional): draft the reminder message in
    the customer's language. Bounded to template variants.

7.  Required Data Sources
    OutstandingBill, Payment, Sales, Customer (credit_limit,
    contact_phone, contact_email).

8.  Required Database Objects
    Read existing tables. One new table:
      customer_intelligence_event (
        id, factory_id, customer_id, event_type, severity,
        fired_at, context_json, action_taken, acknowledged_at
      )

9.  Required UI Surfaces
    /customers page with risk badges.
    /outstanding page with aging buckets and one-tap
    reminder.
    Telegram inline buttons for critical actions.

10. Automation Opportunities
    Daily check on outstanding.
    Weekly digest generation.
    Churn detection weekly.
    Reminder dispatch (templated) on tap.

11. Notifications
    Telegram push on critical (bills > 60 days, concentration).
    Weekly email digest. In-app banners.

12. KPI Impact
    V6 in prior review: 1-2 hours/week + cash recovered.
    Cash flow improvement: recovering 90-day outstanding pays
    for a year of subscription.

13. Complexity
    M. ~3-4 weeks.

14. Priority
    P1 within BUILD-2 (A4 already in scope of BUILD-2).

15. Current Status
    55% built. Outstanding tracking exists. Aging buckets
    exist. One-tap reminder NOT built. Churn risk NOT built.
    Concentration alert NOT built.

================================================================
Capability 7: Payment Intelligence
================================================================

1.  Capability Name
    Payment Intelligence (derives from Payments/Billing +
    Razorpay/Cashfree)

2.  Business Objective
    Make the owner never surprised by a payment failure.
    Recover failed subscription payments through automated
    dunning. Surface collection efficiency as a metric.

3.  User Persona
    Owner (primary, alerts on payment failure).
    Accountant (primary, daily collection review).
    Super Admin (secondary, audit + intervention).

4.  Inputs Required
    Subscription state (active, past_due, suspended, cancelled).
    Payment event log (success, failed, retried).
    Dunning schedule (configured retry cadence: +1, +3,
    +7, +14 days).
    Customer payment method health (gateway-side).

5.  Outputs Generated
    Payment failed alert (Telegram + in-app) on webhook event.
    Dunning in-progress status (in-app).
    Suspended warning (Telegram, urgent) at day +14.
    Cancelled confirmation (Telegram + email) at day +30.
    Recovery confirmation (Telegram + in-app) when
    past_due → active.
    Collection efficiency metric (monthly, in-app):
    successful auto-charges / total invoices.

6.  AI Reasoning Layer
    State machine (no LLM). Notification cadence is fixed by
    the dunning schedule.
    Optional LLM step (V2): explain why a payment might have
    failed ("your card on file expired last month — please
    update it").

7.  Required Data Sources
    payment_subscription, payment_event, payment_dunning,
    factories (owner contact).

8.  Required Database Objects
    (from the 8-phase Payments design) payment_subscription,
    payment_event, payment_dunning, payment_audit_log.
    Read across these.

9.  Required UI Surfaces
    /billing page with subscription state.
    /billing/payments with retry history.
    Super Admin: /super-admin/payments with cross-factory view.

10. Automation Opportunities
    Dunning worker (cron, daily).
    State transitions on webhook.
    Notification fan-out on each transition.

11. Notifications
    Telegram push on failure, recovery, suspension, cancellation.
    In-app banners. Email on suspension and cancellation.

12. KPI Impact
    Revenue protection: stops the revenue leak from manual
    subscription handling. MRR retention. Single biggest
    revenue-protection lever.

13. Complexity
    L (8-phase rollout, ~6-8 weeks per Chief Payments Architect
    design).

14. Priority
    P0 — this is BUILD-1, the first post-stabilization build.
    Blocks pilot cutover on a clean subscription lifecycle.

15. Current Status
    35% built. Razorpay partial. Cashfree partial. Webhook
    NOT processed. Dunning NOT automated. The 8-phase design
    is the spec; nothing has shipped.

================================================================
Capability 8: Factory Health Intelligence
================================================================

1.  Capability Name
    Factory Health Intelligence (supersedes BUILD-5 / R11)

2.  Business Objective
    Give the owner and Munshi's CSM a single number that
    summarizes "how is this factory doing?" Use it in renewal
    conversations. Detect silent churn risk (owner stops
    opening the app).

3.  User Persona
    Owner (sees own score, monthly).
    Super Admin / CSM (sees all scores, weekly).
    Sales (uses score in renewal conversations).

4.  Inputs Required
    App engagement: DAU, MAU, last_open_at, feature usage
    frequency.
    Data quality: % of days with complete DailyProduction,
    % of machines with telemetry, % of workers with attendance.
    Financial: collection rate, outstanding aging trend,
    cost-per-cup trend.
    Operational: downtime trend, production-vs-target trend.

5.  Outputs Generated
    Single health score (0-100) per factory, with 5 sub-scores
    (Engagement, Data Quality, Financial, Operational, Cost).
    Monthly trend chart.
    Risk flag if score drops > 10 points in 30 days.
    Renewal playbook hint (e.g., "data quality low — schedule
    a re-onboarding call").

6.  AI Reasoning Layer
    Weighted sum with configurable weights per sub-score.
    LLM step (optional, V2): generate the renewal playbook
    narrative. Bounded to 3 sentences.

7.  Required Data Sources
    app_event (new), DailyProduction, Telemetry, Attendance,
    Payment, OutstandingBill, cost_per_cup_daily.

8.  Required Database Objects
    New table:
      app_event (
        id, factory_id, user_id, event_type, event_at,
        context_json
      )
      UNIQUE (factory_id, user_id, event_type, event_at).
    New table:
      factory_health_score (
        id, factory_id, computed_at, overall_score,
        engagement_score, data_quality_score,
        financial_score, operational_score, cost_score,
        playbook_hint, context_json
      )

9.  Required UI Surfaces
    /super-admin/factories with health badges.
    /dashboard owner-side mini health widget.
    Renewal email template that includes the score.

10. Automation Opportunities
    Daily health score computation.
    Weekly CSM digest.
    Risk flag generation on drop.

11. Notifications
    Weekly digest to CSM. In-app owner widget.
    Renewal email.

12. KPI Impact
    Renewal conversations become data-driven, not
    relationship-driven. Silent churn risk is caught early.

13. Complexity
    M. ~2-3 weeks. Depends on app_event log being in place
    (the logging instrumentation is the bulk of the work).

14. Priority
    P2 — scheduled as BUILD-5 (post-pilot hardening).

15. Current Status
    5% built. Spec frozen. App event log NOT instrumented.
    Health score NOT computed. Depends on AI Supervisor data
    being in production for 2-3 months.

================================================================
Capability 9: Predictive Intelligence
================================================================

1.  Capability Name
    Predictive Intelligence (supersedes A10 Smart Suggestions
    + new predictive models)

2.  Business Objective
    Move from "Munshi tells you what happened" to "Munshi
    tells you what will happen". Forecast stockouts, downtime,
    payment failures, churn. Suggest 1-2 next-best-actions
    per day.

3.  User Persona
    Owner (primary, daily suggestions + forecasts).
    Operator (primary, weekly forecast review).
    Sales (secondary, churn-risk list).

4.  Inputs Required
    Historical data (per capability 2-8 outputs).
    External: Indian holiday calendar, regional events
    (configurable), weather (V2, optional).
    Market data (V3, optional).

5.  Outputs Generated
    Stockout forecast ("blank stock will run out on June 12
    if consumption continues").
    Downtime forecast ("machine M3 has had 3 stoppages in
    14 days — schedule preventive maintenance").
    Payment failure risk per subscription.
    Customer churn risk per customer.
    Next-best-action: 1-2 suggestions per day, ranked,
    non-spammy.

6.  AI Reasoning Layer
    V1: simple time-series + threshold-based.
    V2: classical ML (prophet, sklearn).
    V3: LLM-augmented suggestions with grounded context.
    NOT V1: deep learning, custom neural nets.

7.  Required Data Sources
    All Capability 2-8 outputs. Indian holiday calendar
    (static config).

8.  Required Database Objects
    Read existing tables. New table:
      prediction (
        id, factory_id, prediction_type, target_id,
        predicted_value, predicted_for_date, confidence,
        context_json, generated_at, expires_at
      )

9.  Required UI Surfaces
    /dashboard "Tomorrow" card.
    /insights page with full forecast list.
    Telegram push on high-confidence predictions only.

10. Automation Opportunities
    Daily forecast generation.
    Suggestion ranking (heuristic in V1).
    Feedback loop: did the user act on the suggestion?
    (track via app_event).

11. Notifications
    Telegram push on high-confidence predictions (1/day max).
    In-app card on dashboard. Weekly email summary.

12. KPI Impact
    Highest of any capability. The shift from descriptive to
    predictive is the "AI Factory Supervisor" moment.
    Revenue: enables the "Optimization" plan tier.

13. Complexity
    L-VL. Forecasting is easy; trustworthy forecasting is
    hard. Cold start (no historical data) is the main
    challenge. V1 scope is time-series only; V2 adds ML.
    ~6-8 weeks for V1.

14. Priority
    P3 — scheduled for V2 of the AI Supervisor (after V1 is
    in production for 2-3 months).

15. Current Status
    0% built. Spec not frozen. Depends on V1 capabilities
    generating historical data.

================================================================
Capability 10: Conversational AI Supervisor
================================================================

1.  Capability Name
    Conversational AI Supervisor (supersedes A8 + part of A10)

2.  Business Objective
    Let the owner ask questions in natural language (Hindi or
    English, voice or text) and get a factory-grounded,
    data-anchored answer. Examples: "कल कितने कप बने?",
    "What was last week's cost per cup on the 250ml line?",
    "Who is the top customer this month?"

3.  User Persona
    Owner (primary, voice on phone, on the go).
    Operator (primary, text in app, daily use).
    Accountant (secondary, text).

4.  Inputs Required
    Natural language question (Hindi/English).
    factory_id (from authenticated session).
    Recent context (last 5 questions in the conversation).
    User's preferred language.

5.  Outputs Generated
    Concise answer in user's language, anchored to specific
    data points.
    Optional: chart or table rendered in-app.
    Optional: link to the relevant page.
    Optional: follow-up suggestion ("want me to send this
    to your Telegram?").

6.  AI Reasoning Layer
    Tool-calling LLM (already exists as ai_agent.py).
    V1 scope: read-only queries only.
    RAG layer for company-specific knowledge (V2).
    Voice input/output (V3).
    Multilingual fine-tuning (V3).

7.  Required Data Sources
    All factory data (read-only).
    User context (factory_id, role, language preference).
    App event log (V2, for personalization).

8.  Required Database Objects
    Read all existing tables. New tables:
      conversation_log (
        id, factory_id, user_id, started_at,
        last_message_at, message_count, language
      )
      conversation_message (
        id, conversation_id, role, content,
        tool_calls jsonb, latency_ms, created_at
      )

9.  Required UI Surfaces
    /chat page in app. Telegram bot (text + voice).
    Voice note reply via Hindi TTS.

10. Automation Opportunities
    V1: human-initiated only.
    V2: proactive suggestions based on conversation history.

11. Notifications
    None (V1 is pull-based). V2: optional weekly recap.

12. KPI Impact
    Stickiness (V12 in prior review, 5-10 min/day saved).
    Funnel for cross-sell: "want to see this on a chart?
    upgrade to Growth tier".

13. Complexity
    M. The LLM is the easy part; the tool schema, the safety
    guardrails, the Hindi tokenization, the latency, and the
    conversation memory are the work. ~4-6 weeks.

14. Priority
    P1 within BUILD-3 (chat surface in app, Hindi+English,
    read-only).

15. Current Status
    35% built. ai_agent.py exists.
    parse_factory_intent_with_agent exists.
    build_ai_tool_context exists. NOT surfaced as chat UI.
    NOT multilingual. No memory. No RAG.

================================================================
V1 SCOPE  (ship in BUILD-2 + BUILD-3, ~10-12 weeks)
================================================================

Capabilities in V1:
  1.  Morning Briefing              P0  BUILD-2
  3.  Production Intelligence       P1  BUILD-2 (detection only)
  4.  Inventory Intelligence        P1  BUILD-2 (alerts only)
  6.  Customer Intelligence         P1  BUILD-2 (outstanding only)
  7.  Payment Intelligence          P0  BUILD-1, ships with V1
  10. Conversational AI Supervisor  P1  BUILD-3 (read-only chat)

V1 must NOT include:
  - Autonomous decision-making
  - Multi-factory optimization
  - Cross-factory benchmarking
  - Voice input
  - Predictive ML
  - Auto-tuning machine parameters
  - Auto-filer GST
  - Customer-facing AI
  - Predictive forecasting
  - RAG layer

================================================================
V2 SCOPE  (~6-9 months after V1)
================================================================

All V1 capabilities, plus:
  2.  Cost Intelligence             (elevated to dashboard widget)
  5.  Worker Intelligence           (full surface)
  8.  Factory Health Intelligence   (in CSM workflow)
  -   RAG layer for company docs
  -   Multi-language fine-tuning (Hindi, Marathi, Tamil)
  -   Voice input (Hindi, voice-to-text)
  -   Customer-facing AI for store inquiries (read-only)

================================================================
V3 SCOPE  (12+ months)
================================================================

All V2 capabilities, plus:
  9.  Predictive Intelligence       (forecasting)
  -   Autonomous suggestions with feedback loop
  -   Multi-factory benchmarking (Super Admin view)
  -   Voice output (Hindi TTS for all briefings)
  -   Cross-tenant pattern learning (privacy-preserving)

================================================================
MOAT ANALYSIS
================================================================

Direct revenue (capability → revenue mechanism):
  7.  Payment Intelligence         protects MRR, dunning recovery
  1.  Morning Briefing              retention = LTV
  6.  Customer Intelligence         cash recovery, retention

Moat (defensible 12-18 months):
  1.  Morning Briefing              daily habit, hard to replicate
                                     without data integration
  2.  Cost Intelligence             vertical-specific, no horizontal
                                     competitor has it
  3.  Production Intelligence       telemetry + downtime cost =
                                     deep integration
  7.  Payment Intelligence          multi-tenant dunning =
                                     operational moat
  9.  Predictive Intelligence       historical data = compounding moat

Commoditizable (12+ months to copy):
  4.  Inventory Intelligence        generic stock alert, every SaaS
                                     can do this
  5.  Worker Intelligence           HR analytics, off-the-shelf
  8.  Factory Health Intelligence   health score is a pattern,
                                     easy to copy
  10. Conversational AI Supervisor  tool-calling LLM is commodity;
                                     the moat is the tool schema

Uniquely defensible (vertical + data + time):
  1.  Morning Briefing    in paper-cup/glass
  2.  Cost Intelligence  in paper-cup/glass
  3.  Production Intelligence (downtime cost) in paper-cup/glass
  9.  Predictive Intelligence (after 6+ months of paper-cup data)

Top 3 moat capabilities (in priority order):
  1.  Cost Intelligence
  2.  Production Intelligence (downtime cost)
  3.  Morning Briefing (daily habit)

This reorders the user's prior intuition: the moat is NOT the
chatbot (10). The moat IS the cost number (2), the downtime
cost (3), and the daily habit (1). The chatbot is the surface;
the cost number is the substance.

================================================================
END OF AI_SUPERVISOR_V1.md
================================================================

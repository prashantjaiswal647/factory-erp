# Munshi AI — Areas

Snapshot date: 2026-06-06
Purpose: Permanent capability map for all 22 Munshi AI areas.
Source: AGENTS.md, PROJECT_MEMORY.md, CURRENT_STATUS.md, DECISIONS.md, AI_SUPERVISOR_V1.md, archived session reviews.
Owner: Chief Systems Architect

This document is the canonical reference for what Munshi AI contains. For each area, eight attributes are defined. The maturity matrix, dependency graph, and critical/strategic/future classification support planning.

Conventions
  %Done      self-reported, snapshot-date 2026-06-06, weighted
             by strategic value
  Maturity   Prototype | MVP | Beta | Production | Production+
             | Scale Ready
  Owner Type founder | product engineer | platform engineer
             | AI engineer | payments specialist | content+product

================================================================
1. SaaS ERP
================================================================

1.  Area Name
    SaaS ERP (the platform foundation)
2.  Purpose
    Multi-tenant SaaS shell: tenancy, auth, RBAC, routing,
    deployment, observability, billing infrastructure, app
    shell. The substrate on which every other area runs.
3.  Business Value
    Without this, nothing else ships. Source of the most
    subtle bugs (tenant isolation, auth drift, RBAC
    inconsistency).
4.  Dependencies
    Auth → RBAC → all other areas.
    Deployment → CI/CD → all other areas.
    Multi-tenancy → every area.
5.  Current Completion %
    72%
6.  Maturity Level
    MVP
7.  Owner Type
    Platform team (Prashant + 1 senior). Cannot be delegated
    to a junior.
8.  Future Direction
    JWT cookie migration (P2, post-pilot, security).
    pgBouncer (P2, post-10 factories).
    Centralized monitoring (P2, post-10 factories).
    Multi-region (P3, post-100 factories).

================================================================
2. Inventory
================================================================

1.  Area Name
    Inventory (Raw Material + Packaging + Finished Goods)
2.  Purpose
    Track every consumable and sellable item from purchase
    to consumption/sale. Enable the owner to answer "what
    do I have, what's low, what did I use?" in seconds.
3.  Business Value
    R7 in the prior review. V11 customer value. Blocks
    stockouts (1 hour saved per incident). Material waste
    reduction. The data layer for cost-per-cup.
4.  Dependencies
    Depends on: SaaS ERP (auth, tenancy), Workers
    (consumption attribution).
    Depended on by: Production, Cost Intelligence, AI
    Supervisor Inventory Intelligence.
5.  Current Completion %
    65%
6.  Maturity Level
    MVP
7.  Owner Type
    Product engineer (1) + UX (0.5). Inventory Redesign
    session in flight.
8.  Future Direction
    Reorder point auto-computation (BUILD-2).
    Per-size finished goods inventory (currently aggregated).
    Lot/batch tracking for raw material (traceability + GST).
    Barcode/QR scanning (V3, mobile).

================================================================
3. Production
================================================================

1.  Area Name
    Production (DailyProduction + Telemetry + Machine)
2.  Purpose
    Record actual production output per shift, per machine,
    per size. Capture machine telemetry. Reconcile plan vs
    actual.
3.  Business Value
    R6 in prior review (downtime cost recovery). V4 customer
    value (15 min/day + anxiety). Data layer for Production
    Intelligence.
4.  Dependencies
    Depends on: Inventory (consumption), Workers (labour),
    Machines (target output).
    Depended on by: Cost Intelligence, Production
    Intelligence, AI Supervisor.
5.  Current Completion %
    60%
6.  Maturity Level
    MVP
7.  Owner Type
    Product engineer (1) + IoT specialist (0.5, for
    telemetry).
8.  Future Direction
    Real-time pace tracking (BUILD-2).
    Downtime auto-detection (BUILD-2 notification, BUILD-4
    surface).
    OEE calculation (BUILD-4).
    Predictive maintenance (V3).

================================================================
4. Workers
================================================================

1.  Area Name
    Workers (Staff + Attendance + Advance + Payroll)
2.  Purpose
    Manage the workforce: profiles, attendance, advance
    payments, payroll, hisab settlement. Worker is
    canonical; Employee is compat.
3.  Business Value
    V5 customer value (2-3 hours/week saved). R7
    (retention). Data layer for Worker Intelligence.
4.  Dependencies
    Depends on: SaaS ERP (auth), Production (worker
    attribution).
    Depended on by: Attendance, Payroll, Worker
    Intelligence, Cost Intelligence.
5.  Current Completion %
    75%
6.  Maturity Level
    MVP
7.  Owner Type
    Product engineer (1). Migration 20260605_0002 done.
8.  Future Direction
    Payroll UI (currently backend-heavy, UI thin).
    Worker skill tags (for machine assignment).
    Geo-tagged attendance (V3).
    Aadhaar-linked onboarding (V3, regulatory).

================================================================
5. Attendance
================================================================

1.  Area Name
    Attendance (Daily check-in + Daily Sequence)
2.  Purpose
    Record daily worker presence. Capture per-shift
    attendance. Surface to the daily sequence log.
3.  Business Value
    Direct feed for payroll, cost, and worker intelligence.
    Audit-trail value.
4.  Dependencies
    Depends on: Workers, Daily Sequence.
    Depended on by: Payroll, Cost Intelligence, Worker
    Intelligence.
5.  Current Completion %
    70%
6.  Maturity Level
    MVP
7.  Owner Type
    Same product engineer as Workers.
8.  Future Direction
    Biometric integration (V3).
    Geo-tagged (V3).
    Anomaly detection (Worker Intelligence, BUILD-3).
    Per-shift reconciliation UI (P1).

================================================================
6. CRM
================================================================

1.  Area Name
    CRM (Customer + Customer Activity + Outstanding)
2.  Purpose
    Track customer profiles, activity, orders, payments,
    outstanding. Enable credit decisions. Surface customer
    intelligence.
3.  Business Value
    R7 cash recovery. V6 customer value. Data layer for
    Customer Intelligence and Sales.
4.  Dependencies
    Depends on: SaaS ERP.
    Depended on by: Sales, Customer Intelligence,
    Outstanding.
5.  Current Completion %
    55%
6.  Maturity Level
    MVP
7.  Owner Type
    Product engineer (0.5) — currently piggybacks on
    Sales engineer.
8.  Future Direction
    Customer segments + tags.
    Activity timeline enrichment.
    Customer portal (separate area, V3).
    Credit limit auto-suggestion (Customer Intelligence,
    BUILD-2).

================================================================
7. Sales
================================================================

1.  Area Name
    Sales (Orders + Invoicing + GST)
2.  Purpose
    Order-to-cash workflow. From customer order → invoice
    → GST-compliant document → payment recording.
3.  Business Value
    R7 cash recovery. V7 customer value. Daily revenue.
    Data layer for Customer Intelligence and Cost
    Intelligence.
4.  Dependencies
    Depends on: CRM, Inventory, Billing.
    Depended on by: Customer Intelligence, Payment
    Intelligence, AI Supervisor.
5.  Current Completion %
    65%
6.  Maturity Level
    MVP
7.  Owner Type
    Product engineer (1) + GST specialist (0.25).
8.  Future Direction
    Returns flow (V2).
    Multi-channel order entry (walk-in vs phone-order, V2).
    E-commerce integration (V3).
    Auto-reconciliation with bank statement (V2).

================================================================
8. Payments
================================================================

1.  Area Name
    Payments (Razorpay + Cashfree + Future Gateways)
2.  Purpose
    Process customer payments via gateway abstraction.
    Handle subscriptions, one-time, refunds. Webhook
    processing. Dunning.
3.  Business Value
    R2 revenue protection. Direct MRR. Single biggest
    revenue-protection lever.
4.  Dependencies
    Depends on: SaaS ERP, Billing, Subscription.
    Depended on by: Billing, Subscription, Payment
    Intelligence, Super Admin.
5.  Current Completion %
    40%
6.  Maturity Level
    MVP (partial)
7.  Owner Type
    Payments specialist (1) + backend (0.5). Critical hire.
8.  Future Direction
    8-phase rollout per Chief Payments Architect design.
    Razorpay automation (BUILD-1).
    Cashfree as default.
    Future gateway adapter (Stripe, PayU).

================================================================
9. Billing
================================================================

1.  Area Name
    Billing (Invoice PDF + GST + Auto Counters)
2.  Purpose
    Generate GST-compliant invoices. PDF rendering.
    Idempotent generation per sale. Factory invoice
    counters.
3.  Business Value
    R8 (must-have, not growth lever). V7 customer value.
    Regulatory compliance.
4.  Dependencies
    Depends on: Sales, SaaS ERP.
    Depended on by: Payments, Customer Intelligence.
5.  Current Completion %
    70%
6.  Maturity Level
    MVP
7.  Owner Type
    Product engineer (0.5).
8.  Future Direction
    Auto-reconciliation with bank statement.
    E-invoicing (when GST mandate lands).
    Credit note / debit note flow.
    Multi-currency (V3).

================================================================
10. Subscription
================================================================

1.  Area Name
    Subscription (Plans + Trial + Renewals)
2.  Purpose
    Manage factory subscriptions: plan selection, trial
    period, renewals, cancellations, provider switching.
3.  Business Value
    R2 (revenue lifecycle). Top-of-funnel conversion (R3).
    MRR. Expansion (Starter→Growth→Optimization).
4.  Dependencies
    Depends on: SaaS ERP, Payments.
    Depended on by: Payment Intelligence, Super Admin.
5.  Current Completion %
    35%
6.  Maturity Level
    Beta (plans exist, lifecycle is manual)
7.  Owner Type
    Payments specialist + Super Admin engineer.
8.  Future Direction
    Razorpay + Cashfree integration (BUILD-1).
    Per-tenant provider switching (post-BUILD-1).
    Plan tier expansion (BUILD-6: Starter/Growth/
    Optimization).
    Trial abuse detection.

================================================================
11. Super Admin
================================================================

1.  Area Name
    Super Admin (Cross-factory visibility)
2.  Purpose
    Munshi internal team surface: list factories, view
    subscriptions, audit, manual overrides, support tools.
3.  Business Value
    R10 (B2B sales enablement). Customer support. Audit.
    C9 (multi-tenant data isolation with a tested
    production record).
4.  Dependencies
    Depends on: every other area (cross-cutting).
    Depended on by: Internal team only.
5.  Current Completion %
    60%
6.  Maturity Level
    MVP
7.  Owner Type
    Backend engineer (0.5) — currently ad-hoc.
8.  Future Direction
    Audit Log UI (P1, pre-pilot).
    Per-tenant support tools (BUILD-7).
    Customer impersonation (with audit).
    Factory Health Score dashboard (BUILD-5).

================================================================
12. AI Supervisor
================================================================

1.  Area Name
    AI Supervisor (10 capabilities per AI_SUPERVISOR_V1.md)
2.  Purpose
    The persistent, proactive, multilingual advisor. Daily
    reason the owner opens the app. The moat.
3.  Business Value
    R4 (retention). C1 (the moat). V1 (daily value). The
    strategic asset of the company.
4.  Dependencies
    Depends on: every other area (data sources).
    Depended on by: nothing internal. It is the
    customer-facing AI.
5.  Current Completion %
    20%
6.  Maturity Level
    Prototype (ai_agent.py exists, no capabilities shipped)
7.  Owner Type
    AI engineer (1) + product engineer (1) + prompt
    engineer (0.5). Most leveraged hires.
8.  Future Direction
    V1 = 6 capabilities (BUILD-2 + BUILD-3).
    V2 = 8 capabilities + RAG + multilingual.
    V3 = 10 capabilities + predictive + voice.
    Phase D = Universal AI Supervisor Studio.

================================================================
13. AI Brain
================================================================

1.  Area Name
    AI Brain (LLM tooling, context, memory, RAG)
2.  Purpose
    The substrate the AI Supervisor runs on: tool schema,
    context builder, memory, RAG layer, prompt versioning,
    eval suite.
3.  Business Value
    Foundation for AI Supervisor. Without it, the
    Supervisor is brittle.
4.  Dependencies
    Depends on: SaaS ERP, every data area (for tool schema).
    Depended on by: AI Supervisor.
5.  Current Completion %
    35%
6.  Maturity Level
    Prototype
7.  Owner Type
    AI engineer (1).
8.  Future Direction
    RAG layer (V2).
    Per-factory memory + context.
    Prompt versioning + eval suite.
    Tool schema expansion as new areas ship.

================================================================
14. Voice Agent
================================================================

1.  Area Name
    Voice Agent (Hindi/English voice interface)
2.  Purpose
    Voice-first interface for owners who don't want to
    type. Hindi STT → intent → tool call → Hindi TTS.
3.  Business Value
    Persona fit (owner is on phone, often in Hindi).
    Stickiness. V1 ceiling lifter.
4.  Dependencies
    Depends on: AI Brain, AI Supervisor.
    Depended on by: nothing (it's an alternate interface).
5.  Current Completion %
    0%
6.  Maturity Level
    Not started
7.  Owner Type
    AI engineer (1) + speech specialist (0.25). Defer hire
    to V2.
8.  Future Direction
    V2: Voice input on Conversational AI Supervisor.
    V3: Voice output for all briefings.
    V3: Outbound voice (Proactive AI calling the owner).

================================================================
15. LMS
================================================================

1.  Area Name
    LMS (Worker Training + Owner Education)
2.  Purpose
    Training content for workers (machine operation,
    safety) and owners (ERP usage, growth playbooks).
    In-app + video.
3.  Business Value
    Onboarding speed. Worker quality. Owner retention.
4.  Dependencies
    Depends on: SaaS ERP (auth), Workers.
    Depended on by: nothing critical.
5.  Current Completion %
    0%
6.  Maturity Level
    Not started
7.  Owner Type
    Content + product (0.5). Defer hire to V3.
8.  Future Direction
    V3: Worker training videos.
    V3: Owner growth playbooks.
    V3: Certification tracking.

================================================================
16. RAG (Knowledge Layer)
================================================================

1.  Area Name
    RAG (Retrieval-Augmented Generation)
2.  Purpose
    Factory-specific knowledge base: company docs,
    manuals, GST rules, regional festival calendar,
    supplier notes. Retrieval layer for the AI Supervisor.
3.  Business Value
    Lifts the AI Supervisor from "queries data" to
    "uses your docs". Highest single lever for V2 AI
    value.
4.  Dependencies
    Depends on: AI Brain.
    Depended on by: AI Supervisor (V2+), Voice Agent (V3).
5.  Current Completion %
    0%
6.  Maturity Level
    Not started
7.  Owner Type
    AI engineer (1). Vector store TBD.
8.  Future Direction
    V2: Doc upload + retrieval for owner Q&A.
    V2: GST rule retrieval.
    V3: Multilingual doc retrieval.
    V3: Cross-factory anonymized pattern retrieval.

================================================================
17. Factory Intelligence
================================================================

1.  Area Name
    Factory Intelligence (Health Score + Predictive)
2.  Purpose
    Aggregate signals across all areas into a single
    health score per factory. Detect silent churn. Power
    renewal conversations.
3.  Business Value
    R11 (renewal conversations). C8 (CSM-style
    data-driven renewal). Long-term NRR lever.
4.  Dependencies
    Depends on: every other area (aggregation).
    Depended on by: Super Admin, Sales, CSM.
5.  Current Completion %
    10%
6.  Maturity Level
    Not started (scheduled as BUILD-5)
7.  Owner Type
    Data engineer (0.5) + product (0.25).
8.  Future Direction
    BUILD-5: Factory Health Score.
    V3: Predictive churn models.
    V3: Cross-factory benchmarking (Super Admin).

================================================================
18. Automation (n8n)
================================================================

1.  Area Name
    Automation (n8n flows + outbox)
2.  Purpose
    Customer-specific workflow automation. Integration
    with Telegram, WhatsApp, email, banking. Outbox
    pattern for guaranteed delivery.
3.  Business Value
    C7 (n8n as the integration fabric). Per-customer
    customization. Sales differentiator.
4.  Dependencies
    Depends on: SaaS ERP.
    Depended on by: AI Supervisor (notifications),
    Customer Intelligence (reminders), Payment
    Intelligence (dunning).
5.  Current Completion %
    45%
6.  Maturity Level
    MVP
7.  Owner Type
    Backend engineer (0.5) + DevOps (0.25).
8.  Future Direction
    Outbox pattern (P2, post-pilot).
    Customer-facing workflow library (BUILD-7).
    n8n backup + DR.
    Per-factory n8n isolation (security).

================================================================
19. Security
================================================================

1.  Area Name
    Security (Auth, RBAC, Secrets, PCI scope, Caddy)
2.  Purpose
    Authenticate, authorize, encrypt, audit, isolate.
    Stay within PCI-DSS SAQ A scope. Never leak
    cross-tenant data. Never expose internal exceptions.
3.  Business Value
    C9 (multi-tenant data isolation as a sales asset).
    Trust foundation. Non-negotiable.
4.  Dependencies
    Depends on: SaaS ERP.
    Depended on by: every other area.
5.  Current Completion %
    65%
6.  Maturity Level
    MVP
7.  Owner Type
    Security-conscious senior engineer (Prashant).
    Cannot be delegated.
8.  Future Direction
    JWT cookie migration (P2).
    Secret rotation cadence (P2).
    PG RLS (P2, post-10 factories).
    Penetration test (P1, pre-pilot).
    Bug bounty (V3, post-100 factories).

================================================================
20. Multi-Tenancy
================================================================

1.  Area Name
    Multi-Tenancy (factory_id isolation, tenant lifecycle)
2.  Purpose
    Every read, write, update, delete, upload, export,
    invoice, payment, and PDF scopes to
    current_user.factory_id. Client-supplied factory_id
    is never honored.
3.  Business Value
    P0 production gate (AGENTS.md §6, §15). Sales asset
    (C9). Non-negotiable.
4.  Dependencies
    Depends on: SaaS ERP, Security.
    Depended on by: every business-data area.
5.  Current Completion %
    70%
6.  Maturity Level
    MVP (P0 isolation test lands this week)
7.  Owner Type
    Same as Security.
8.  Future Direction
    T1 isolation test (P0, this week).
    3 lint rules (P0, this week).
    CI gate (P0, this week).
    PG RLS (P2, post-10 factories).
    Per-tenant API keys (V3).

================================================================
21. Reporting
================================================================

1.  Area Name
    Reporting (Dashboard + Analytics + Scheduled Reports)
2.  Purpose
    Surface operational, financial, and AI-generated
    insights in dashboards. Schedule PDF/email reports.
    Enable ad-hoc queries.
3.  Business Value
    Retention. Renewal conversations. Sales enablement.
4.  Dependencies
    Depends on: every data area.
    Depended on by: nothing critical.
5.  Current Completion %
    40%
6.  Maturity Level
    MVP
7.  Owner Type
    Product engineer (0.5) + data viz (0.25).
8.  Future Direction
    Cost-per-cup trend chart (BUILD-3).
    Scheduled PDF/email reports (V2).
    Cross-period comparisons (V2).
    Ad-hoc query builder (V3).

================================================================
22. Customer Portal
================================================================

1.  Area Name
    Customer Portal (Logged-in customer surface)
2.  Purpose
    Self-serve surface for the buyer's customer: view
    orders, download invoices, see payment history, get
    reminders, place re-orders. Public-facing or
    invited-login.
3.  Business Value
    Reduces Owner/Accountant workload. Customer
    stickiness. Indirect retention lever.
4.  Dependencies
    Depends on: CRM, Sales, Billing.
    Depended on by: nothing critical.
5.  Current Completion %
    30%
6.  Maturity Level
    MVP (Storefront exists; no logged-in portal)
7.  Owner Type
    Product engineer (0.5).
8.  Future Direction
    V2: Logged-in customer view (order history, invoice
    download).
    V2: Self-serve payment link.
    V3: Re-order surface.
    V3: Customer-facing AI for order queries.

================================================================
MATURITY MATRIX
================================================================

  Area                  %Done   Maturity    Strategic Wt  Weighted
  ────────────────────  ──────  ──────────  ────────────  ────────
  SaaS ERP              72      MVP         Core          72
  Inventory             65      MVP         Core          65
  Production            60      MVP         Core          60
  Workers               75      MVP         Core          75
  Attendance            70      MVP         Core          70
  CRM                   55      MVP         Core          55
  Sales                 65      MVP         Core          65
  Payments              40      MVP         Core (rev)    60
  Billing               70      MVP         Core          70
  Subscription          35      Beta        Core (rev)    55
  Super Admin           60      MVP         Core          60
  AI Supervisor         20      Prototype   Moat          80
  AI Brain              35      Prototype   Moat          55
  Voice Agent            0      Not started Future          0
  LMS                    0      Not started Future          0
  RAG                    0      Not started Moat (V2)     30
  Factory Intelligence  10      Not started Future         25
  Automation            45      MVP         Core          45
  Security              65      MVP         Non-negot     90
  Multi-Tenancy         70      MVP         Non-negot     95
  Reporting             40      MVP         Retention     40
  Customer Portal       30      MVP         Retention V2  35

  Weighted overall: ~52% (consistent with prior estimate)

================================================================
DEPENDENCY GRAPH
================================================================

  Foundation layer (no dependencies on other Munshi areas):
    SaaS ERP
    Security
    Multi-Tenancy
    AI Brain

  Layer 1 (depend on Foundation):
    Inventory
    Workers
    CRM
    Automation

  Layer 2 (depend on Layer 1):
    Production         → Inventory, Workers
    Attendance         → Workers
    Sales              → CRM, Inventory, Billing
    Billing            → Sales
    Subscription       → Payments
    Payments           → Billing, Subscription

  Layer 3 (depend on Layer 2):
    Super Admin        → all
    Reporting          → all
    Customer Portal    → CRM, Sales, Billing

  Layer 4 (depend on Layer 3):
    AI Supervisor      → all
    Factory Intelligence → all
    RAG                → AI Brain, AI Supervisor
    Voice Agent        → AI Brain, AI Supervisor
    LMS                → SaaS ERP, Workers

  Critical path for next 6 months:
    SaaS ERP → Security → Multi-Tenancy → Inventory
      → Production → AI Supervisor
                  ↓
            Cost Intelligence

  Critical path for Universal AI Supervisor (Phase D):
    AI Brain → RAG → AI Supervisor → Voice Agent
                                    → Predictive

================================================================
CRITICAL / STRATEGIC / FUTURE
================================================================

  Critical (must be Production+ by Month 3):
    SaaS ERP, Security, Multi-Tenancy, Inventory, Production,
    Workers, Attendance, Sales, Billing, Payments,
    Subscription

  Strategic (must be 60%+ by Month 6):
    AI Supervisor, AI Brain, CRM, Super Admin, Reporting,
    Factory Intelligence

  Future (planning only, no build in 6 months):
    Voice Agent, LMS, RAG, Customer Portal (V2),
    Automation (polish)

  Anti-patterns to avoid:
    - Building Voice Agent or LMS before AI Supervisor V1
      is in production.
    - Building Customer Portal before Customer Intelligence
      is in.
    - Building RAG before AI Brain has prompt versioning
      + eval.
    - Building LMS in any phase.
    - Treating Storefront as a Customer Portal (it is not;
      it is marketing).

================================================================
END OF AREAS.md
================================================================

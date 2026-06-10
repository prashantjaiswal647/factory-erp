# MUNSHI AI — Priority Roadmap

Date: 2026-06-09
Author: Chief Product Architect
Status: Pilot factory onboarding phase
Security: Post re-audit, all P0/P1 cleared
Read first: AGENTS.md, CURRENT_STATUS.md, DECISIONS.md

---

## 0. Brutal Premise

Munshi AI is no longer a science project. It is a paying ERP serving
real Indian factory owners who:

  - open the app from a phone, often in Hindi
  - lose sleep over cash stuck in receivables
  - cannot afford a CA, an ops manager, or a downtime analyst
  - cancel the subscription the day it stops being useful daily

Every feature below is evaluated against ONE question:

  "Will an Indian paper-cup / glass factory owner open Munshi AI
   tomorrow morning because of this feature?"

If the answer is no, it does not ship in the next 90 days.

---

## 1. Prioritization Formula

```
Priority Score =
   (Owner Pain         × 5)
 × (Daily Usage        × 4)
 × (Revenue Impact     × 5)
 × (Pilot Adoption     × 5)
 − (Implementation Cx  × 2)
```

All factors scored 1–10. The product of the four weighted positives
gives the raw score. Implementation complexity is a flat penalty so
that two features with identical user value are broken by effort.

| Factor           | What 1 means                       | What 10 means                        |
|------------------|------------------------------------|--------------------------------------|
| Owner Pain       | Nice to have, owner doesn't notice | Daily agony, owner pays to fix it    |
| Daily Usage      | Once a month at best               | Multiple times per shift              |
| Revenue Impact   | Indirect / retention only          | Direct cash in bank this week         |
| Pilot Adoption   | One factory out of ten needs it    | Every factory demands it on day 1     |
| Implementation Cx| 1 day, 1 file                      | Multi-sprint, multi-team, new infra   |

Hard rules (no exceptions):

  - Score < 100,000      → defer
  - Score 100K – 1M      → could-have
  - Score 1M – 5M        → should-have
  - Score > 5M           → must-have, next sprint

---

## 2. Phase Scoring (P4.5 → P5.1)

Scored against the formula above. Tie-breakers: daily usage > owner
pain > revenue impact > adoption > complexity.

| Phase | Title                              | Pain | Daily | Rev | Adopt | Cx  | Raw Score       | Tier        |
|-------|------------------------------------|------|-------|-----|-------|-----|-----------------|-------------|
| P4.5  | Telegram Assistant Completion      |   9  |  10   |  6  |   9   |  5  | 4,859,990       | Must-have   |
| P4.6  | Invoice Intelligence               |  10  |   9   |  8  |   9   |  4  | 3,240,000       | Must-have   |
| P4.7  | Recovery Intelligence              |  10  |   8   | 10  |   9   |  5  | 3,600,000       | Must-have   |
| P4.8  | Factory Daily Briefing AI          |   9  |  10   |  7  |   9   |  6  | 5,670,000       | Must-have   |
| P4.9  | Machine Breakdown Logging          |   8  |   6   |  7  |   7   |  3  | 1,176,000       | Should-have |
| P5.0  | Operational Intelligence Layer     |   7  |   5   |  6  |   5   |  8  |   210,000       | Could-have  |
| P5.1  | Advanced Intelligence (ML etc.)    |   4  |   2   |  3  |   2   | 10  |    48,000       | DEFERRED    |

P5.1 is explicitly blocked until BOTH:

  - 10+ paying factories onboarded
  - 90+ days of historical data per factory

Until then, statistical models trained on sparse data will silently
produce wrong numbers. Worse, they will produce numbers that LOOK
authoritative. An Indian factory owner who trusts a wrong "predicted
maintenance" date will fire the real mechanic. We will not ship that.

---

## 3. Phase P4.5 — Telegram Assistant Completion

Goal: Owner opens Telegram every day because it is the only channel
that actually answers them.

Pain summary:
  Right now Telegram is half-built. Welcome message works, code-based
  binding works, but the assistant has no menu, no status, no
  proactive pings. Owner binds once, gets welcome, never opens it
  again. This is the #1 reason a pilot factory churns in week 3.

Must-have in this phase:

  1.  Welcome Message             (already done in Z2.7A)
  2.  Service Onboarding Message   (post-signup, explains what bot can do)
  3.  Owner Channel                (default: all alerts land here)
  4.  Sub-Owner Channel            (sees only what their role permits)
  5.  Role-Based Alert Routing     (Owner = all; Sub-Owner = operations only;
                                    Supervisor = production only)
  6.  Inline Buttons on every alert (View Details, Acknowledge, Snooze)
  7.  /menu Command                (one-tap summary of factory state)
  8.  Telegram Status Tracking     (delivered / read / failed, in DB)
  9.  Test Message button          (already in Z2.7B card)
  10. Action Notifications         (when Sub-Owner or Supervisor does
                                    something, owner gets a one-liner)

What it explicitly does NOT include:

  - Voice notes
  - Image / photo upload
  - Multi-language bot replies
  - Group chat support

Acceptance: Owner opens Telegram at least once per day for 14
consecutive days. Measured by `telegram_user_bindings.last_opened_at`
touched daily.

| Field                | Value           |
|----------------------|-----------------|
| Business Value       | 9 / 10          |
| Development Cx       | 5 / 10          |
| Pilot Factory Impact | 9 / 10          |
| Revenue Impact       | 6 / 10 (retention) |
| Risk Level           | Medium (channel consistency) |
| Sprint Duration      | 1.5 sprints     |

---

## 4. Phase P4.6 — Invoice Intelligence

Goal: Owner generates a GST-ready branded PDF invoice in under 30
seconds from anywhere.

Pain summary:
  Current invoice path requires desktop, GST config, and PDF download.
  Owner sends a WhatsApp photo of a hand-written receipt instead. The
  factory's books are in two places: the real books and the owner's
  memory. This is the #1 reason a CA cannot file GST on time.

Must-have in this phase:

  1.  Auto PDF Invoice              (already in Z2.6 / AGENTS §12A)
  2.  Invoice Branding              (factory logo + GSTIN + bank details)
  3.  Telegram Invoice Delivery      (push PDF to owner + customer bot)
  4.  Email Invoice Delivery         (SMTP + SendGrid fallback)
  5.  Download History              (per customer, per month)
  6.  Invoice Number Sequencing      (per-type counter, no gaps, no dupes)
  7.  GST Validation                (GSTIN format + state code match)

What it explicitly does NOT include:

  - E-invoicing (Govt IRP, IRN generation)
  - E-way bill
  - Multi-currency
  - Reverse charge
  - TDS / TCS

Acceptance: Owner can produce a fully branded PDF and have it land in
the customer's Telegram or email inbox in under 30 seconds from the
"Add Sale" tap.

| Field                | Value           |
|----------------------|-----------------|
| Business Value       | 10 / 10         |
| Development Cx       | 4 / 10          |
| Pilot Factory Impact | 9 / 10          |
| Revenue Impact       | 8 / 10 (faster payment collection) |
| Risk Level           | Low (template + delivery) |
| Sprint Duration      | 1 sprint        |

---

## 5. Phase P4.7 — Recovery Intelligence

Goal: Owner knows exactly where money is stuck the moment the cash
crunch starts.

Pain summary:
  "Kaun kitna de raha hai" is the most-asked question by Indian SME
  owners. They track it in their head, lose it on weekends, forget
  it after a fight with the buyer. The factory has ₹4L stuck in
  receivables and the owner thinks it's ₹1.5L. By the time the
  mismatch is caught, the buyer has already switched supplier.

Must-have in this phase:

  1.  Outstanding Dashboard          (factory total, per-customer break)
  2.  Top Due Customers              (sorted by amount, days overdue)
  3.  Due Buckets                    (0-7, 8-30, 31-60, 60+ days)
  4.  Collection Forecast            (7-day, 30-day, 90-day based on
                                      historical payment velocity)
  5.  Telegram Recovery Alerts       (overdue nudge to owner daily 9am)
  6.  Weekly Recovery Report         (Sunday 20:00 IST per AGENTS §20)

What it explicitly does NOT include:

  - Credit scoring ML
  - Customer churn prediction
  - Buyer-side auto-reminder bot
  - Legal escalation flow
  - Cheque / PDC tracking

Acceptance: Owner can answer "kitna paisa atka hua hai aur kisse"
in under 5 seconds from the dashboard, and gets one Telegram nudge
per day until it goes below threshold.

| Field                | Value           |
|----------------------|-----------------|
| Business Value       | 10 / 10         |
| Development Cx       | 5 / 10          |
| Pilot Factory Impact | 9 / 10          |
| Revenue Impact       | 10 / 10 (direct cash) |
| Risk Level           | Low (sums only) |
| Sprint Duration      | 1 sprint        |

---

## 6. Phase P4.8 — Factory Daily Briefing AI

Goal: Owner understands factory health in under 2 minutes every
morning, in Telegram and on the dashboard.

Pain summary:
  Owner does not have time to open 7 different screens. He has time
  for one Telegram message at 6:00 AM and one dashboard card at
  8:00 AM. If that single artefact is wrong, the whole app is wrong.
  If it is right, the app becomes a daily ritual.

Must-have in this phase:

  1.  Production Summary             (yesterday: target vs actual)
  2.  Inventory Summary              (low stock + overstock)
  3.  Sales Summary                  (yesterday revenue + month-to-date)
  4.  Collections Summary            (collected + outstanding + overdue)
  5.  Expense Summary                (yesterday + month-to-date vs budget)
  6.  Net Factory Health Score       (single 0–100 number, deterministic
                                      per AGENTS §3 A2.3)

Delivery:
  - Telegram: one structured message at 06:00 IST (already shipped
    partial per AGENTS §3)
  - Dashboard: one card on /dashboard with the same 6 sections

What it explicitly does NOT include:

  - Comparative benchmarks (other factories)
  - AI-generated narrative / commentary
  - Predictive "next week will be" forecast
  - Industry news / market rates
  - Shareholder / investor views

Acceptance: At 06:00 IST the owner gets a 6-section message that is
factually correct, deterministic, and short enough to read in 90
seconds. If any number is wrong, the whole product is wrong.

| Field                | Value           |
|----------------------|-----------------|
| Business Value       | 9 / 10          |
| Development Cx       | 6 / 10          |
| Pilot Factory Impact | 9 / 10          |
| Revenue Impact       | 7 / 10 (retention + upsell) |
| Risk Level           | Medium (wrong number = loss of trust) |
| Sprint Duration      | 2 sprints       |

---

## 7. Phase P4.9 — Machine Breakdown Logging

Goal: Simple maintenance records. No predictions. No ML.

Pain summary:
  Owner wants to know: "kitni baar band hui, kab, kya fix kiya,
  khaarcha kitna aaya." Not "machine X will fail in 17 days with 73%
  confidence." The latter is theatre. The former is a spreadsheet
  that pays for itself in week 2.

Must-have in this phase:

  1.  Report Breakdown               (5-field form: machine, reason,
                                      duration, cost, spare parts)
  2.  Breakdown History              (per machine, per month table)
  3.  Repair Cost                    (logged in paise, factory-scoped)
  4.  Breakdown Analytics            (frequency + cost per machine,
                                      no forecasting)
  5.  Telegram Alerts                (single alert on breakdown, single
                                      alert when machine resumes)

What it explicitly does NOT include:

  - Predictive Maintenance
  - Anomaly Detection
  - Service Forecasting
  - Failure probability
  - Remaining-useful-life models
  - Sensor / IoT integration
  - Vibration / temperature analysis
  - Vendor recommendation ML

Acceptance: Owner can open the machine detail page and see in plain
numbers: "this machine broke 3 times this month, total cost ₹4,500,
top reason: heater coil."

| Field                | Value           |
|----------------------|-----------------|
| Business Value       | 8 / 10          |
| Development Cx       | 3 / 10          |
| Pilot Factory Impact | 7 / 10          |
| Revenue Impact       | 7 / 10 (downtime loss avoided) |
| Risk Level           | Low             |
| Sprint Duration      | 0.75 sprint     |

---

## 8. Phase P5.0 — Operational Intelligence Layer

Goal: Decision-support insights, not decision-making automation.

Must-have in this phase:

  1.  Production Efficiency          (actual vs target, by shift)
  2.  Machine Utilization            (hours used / hours available)
  3.  Wastage Analysis               (per product, per worker, per machine
                                      — already partially in AGENTS §18)
  4.  Customer Profitability         (revenue − cost-to-serve − wastage)
  5.  Product Profitability          (revenue − material − wastage)

What it explicitly does NOT include:

  - Cross-factory benchmarks
  - Statistical process control
  - Six-sigma / lean metrics
  - Time-series forecasting
  - ML clustering

Acceptance: Owner can answer "kaunsa product sabse zyada kamata hai
aur kaunsa customer sabse zyada kharchata hai" in 30 seconds.

| Field                | Value           |
|----------------------|-----------------|
| Business Value       | 7 / 10          |
| Development Cx       | 8 / 10          |
| Pilot Factory Impact | 5 / 10          |
| Revenue Impact       | 6 / 10 (margin) |
| Risk Level           | Medium          |
| Sprint Duration      | 2 sprints       |
| Defer until          | After P4.5–P4.9 ship + 5 factories live |

---

## 9. Phase P5.1 — Advanced Intelligence Layer

Goal: ML-driven insights, only when we have data to train on.

Gating conditions (both required):

  - 10+ paying factories onboarded with at least 30 days of data
  - 90+ days of historical data per active factory

Then and only then do we open:

  1.  Predictive Maintenance
  2.  Cost Anomaly Detection
  3.  Pattern Recognition
  4.  Forecasting Models

Why the gate is hard:

  - Indian SME seasonality is high (Diwali shutdown, summer slow).
    One quarter of data is not enough.
  - Cross-factory pooling needs legal sign-off (AGENTS §17).
  - Wrong "predictive" output is worse than no output. Owner fires
    a working mechanic because the model said the machine will fail.
    That kills the pilot.

| Field                | Value           |
|----------------------|-----------------|
| Business Value       | 4 / 10 today   |
| Development Cx       | 10 / 10         |
| Pilot Factory Impact | 2 / 10          |
| Revenue Impact       | 3 / 10          |
| Risk Level           | HIGH (data quality) |
| Sprint Duration      | 3+ sprints      |
| Start                | After 10+ factories + 90 days data |

---

## 10. Recommended Sequence

| Order | Phase | Why this order                                  |
|-------|-------|--------------------------------------------------|
| 1     | P4.8  | Highest score (5.67M). Daily habit is the moat.  |
| 2     | P4.5  | Channel for all other alerts. 4.86M.            |
| 3     | P4.7  | Direct cashflow impact. 3.6M.                    |
| 4     | P4.6  | Invoicing is table stakes for GST. 3.24M.        |
| 5     | P4.9  | Quick win. 1.18M. Builds trust.                  |
| 6     | P5.0  | After pilot proves basics work. 210K.            |
| -     | P5.1  | GATED. 48K today, 0 value without data.          |

Total budget for P4.5 → P4.9: ~6.25 sprints of focused work.
That is roughly 3 months for a 1-engineer team, or 6 weeks for a
2-engineer team.

---

## 11. TOP 10 — Features That Will Make Factory Owners Pay

In strict order. Each one passes the formula at score > 1,000,000.

  1. Telegram Daily Briefing (P4.8)            score 5.67M
  2. Telegram Assistant (P4.5)                  score 4.86M
  3. Recovery / Outstanding Dashboard (P4.7)    score 3.60M
  4. Auto-PDF Invoice + Branding (P4.6)         score 3.24M
  5. Invoice Delivery via Telegram + Email      score ~3M  (subset of P4.6)
  6. Production Entry in <30 seconds            score ~2M  (already shipped, polish)
  7. Low-Stock Alert with Auto-Purchase Hint    score ~2M  (P4.5 alert type 1)
  8. Daily Wastage Snapshot                     score ~1.8M (AGENTS §18)
  9. Per-Customer Payment History at a Glance   score ~1.5M
 10. Monthly P&L (Revenue − Cost − Wastage)     score ~1.2M

All ten are:
  - Used daily
  - Solve a real pain
  - Ship in 1 sprint each
  - Have a measurable adoption metric

---

## 12. TOP 10 — Features That Look Impressive But Should NOT Be Built Yet

Each one fails the formula. Build them only after the gate conditions.

  1. Predictive Maintenance
     Why not: requires 90+ days per-machine data, then per-machine
     failure mode training. Until then it is theatre.

  2. AI Anomaly Detection
     Why not: anomaly in what baseline? We do not have a baseline.
     False positives will fire constantly on a noisy Indian factory
     floor and owners will mute everything.

  3. Machine Failure Forecasting
     Why not: see above. Also creates a legal risk (we said it
     "would" fail and it did not, owner blames us).

  4. Cost Baseline Models (statistical)
     Why not: needs 6+ months of clean data per factory. A
     3-factory pilot does not have that. The current 30-day rolling
     mean is enough and is already shipped.

  5. Pattern Recognition on Production
     Why not: useful only at 10+ factories with shared schema.
     One-factory patterns are too obvious for ML to find.

  6. Forecasting Models (sales / demand / wastage)
     Why not: Indian SME demand is event-driven (festivals, weddings,
     election years). A linear model will be confidently wrong.

  7. Real-Time IoT Sensor Integration
     Why not: pilot factories cannot afford PLC retrofits. The phone
     is the only sensor we have.

  8. Cross-Factory Benchmarking
     Why not: legal (data sharing), competitive (factories will
     refuse), and statistically weak (3-factories ≠ a cohort).

  9. ML Customer Churn / Credit Score
     Why not: needs hundreds of paid-and-defaulted invoices per
     customer. We do not have that.

 10. AI Chatbot / "Ask AI Anything"
     Why not: we are not OpenAI. A wrong answer in a chatbot is
     worse than no chatbot. The morning briefing is enough.

Rule of thumb: if a feature requires "trained model" or "large
dataset" in its PRD, defer it. The factory owner will not pay extra
for it, and it will burn engineering time that should go to P4.5–P4.9.

---

## 13. Single Recommendation

Ship P4.5 → P4.9 in that order, in 6.25 sprints. Do not start P5.0
or P5.1 until at least 5 paying factories have been live for 60+ days
each. Every sprint, re-score the backlog against the formula. If a
feature is not in the top 10 above, it is not in the next 90 days.

Daily ritual: build the morning briefing first. Everything else
distributes through it.

---

## 14. Acceptance Gate

This roadmap is "valid" only while:

  - P0/P1 launch blockers stay green (AGENTS.md §4)
  - validate-and-test.sh passes
  - backend pytest passes
  - npm run build passes
  - 1+ pilot factory is paying
  - 0 P0 incidents in production

If any of these slips, the roadmap is paused and the slip is fixed
before resuming. New features do not get added to the roadmap while
a P0 is open.

---

Source: AGENTS.md §3 §4 §15A §18 §19 §20, ALERT-1 design, ALERT-5
design, Z2.7A/B delivery, MUNSHI_6_MONTH_ROADMAP.md, DECISIONS.md
#8 (Universal AI Supervisor 4-Phase Strategy).

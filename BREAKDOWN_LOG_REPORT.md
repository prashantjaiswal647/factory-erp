# MUNSHI AI — Sprint P4.9: Machine Breakdown Logging Report

Date: 2026-06-09
Author: Chief Product Architect
Sprint Priority Score: 1,176,000 (Should-have, rank #5)
Source roadmap: MUNSHI_AI_PRIORITY_ROADMAP.md §7

---

## 0. Brutal Premise

This sprint exists to answer four questions in plain numbers:

  1. Kaunsi machine fail hui?   (which machine)
  2. Kab?                        (when)
  3. Kyun?                       (why)
  4. Repair cost kitna aaya?     (how much)

That is the entire product spec for P4.9. Anything that does not serve
those four questions does not ship in this sprint.

Explicit non-goals (per spec, locked):

  - Predictive maintenance
  - AI forecasting
  - Cost anomaly detection
  - Machine learning models
  - Statistical analysis (no median, no baseline, no percentile,
    no z-score, no standard deviation, no correlation)

Why: pilot factories have fewer than 90 days of clean data per
machine. The audit's "Operational Intelligence Layer" (P5.0) and
"Advanced Intelligence Layer" (P5.1) are gated on 10+ factories and
90+ days of data. Building the maths on a 1-factory 30-day dataset
will produce confident-looking wrong numbers. We will not ship that.

---

## 1. Spec Item Status (5 of 5)

| # | Spec item          | Status   | Evidence                                            |
|---|--------------------|----------|-----------------------------------------------------|
| 1 | Report Breakdown   | PARTIAL  | POST /api/operations/breakdown exists; no downtime_start/end, no cost |
| 2 | Breakdown Reason   | PARTIAL  | issue_category is free text; no enum                |
| 3 | Repair Cost        | NEW      | no field on existing path; not stored anywhere      |
| 4 | Breakdown History  | NEW      | no GET endpoint; would require scanning ActivityLog text |
| 5 | Telegram Alerts    | NEW      | not wired; breakdown is silent in Telegram          |

Net: 0 fully DONE, 2 PARTIAL, 3 NEW. Real build work is required.

---

## 2. Already Shipped (and what to keep)

File: apps/api/routers/operations.py:1085-1123

```python
@router.post("/operations/breakdown", status_code=status.HTTP_201_CREATED)
def report_machine_breakdown(payload: MachineBreakdownCreate, ...):
    machine = db.query(Machine).filter(Machine.id == payload.machine_id,
                                       Machine.factory_id == factory_id).first()
    desc = f"Machine Breakdown: {machine_label} - {payload.issue_category}"
    if payload.custom_notes: desc += f". Notes: {payload.custom_notes}"
    activity = ActivityLog(event_type="machine_telemetry", description=desc)
    db.add(activity); db.commit()
    return _activity_to_dict(activity)
```

What is good and stays:

  - The endpoint exists at /api/operations/breakdown and is reachable
    from the production page (per ALERT-1 UI plan).
  - Permission is correct: Owner + Sub-Owner + Supervisor can report
    (the operator on the floor must be able to log it).
  - Factory isolation is enforced via `machine.factory_id == factory_id`.
  - The ActivityLog write is preserved as a "daily sequence" view.

What changes:

  - The endpoint body extends to the new schema (cost, start/end,
    worker, spare parts).
  - The endpoint also writes a structured MachineDowntime row.
  - The endpoint fires a Telegram alert to the Owner.
  - The ActivityLog description stays short ("Machine breakdown: {label}")
    and points to the MachineDowntime row for the full detail.

---

## 3. Data Model (one new table)

### 3.1 Table: machine_downtimes

```
id                          BIGINT PK
factory_id                  BIGINT FK + indexed
machine_id                  BIGINT FK machines.id + indexed
reporter_user_id            BIGINT FK users.id (who logged it)
downtime_start              TIMESTAMPTZ  NOT NULL
downtime_end                TIMESTAMPTZ  NULL     (NULL = still down)
duration_minutes            INTEGER      GENERATED ALWAYS AS
                              (CASE WHEN downtime_end IS NULL
                                    THEN NULL
                                    ELSE EXTRACT(EPOCH FROM (downtime_end - downtime_start))/60
                              END) STORED
reason_category             VARCHAR(40)  NOT NULL
                              values: MECHANICAL, ELECTRICAL, TOOLING,
                                      MATERIAL, OPERATOR_ERROR, POWER,
                                      SCHEDULED_MAINTENANCE, OTHER
reason_notes                TEXT         NULL
spare_parts_used            JSONB        default '[]'
                              shape: [{"part_name": str, "qty": num,
                                       "unit_cost_paise": int}, ...]
repair_cost_paise           BIGINT       default 0
work_impact_boxes_missed    INTEGER      NULL    (optional operator estimate)
created_at                  TIMESTAMPTZ  default now()
updated_at                  TIMESTAMPTZ  default now() on update now()

Indexes:
  ix_machine_downtimes_factory_machine_start
    (factory_id, machine_id, downtime_start DESC)
  ix_machine_downtimes_factory_start
    (factory_id, downtime_start DESC)
  ix_machine_downtimes_factory_machine_open
    (factory_id, machine_id) WHERE downtime_end IS NULL
    -- partial index for "currently down" queries
```

All money in paise (BIGINT). Per AGENTS §15A factory-scoped via
TenantMixin. No destructive columns. No backfill needed (table is new).

### 3.2 Why a new table, not ActivityLog

The audit's #4 P1 item ("Excel validation report UI incomplete") and
the broader AGENTS §3 "data flow must be traceable" both want
structured data for analytics. Storing breakdowns in
ActivityLog.description as free text would make "which machine
failed most" a full table scan with regex. With MachineDowntime:

  - SUM(repair_cost_paise) GROUP BY machine_id -> a real query
  - ORDER BY count(*) DESC LIMIT 5 -> top 5 offenders
  - ORDER BY downtime_start DESC LIMIT 20 -> recent history

No regex. No string parsing. Pure SQL.

### 3.3 Why no enum at the application level

We keep reason_category as a string with a CHECK constraint, not a
Postgres ENUM. Reason: enum migrations are painful (ALTER TYPE
ADD VALUE needs its own migration and cannot run inside a
transaction). A VARCHAR + CHECK is easier to evolve when a new
reason shows up in pilot data.

---

## 4. Pydantic Schemas

File: apps/api/schemas.py (additive; do not break existing schemas)

```python
class SparePartPayload(BaseModel):
    part_name: str = Field(..., min_length=1, max_length=100)
    qty: Decimal = Field(..., gt=0)
    unit_cost_paise: int = Field(..., ge=0)

class MachineDowntimeCreate(BaseModel):
    machine_id: int
    downtime_start: datetime
    downtime_end: Optional[datetime] = None
    reason_category: Literal[
        "MECHANICAL", "ELECTRICAL", "TOOLING", "MATERIAL",
        "OPERATOR_ERROR", "POWER", "SCHEDULED_MAINTENANCE", "OTHER",
    ]
    reason_notes: Optional[str] = Field(default=None, max_length=2000)
    spare_parts_used: list[SparePartPayload] = Field(default_factory=list)
    repair_cost_rupees: Optional[Decimal] = Field(default=None, ge=0)
    work_impact_boxes_missed: Optional[int] = Field(default=None, ge=0)

class MachineDowntimeUpdate(BaseModel):
    downtime_end: Optional[datetime] = None
    reason_notes: Optional[str] = None
    spare_parts_used: Optional[list[SparePartPayload]] = None
    repair_cost_rupees: Optional[Decimal] = None
    work_impact_boxes_missed: Optional[int] = None

class MachineDowntimeResponse(BaseModel):
    id: int
    machine_id: int
    machine_name: str
    machine_number: Optional[str]
    reporter_user_id: int
    reporter_full_name: str
    downtime_start: datetime
    downtime_end: Optional[datetime]
    duration_minutes: Optional[int]
    reason_category: str
    reason_label: str          # Hinglish display name
    reason_notes: Optional[str]
    spare_parts_used: list[dict]
    repair_cost_paise: int
    repair_cost_rupees: Decimal
    work_impact_boxes_missed: Optional[int]
    created_at: datetime

class MachineDowntimeHistoryResponse(BaseModel):
    items: list[MachineDowntimeResponse]
    total: int
    total_repair_cost_paise: int
    total_downtime_minutes: int
    by_reason: dict[str, int]   # count per reason_category
```

The `reason_label` field is the Hinglish display name looked up from
a hard-coded dict in services/machine_reason_labels.py. No
translation table, no DB lookup. Eight entries. Trivial.

---

## 5. Router (apps/api/routers/machine_breakdown.py — NEW)

All routes factory-scoped via check_permissions. Sub-Owner + Supervisor
can POST (they are the ones on the floor). All three Owner / Sub-Owner
/ Supervisor can GET.

```
POST   /api/operations/breakdown
       body: MachineDowntimeCreate
       permission: Owner, Sub-Owner, Supervisor
       201 -> MachineDowntimeResponse
       404 -> unknown machine_id or wrong factory
       side-effects:
         - INSERT machine_downtimes row
         - INSERT ActivityLog row (event_type="machine_breakdown")
         - background: send_telegram_alert to Owner (best-effort)

GET    /api/machines/{machine_id}/breakdowns
       query: ?from=YYYY-MM-DD&to=YYYY-MM-DD&limit=50
       permission: Owner, Sub-Owner, Supervisor
       200 -> MachineDowntimeHistoryResponse
       Use case: per-machine history view

GET    /api/operations/breakdowns
       query: ?from=&to=&machine_id=&reason_category=
       permission: Owner, Sub-Owner, Supervisor
       200 -> MachineDowntimeHistoryResponse
       Use case: factory-wide history view + filters

PATCH  /api/operations/breakdown/{breakdown_id}
       body: MachineDowntimeUpdate
       permission: Owner, Sub-Owner (Supervisor can only patch their own)
       200 -> MachineDowntimeResponse
       Use case: close a still-open breakdown, add cost after the fact
```

### 5.1 Telegram alert side-effect

In the POST handler, after the row is committed, fire:

```python
try:
    send_machine_breakdown_alert(factory, machine, downtime_row, reporter)
except Exception as exc:
    logger.warning("breakdown alert failed", exc_info=exc, extra={
        "factory_id": factory.id, "machine_id": machine.id,
    })
```

`send_machine_breakdown_alert` lives in
`apps/api/services/telegram_alert_templates.py` (already designed in
P4.5 / ALERT-5). One message, Owner only, deterministic Hinglish:

  "🔧 Machine {machine_name} ({number}) breakdown.
   Reason: {reason_label}.
   Duration so far: {duration_min} min
   {is_open ? "(abhi tak theek nahi hua)" : "(resolved)"}.
   Reporter: {reporter_name}."

NO second message when cost is added. NO follow-up if the same
machine breaks again the same day. NO "this is the 3rd breakdown
this week" callout. The alert is purely a 1-liner of "this just
happened, who logged it, why." Anything beyond that is the user's
explicit "do not build" list.

If a Sub-Owner reports a breakdown, the alert goes to the Owner
(per AGENTS §15A: Sub-Owner -> Owner best-effort). If a Supervisor
reports, the alert also goes to the Owner. Operator cannot report
breakdowns through this endpoint (kept simple; operator is not a
role we onboard for pilot).

### 5.2 Cost handling

`repair_cost_rupees` arrives as a Decimal. Convert to paise on write:

```python
paise = int((payload.repair_cost_rupees or Decimal("0")) * 100)
```

Stored as BIGINT. Returned as Decimal for UI by dividing by 100.
This matches the cost_per_cup_daily pattern already in models.py.

---

## 6. Why the existing /operations/breakdown endpoint is not the only entry point

We extend it, we do not duplicate. The existing path:

  - Lives in operations.py
  - Reachable from the production page UI
  - Already factory-isolated
  - Already permission-gated

We modify `MachineBreakdownCreate` in operations.py to import from
schemas.py so the same schema is reused. The router function is
updated to also write the machine_downtimes row and fire the
Telegram alert. We do NOT add a new POST endpoint at
/api/machines/{id}/breakdown — that would split the entry point
and confuse the UI. One POST, two writes (ActivityLog + structured
table), one side-effect (Telegram).

---

## 7. UI Changes (3 small pieces)

File 1: apps/web/src/pages/ProductionPage.tsx
  Add [Report Breakdown] button next to the existing [+ Production]
  button. Modal with 6 fields:
    - machine (select)
    - downtime start (datetime, default = now)
    - downtime end (datetime, optional = still down)
    - reason category (select from 8 enum values)
    - reason notes (textarea, optional)
    - repair cost (number, rupees, optional)
    - work impact: boxes missed (number, optional)
    - spare parts used (dynamic list, optional)
  Submit: POST /api/operations/breakdown
  Success toast: "Breakdown logged. Owner ko alert chala gaya."

File 2: apps/web/src/pages/MachineDetailPage.tsx (NEW)
  Route: /machines/:machineId
  Sections (in this order, no extras):
    - Header (name, number, mould size)
    - Status: "Currently down" badge if any open downtime
    - Stats row:
        Total breakdowns (all time)
        Total repair cost (₹)
        Total downtime (hours)
        Top reason
    - Recent breakdowns table (last 20)
    - [Report Breakdown] button (same modal as Production page)
  No charts. No trend lines. No "this machine is X% worse than last
  month" callout. The audit's P1.6 listener drift is separate work;
  do not conflate.

File 3: apps/web/src/components/Layout.tsx (or Sidebar)
  Add sidebar entry: "Machines" -> /machines (new list page)
  Each row shows: name, number, total breakdowns, last breakdown
  date, currently down badge if any.
  No ML. No "predict failure" warnings. Just a table.

File 4: apps/web/src/lib/api.ts
  New helpers:
    reportMachineBreakdown(payload)
    listMachineBreakdowns(machineId, params)
    listFactoryBreakdowns(params)
    patchMachineBreakdown(breakdownId, payload)

---

## 8. Tests (apps/api/tests/test_p4_9_machine_breakdowns.py)

Test cases (in order):

  test_report_breakdown_creates_machine_downtime_row
    POST /api/operations/breakdown with full body
    assert: 201
    assert: machine_downtimes row exists with correct fields
    assert: ActivityLog row exists with event_type="machine_breakdown"
    assert: paise conversion is correct (rupees * 100)

  test_report_breakdown_optional_fields_default
    POST with only machine_id + reason_category + downtime_start
    assert: 201
    assert: repair_cost_paise = 0
    assert: spare_parts_used = []
    assert: downtime_end is NULL (still open)

  test_report_breakdown_with_spare_parts
    POST with 2 spare parts
    assert: spare_parts_used JSONB has both with correct qty +
            unit_cost_paise

  test_breakdown_history_per_machine
    POST 3 breakdowns on machine A, 1 on machine B
    GET /api/machines/A/breakdowns -> 3 items, newest first
    GET /api/machines/B/breakdowns -> 1 item

  test_breakdown_history_factory_wide
    GET /api/operations/breakdowns
    assert: total = 4
    assert: total_repair_cost_paise = sum of all
    assert: total_downtime_minutes = sum of all (only closed ones)
    assert: by_reason = {"MECHANICAL": 2, "ELECTRICAL": 2}

  test_factory_isolation
    factory A posts 2 breakdowns
    factory B user GET /api/operations/breakdowns -> 0 items
    factory A user GET same -> 2 items

  test_unknown_machine_returns_404
    POST with machine_id that does not exist in this factory
    assert: 404

  test_close_open_breakdown_via_patch
    POST breakdown with downtime_end = null
    PATCH with downtime_end = now
    assert: duration_minutes computed correctly (within 1 min)

  test_supervisor_can_report_breakdown
    Supervisor-role user POSTs
    assert: 201, row exists with reporter_user_id = supervisor

  test_owner_receives_telegram_alert
    Sub-Owner reports a breakdown
    captured send_telegram_message called with text containing
    machine_name, reason_label, reporter name, and the word "breakdown"

  test_owner_does_not_get_alert_when_owner_reports
    Owner reports a breakdown
    assert: NO Telegram send (own actions do not alert)
    assert: breakdown row still written

  test_telegram_alert_does_not_breakdown_write
    monkeypatch send_machine_breakdown_alert -> raise
    POST /api/operations/breakdown
    assert: 201
    assert: machine_downtimes row exists (alert failure is best-effort)

  test_reason_category_validation
    POST with reason_category="GUESSING"
    assert: 422 Pydantic validation error

  test_negative_repair_cost_rejected
    POST with repair_cost_rupees = -10
    assert: 422

  test_open_breakdown_query
    POST 3 breakdowns, only 1 has downtime_end=null
    GET /api/operations/breakdowns?from=...&to=...&is_open=true
    assert: 1 item

  test_paise_round_trip
    POST with repair_cost_rupees = 1234.50
    assert: stored as 123450 paise
    GET returns Decimal("1234.50")

  test_no_pii_in_telegram_alert
    Owner name, customer name, full customer list must NOT appear
    in the Telegram text. The alert is about the machine only.

  test_no_alert_when_owner_blocked_bot
    binding is_active = False
    Sub-Owner reports a breakdown
    assert: 201, row written, no crash
    assert: send_machine_breakdown_alert returns silently (skips dead)

### 8.1 Regression sweep (must stay green)

  tests/test_telegram_self_service.py          21 cases
  tests/test_p4_5_telegram_completion.py       ~22 cases
  tests/test_pilot_zero_touch_acceptance.py    1 case
  tests/test_finished_goods_sync.py            varies
  tests/test_role_based_telegram_alerts.py     varies

  New test_p4_9_machine_breakdowns.py          ~17 cases

  Total: ~60+ cases. All green = P4.9 done.

---

## 9. Sprint Sequencing (within P4.9)

Day 1 morning — schema + endpoint:
  P4.9.1  Alembic migration 0027_machine_downtimes            0.25d
  P4.9.2  MachineDowntime model in models.py                   0.1d
  P4.9.3  Pydantic schemas in schemas.py                       0.25d
  P4.9.4  services/machine_reason_labels.py (8-entry dict)     0.05d
  P4.9.5  Refactor operations.py breakdown endpoint            0.5d
  P4.9.6  send_machine_breakdown_alert in telegram_alert_templates 0.1d

Day 1 afternoon — query + UI:
  P4.9.7  GET /api/machines/{id}/breakdowns                    0.25d
  P4.9.8  GET /api/operations/breakdowns (with filters)         0.25d
  P4.9.9  PATCH /api/operations/breakdown/{id}                0.25d
  P4.9.10 apps/web/src/lib/api.ts helpers                       0.1d
  P4.9.11 ReportBreakdownModal.tsx (shared component)          0.5d
  P4.9.12 ProductionPage.tsx [Report Breakdown] button         0.1d
  P4.9.13 MachineDetailPage.tsx                                0.5d
  P4.9.14 /machines list page (sidebar entry)                  0.25d

Day 2 morning — tests:
  P4.9.15 test_p4_9_machine_breakdowns.py (~17 cases)          0.5d
  P4.9.16 Regression sweep + validate-and-test.sh              0.5d

Total: 2 days, 1 engineer.

---

## 10. Acceptance Criteria (the 4 owner questions)

P4.9 is DONE only when the owner can answer these in under 10
seconds from the UI, and the answers match the data:

  [ ] Which machine failed?
      GET /api/operations/breakdowns OR /machines list page
      returns the answer within 1 SQL query.

  [ ] When?
      downtime_start + downtime_end columns, rendered as
      "12 Jun 2026, 10:30 — 11:45 (75 min)".

  [ ] Why?
      reason_category enum + reason_notes free text.
      No inference, no LLM, no ML. Owner reads the notes.

  [ ] How much?
      repair_cost_rupees in the response, sum() over time,
      per machine and factory-wide. No baseline, no percentile.

Plus the test gate:
  [ ] 17 new pytest cases pass
  [ ] 0 regressions in self_service + p4_5 + zero_touch + sync
  [ ] alembic upgrade head on disposable DB: clean
  [ ] alembic downgrade -1: clean
  [ ] Manual: Sub-Owner reports a breakdown from a phone,
      Owner phone receives the alert within 5 seconds

---

## 11. What P4.9 Does NOT Do (locked list)

Per the spec, these are out of scope. We re-state them here so the
next sprint author cannot silently expand:

  - NO predictive maintenance
  - NO AI forecasting
  - NO cost anomaly detection
  - NO machine learning models
  - NO statistical analysis (no median, no mean, no baseline,
    no z-score, no percentile, no correlation, no regression,
    no clustering, no time-series decomposition)
  - NO "this machine usually fails every 30 days" callouts
  - NO "your repair cost is 2.3x the median" warnings
  - NO "we recommend you service this machine in 17 days" hints
  - NO "compare to other factories" benchmarks
  - NO integration with PLC / IoT / sensor data
  - NO scheduled service reminders (no auto-create service entry)
  - NO "auto-open work order" workflow
  - NO "auto-quote from vendor" integration
  - NO photo / video upload of the broken machine
  - NO voice notes from the operator
  - NO machine uptime / OEE calculation
  - NO "machine is slower than usual" detection (would need
    production throughput baseline, see P5.0)

All of those are blocked behind the P5.0 / P5.1 gates in the
priority roadmap (10+ factories + 90 days data). The audit's
P1.6 listener-drift work and ALERT-1's "service due in 3 days"
are also out of scope here.

---

## 12. Risk Map

  Risk                                            Mitigation
  ----------------------------------------------  --------------------------------
  Spare parts JSONB schema drift                 Pydantic SparePartPayload
                                                 validates at API boundary
  Paise conversion rounding (rupees * 100)       int() on Decimal, no round
  Cross-factory machine_id collision             Per-request
                                                 machine.factory_id == factory_id
  Telegram alert floods owner                     1 alert per breakdown, no
                                                 follow-ups, no repeats
  Alert failure breaks breakdown write            try/except + log, never
                                                 propagates from POST handler
  Supervisor reports for someone else's machine  Reporter is current_user, no
                                                 spoofing, audit trail honest
  Open breakdown never closed                     PATCH endpoint, UI shows
                                                 "currently down" badge, no
                                                 auto-close
  Old free-text breakdown in ActivityLog          New table is the source of
                                                 truth; old rows are read-
                                                 only history
  Schema change breaks existing test_erp_flows   Migration 0027 is additive
                                                 only, no column renames
                                                 or drops
  Test data pollution across tests               Each test creates a fresh
                                                 factory via clean_db fixture

---

## 13. Pilot vs Enterprise (this sprint)

  Feature                          Pilot (P4.9)         Enterprise
  -------------------------------- -------------------- ----------------------
  Reason taxonomy                  8 fixed enum         per-factory override
  Cost anomaly detection           NONE                 median * 2.5 (P5.1)
  Predictive maintenance           NONE                 ML model (P5.1)
  Spare parts tracking             free-text list       catalog table + cost
  Service interval reminder        NONE                 per-machine interval
  Telegram alert cadence           1 per event          dedup within 1h window
  Breakdown analytics              counts + sums        Pareto + time-series
  Photo upload                     NONE                 S3 + thumbnail
  Voice notes                      NONE                 whisper transcription
  Cross-machine comparison         counts only          full benchmark suite

  P4.9 = Pilot column. Free-text parts, 8 reason buckets, 1 alert
  per event, counts and sums. No maths.

---

## 14. Single Recommendation

Build P4.9 in 2 days, 1 engineer. Three PRs:

  PR 1: model + migration + schemas + reason labels
         (apps/api/models.py, alembic 0027, apps/api/schemas.py,
          apps/api/services/machine_reason_labels.py)
  PR 2: router + telegram alert + activity_log hook
         (apps/api/routers/operations.py refactor,
          apps/api/services/telegram_alert_templates.py add,
          apps/api/services/activity_logger.py hook)
  PR 3: frontend + tests
         (apps/web/src/lib/api.ts, ReportBreakdownModal.tsx,
          ProductionPage.tsx, MachineDetailPage.tsx, /machines
          page, sidebar entry, test_p4_9_machine_breakdowns.py)

After P4.9 ships, the owner can answer the four questions. The
five must-have items are met. The five "do not build" items stay
unbuilt until the P5.1 gate is opened (10+ factories + 90 days).

---

Source: apps/api/routers/operations.py:1085, apps/api/models.py:306
(Canonical Machine), AGENTS.md §3 §9 §15 §15A, MUNSHI_AI_PRIORITY_
ROADMAP.md §7, P4.5 report, ALERT-5 template design.

# Munshi AI Telegram Configuration Audit

Audit date: 2026-06-15

Scope: Telegram webhooks, menus, callback routing, scheduled delivery, live read services, write services, persistence models, tests, Docker services, and n8n references.

## Executive Summary

Munshi AI has three overlapping Telegram implementations:

1. **Current self-service `/menu` path** in `routers/integrations.py` and `services/telegram_onboarding.py`.
   - Four top-level buttons: Dekho, Kaam Karo, Alerts, Settings.
   - All eight Dekho buttons query live, factory-scoped database data.
   - All six Kaam Karo buttons are placeholders and do not write business data.
   - Alerts and Settings are navigation placeholders.

2. **Legacy action callback path** at `POST /api/v1/telegram/action`.
   - Uses `A*`, `W*`, and `R*` callback names.
   - Contains real guided write flows for production, attendance, shift wastage, invoice creation, payment allocation, and production editing.
   - It is not connected to the callback names displayed by the current `/menu`.
   - Some writes bypass canonical ERP service paths and need contract/security review before exposure.

3. **Background automation path**.
   - Morning briefing, cost-spike alerts, profit alerts, weekly digest, critical unified alerts, and role-based action alerts can send Telegram messages.
   - Wastage and factory-health schedulers compute snapshots but do not directly send standalone Telegram messages.
   - Payment reminders are owner-triggered n8n webhook dispatches, not an enabled Telegram scheduler.

The highest-priority configuration defect is the split callback architecture: visible `action:*` buttons are placeholders while real `W*`/`A*` handlers exist elsewhere.

## 1. Auto-Send Messages Already Configured

| Message/Alert | Trigger | Schedule | Recipient Role | Source File | Live DB Data? | Status |
|---|---|---|---|---|---|---|
| Morning briefing | Scheduler batch for active factories | Daily 07:00 IST, reporting previous day | Owner; active Sub-Owner bindings receive a separate operational briefing | `services/briefing_scheduler.py`, `services/briefing_service.py` | Yes | Working, but welcome text incorrectly says 09:00 |
| Daily briefing/manual refresh | Telegram legacy callback or briefing API | On demand | Owner/Sub-Owner, role-filtered | `services/telegram_onboarding.py`, `services/briefing_recovery_merge.py`, `routers/briefings.py` | Yes | Working |
| Weekly profit digest | Scheduler batch | Sunday 20:00 IST | Owner | `services/weekly_digest_scheduler.py`, `services/weekly_profit_digest.py` | Yes, reads persisted snapshots | Working, but welcome text incorrectly says 19:00 |
| Payment reminders | Owner calls automation endpoint; payload sent to n8n | No scheduler configured in Compose | External n8n workflow/customer channel; not direct Telegram | `routers/automation.py` | Yes | Partially Working; manual trigger only, n8n workflow not present in repo |
| Low stock alerts | `sync_factory_alerts()` during morning briefing; critical alerts send immediately | During 07:00 briefing batch or explicit sync | Owner | `services/unified_alerts.py`, `services/briefing_scheduler.py` | Yes | Working for generated risk items; no dedicated low-stock scheduler |
| Wastage alerts | Wastage snapshot creates `WastageAlertLog`; unified-alert sync may send critical alert | Snapshot daily 06:00; Telegram evaluation during briefing sync | Owner for critical unified alerts | `services/wastage_scheduler.py`, `services/wastage_intelligence.py`, `services/unified_alerts.py` | Yes | Partially Working; no direct standalone wastage send |
| Production alerts | Sub-Owner/Supervisor production create/delete hooks | Immediate on business action | Owner | `services/telegram_action_alerts.py`, `routers/operations.py` | Yes | Working, best effort, throttled |
| Factory health alerts | Health snapshot calculation | Daily 23:58 IST | None directly; included in later briefing | `services/factory_health_scheduler.py`, `services/briefing_service.py` | Yes | Partially Working; calculation only |
| Cost spike alert | Cost variance exceeds deterministic threshold | Daily 23:55 IST | Factory Telegram target/Owner fallback | `services/cost_scheduler.py` | Yes | Working, deduplicated once per factory/day |
| Profit warning/critical alert | Profit snapshot meets alert rule | Daily 23:59 IST | Factory Telegram target/Owner fallback | `services/profit_scheduler.py` | Yes | Working |
| Critical unified alert | New critical alert or severity escalation | Immediate when `send_critical=True` | Active Owner bindings | `services/unified_alerts.py` | Yes | Working |
| ERP action alert | Sub-Owner/Supervisor creates sale, payment, production, inventory adjustment, advance, high expense, customer, or high outstanding | Immediate | Owner only | `services/telegram_action_alerts.py` | Yes | Working; max 5 per actor/action/hour |
| Telegram connection welcome | Successful bind code/token | Immediate | Newly bound Owner/Sub-Owner | `routers/integrations.py`, `services/telegram_onboarding.py` | Factory/user details are live | Working; advertised schedules are stale |
| Session cleanup messages | Session cleaner marks expired sessions and removes old callback dedupe records | Every 60 seconds | None | `services/telegram_session_cleaner.py` | DB maintenance only | No messages sent |

Docker Compose enables: briefing, cost, factory-health, wastage, profit, weekly-digest, and Telegram session-cleaner services.

No Telegram-specific n8n workflow is stored in the repository. The only Telegram n8n reference is an optional bridge URL in `routers/integrations.py`. The committed n8n JSON is invoice-oriented.

## 2. Telegram `/menu` Buttons

| Button | Callback Data | Parent Menu | Backend Handler | Live DB Data? | Status |
|---|---|---|---|---|---|
| Dekho | `menu:view` | Main | `handle_nested_menu_callback` | No data itself | Working |
| Kaam Karo | `menu:action` | Main | `handle_nested_menu_callback` | No data itself | Working navigation |
| Alerts | `menu:alerts` | Main | Placeholder branch | No | Placeholder |
| Settings | `menu:settings` | Main | Placeholder branch | No | Placeholder |
| Outstanding | `read:outstanding` | Dekho | `read_outstanding` | Yes | Working |
| Today Production | `read:today_production` | Dekho | `read_today_production` | Yes | Working |
| Inventory Stock | `read:inventory` | Dekho | `read_inventory` | Yes | Working |
| Payments Received | `read:payments` | Dekho | `read_payments` | Yes | Working |
| Expenses | `read:expenses` | Dekho | `read_expenses` | Yes | Working |
| Attendance | `read:attendance` | Dekho | `read_attendance` | Yes | Working |
| Day/Night Wastage | `read:wastage` | Dekho | `read_wastage` | Yes | Working |
| Invoice Summary | `read:invoices` | Dekho | `read_invoices` | Yes | Working |
| Add Production | `action:add_production` | Kaam Karo | Generic placeholder branch | No | Placeholder |
| Save Shift Wastage | `action:save_wastage` | Kaam Karo | Generic placeholder branch | No | Placeholder |
| Record Payment | `action:record_payment` | Kaam Karo | Generic placeholder branch | No | Placeholder |
| Create Invoice | `action:create_invoice` | Kaam Karo | Generic placeholder branch | No | Placeholder |
| Mark Attendance | `action:mark_attendance` | Kaam Karo | Generic placeholder branch | No | Placeholder |
| Add Expense | `action:add_expense` | Kaam Karo | Generic placeholder branch | No | Placeholder |
| Save/Edit/Cancel | `confirm:*` | Confirmation | Placeholder session handler | No business writes | Partially Working |

## 3. Dekho Read-Only Buttons

All handlers are in `services/telegram_read_service.py`. Authorization requires an active `TelegramUserBinding`, active same-factory user, and role Owner or Sub-Owner.

| Button | Factory Scoped | Real Data | Output/Limit | Pagination/View More |
|---|---|---|---|---|
| Outstanding | Yes | `OutstandingBill` + `Customer` | Total, overdue total, top 10 bills ordered by balance | No pagination; dashboard hint only |
| Today Production | Yes | `DailyProduction`, `Machine`, `Worker` | Total boxes/packets/raw deductions, latest 10 rows | No pagination |
| Inventory Stock | Yes | `BlankStock`, `BottomStock`, `FinalProductStock` | Item/low/out counts and first 10 combined rows | No pagination; dashboard hint |
| Payments Received | Yes | `PaymentCollection` + `Customer` | Today total, last-seven-day total, latest 10 | No pagination |
| Expenses | Yes | `FactoryExpense` | Today/week/month totals, top 10 categories | No pagination |
| Attendance | Yes | `AttendanceLog` | Status counts and payable attendance for today | Not needed; aggregate only |
| Day/Night Wastage | Yes | `ShiftWastage` | Day/night/total and up to 10 notes | No pagination |
| Invoice Summary | Yes | `InvoiceDocument` | Total/cancelled/outstanding plus latest 10 invoices | No pagination; history hint |

Observations:

- No Dekho callback returns the old “Live data integration next phase mein hogi” text.
- Empty-state messages are legitimate data-empty responses, not placeholders.
- Inventory reads all canonical rows and does not separately label raw versus finished sections.
- There is no Telegram-side pagination or functional View More callback.

## 4. Kaam Karo Action Buttons

### Visible Nested Menu

| Action | Visible | Callback | Step Flow | Saves DB | Confirmation | Audit Log | Permission |
|---|---|---|---|---|---|---|---|
| Add Production | Yes | `action:add_production` | Placeholder session only | No | Placeholder Save/Edit/Cancel | No business audit | Owner/Sub-Owner menu access |
| Save Shift Wastage | Yes | `action:save_wastage` | Placeholder session only | No | Placeholder | No | Owner/Sub-Owner |
| Record Payment | Yes | `action:record_payment` | Placeholder session only | No | Placeholder | No | Owner/Sub-Owner |
| Create Invoice | Yes | `action:create_invoice` | Placeholder session only | No | Placeholder | No | Owner/Sub-Owner |
| Mark Attendance | Yes | `action:mark_attendance` | Placeholder session only | No | Placeholder | No | Owner/Sub-Owner |
| Add Expense | Yes | `action:add_expense` | Placeholder session only | No | Placeholder | No | Owner/Sub-Owner |

### Separate Legacy Write Router

`POST /api/v1/telegram/action` exposes real handlers, but current `/menu` does not emit their callback names.

| Legacy Flow | Callback Family | Implemented Write | Confirmation | Audit | Assessment |
|---|---|---|---|---|---|
| Add Production | `A3:*` | Creates production through Telegram action service | Yes | Yes | Implemented but disconnected from current menu |
| Mark Attendance | `A4:*` | Creates/updates attendance | Yes | Yes | Implemented but disconnected |
| Save Shift Wastage | `W2:*` | Writes `ShiftWastage` | Yes | Yes | Implemented but disconnected |
| Create Invoice | `W3:*` | Directly creates legacy `SalesInvoice` and `OutstandingBill` | Yes | Yes | Risky/Partially Working; bypasses canonical invoice APIs and uses fixed pricing/random invoice number |
| Record Payment | `W4:*` | Allocates `BillPayment` to outstanding bills | Yes | Yes | Partially Working; review against canonical payment service |
| Edit Production | `W5:*` | Updates `DailyProduction` and recalculates stock | Yes | Yes | Implemented, not visible |
| Add Expense | None | None | No | No | Not Implemented |

Permission concerns in the legacy route:

- Unknown chats are blocked and callbacks are deduplicated.
- A binding resolves the actual user, but legacy fallback may use the factory Owner when no user binding is found.
- Role checks are inconsistent by action. For example, payment explicitly restricts Sub-Owner, while other writes do not consistently enforce a role matrix.
- Supervisor cannot create a `TelegramUserBinding` in the current self-service model, but action alerts can originate from Supervisor ERP actions.

## 5. Visible but Not Configured

These buttons are visible and only create placeholder sessions/text:

- Alerts
- Settings
- Add Production
- Save Shift Wastage
- Record Payment
- Create Invoice
- Mark Attendance
- Add Expense
- Confirmation Edit
- Confirmation Save

Current placeholder wording includes:

- “Alert Center navigation placeholder.”
- “Settings navigation placeholder.”
- “Step-by-step input placeholder ready hai.”
- “database update disabled hai.”
- “Input collection next phase mein enable hoga.”

## 6. Missing Buttons Recommended

| Button | Recommended Location | Existing Backend Capability | Priority |
|---|---|---|---|
| Raw Material Stock | Dekho > Inventory submenu | `BlankStock`, `BottomStock`; legacy `A2:view_rm` exists | High |
| Finished Goods Stock | Dekho > Inventory submenu | `FinalProductStock`; legacy `A2:view_fg` exists | High |
| Low Stock | Dekho or Alerts | Unified alerts and briefing risk items | High |
| Customer Outstanding Search | Dekho > Outstanding | Customer/outstanding queries exist | High |
| Invoice Search | Dekho > Invoices | Legacy `A12:*` exists | High |
| Download Invoice PDF | Invoice result row | Canonical authenticated PDF endpoint exists | High; use secure link/auth strategy |
| Today Day/Night Wastage | Already present | Live | Complete |
| Sunday Weekly-Off Attendance | Attendance submenu | Attendance domain exists; no Telegram callback | Medium |
| Cancel Invoice | Kaam Karo > Invoice | Canonical cancellation/reversal paths need routing | Medium; Owner only |
| Owner Approval Actions | Alerts/action center | Unified alerts and owner verification fields exist | Medium |

Do not expose legacy direct invoice creation as-is. Route Telegram writes through canonical ERP services so invoice numbering, stock deductions, ledger allocation, GST validation, and audit behavior remain consistent.

## 7. Testing Audit

| Requirement | Current Coverage | Result |
|---|---|---|
| `/menu` shows main menu | `test_owner_menu_contains_full_set_of_buttons` | Covered |
| Every Dekho callback is configured | `test_dekho_menu_uses_stable_live_read_callbacks` | Callback list covered |
| Each callback returns non-placeholder live response | Factory-scoped test exercises outstanding, inventory, production, wastage | Partial; payments, expenses, attendance, invoices need explicit seeded-data assertions |
| Unauthorized Telegram user blocked | Unknown chat and webhook-secret tests | Covered |
| Factory isolation | Binding and callback isolation tests | Covered |
| Owner/Sub-Owner permissions | Separate binding/menu and owner-only callback tests | Covered |
| Supervisor disabled by default | Integration access rejection test and binding model constraint | Covered |
| Read-only buttons do not write DB | No comprehensive before/after business-table assertion | Gap |
| Write buttons require confirmation | Nested placeholder test and legacy guided-flow tests | Covered structurally |
| Visible write buttons actually save | Tests explicitly assert they do not write | Not implemented |
| Callback replay protection | Dedupe tests | Covered |
| Session expiration/cleanup | Session and dedupe cleanup tests | Covered |
| Action alert throttling/failure isolation | Action-alert tests | Covered |

Recommended tests:

1. Parameterize all eight `read:*` callbacks with seeded same-factory and cross-factory rows.
2. Snapshot business-table row counts before/after each Dekho callback.
3. Assert every visible non-navigation button returns text without “placeholder”, “next phase”, or “disabled”.
4. Once Kaam Karo is wired, test role permission, confirmation, canonical service invocation, transaction rollback, and ActivityLog creation per action.
5. Add a contract test ensuring every callback in `ACTION_MENU` has a concrete dispatcher.

## 8. Priority Plan

### Phase 1: Make All Dekho Buttons Live

Current state: functionally live.

Next work:

- Add explicit tests for payments, expenses, attendance, and invoice callbacks.
- Split Inventory into Raw Material, Finished Goods, and Low Stock.
- Add search/pagination or bounded View More callbacks.
- Wire Alerts to `UnifiedAlert` instead of placeholder text.
- Correct welcome-message schedules to 07:00 and Sunday 20:00 IST.

### Phase 2: Make Kaam Karo Write Buttons

- Choose one callback namespace; retire the split between `action:*` and `A*/W*`.
- Route writes through canonical production, attendance, wastage, payment, invoice, and expense services.
- Enforce an explicit Owner/Sub-Owner permission matrix.
- Keep confirmation, dedupe, session expiry, transaction rollback, and audit logging.
- Implement Add Expense, which currently has no write handler.
- Do not expose the legacy invoice handler until fixed.

### Phase 3: Auto Alerts and Scheduled Telegram Summaries

- Add a dedicated scheduled payment-reminder policy if desired; current endpoint only pushes to n8n on demand.
- Decide whether WARNING wastage/health alerts should send independently or remain briefing-only.
- Add direct factory-health alert policy if required.
- Add delivery observability for all schedulers using recipient-aware logs.
- Reconcile welcome-message claims with actually enabled automations.

## Configuration Checklist

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_BOT_USERNAME`
- `TELEGRAM_WEBHOOK_SECRET`
- `PUBLIC_API_ORIGIN`
- `JWT_SECRET_KEY` for encrypted per-factory tokens
- `N8N_API_KEY` for the legacy action bridge
- Optional `N8N_PAYMENT_REMINDER_WEBHOOK`
- Telegram webhook expected at `/api/integrations/telegram/webhook`

## Final Status

- **Dekho:** Working with live, factory-scoped DB data.
- **Kaam Karo:** Visible but placeholder in the active `/menu`.
- **Legacy writes:** Substantial implementation exists but is disconnected and not uniformly safe.
- **Scheduled Telegram:** Morning briefing, cost, profit, weekly digest, critical alerts, and action alerts are configured.
- **Snapshot-only schedulers:** Wastage and factory health.
- **n8n:** Payment reminder trigger and optional bridge references exist; no committed Telegram workflow.

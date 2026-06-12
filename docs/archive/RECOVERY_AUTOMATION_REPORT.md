# Munshi AI Sprint P4.11 — Recovery Automation Report

Date: 2026-06-09
Status: COMPLETED
Tests: 30/30 PASS

---

## What Was Built

Owner को सिर्फ outstanding दिखाना नहीं, बल्कि recovery action लेने में मदद करना.

### 1. Recovery Action Suggestions

For each high-risk due customer (>15 days or >₹1L), the system generates a structured suggestion with:
- Customer name
- Outstanding amount
- Due days
- Suggested action: "Payment reminder bhejna chahiye."

### 2. Owner Approval Flow (Telegram)

Four Telegram callbacks implemented:

| Callback | Action | Result |
|---|---|---|
| `R1:send_reminder:<customer_id>` | Copy reminder | Returns copyable Hinglish reminder text |
| `R1:skip:<customer_id>` | Skip | Marks followup as "skipped" |
| `R1:done:<customer_id>` | Mark done | Marks followup as "followup_done" |
| `R1:snooze:<customer_id>` | Snooze 3d | Hides for 3 days |

### 3. Reminder Delivery

Reminder text is copy-ready Hinglish (no WhatsApp/SMS integration):

```
Namaste ABC Traders ji,
Aapka ₹320000 payment 18 din se pending hai.
Kripya payment update karein.

* Factory Name
```

Owner copies and sends manually. No automatic customer messaging.

### 4. Dashboard UI — Action Buttons

Collection War Room table now has 3 action buttons per customer row:

| Button | Color | Action |
|---|---|---|
| Copy Reminder | Blue | Copies reminder text to clipboard, logs as "copied" |
| Mark Done | Green | Confirmation dialog then marks "followup_done" |
| Snooze 3d | Amber | Snoozes for 3 days, hides from suggestions |

### 5. Backend Model — `recovery_followups`

| Column | Type | Description |
|---|---|---|
| `id` | Integer PK | Auto-increment |
| `factory_id` | BigInteger | Tenant isolation |
| `customer_id` | Integer FK | Customer reference |
| `outstanding_bill_id` | Integer FK, nullable | Bill reference |
| `suggested_amount_paise` | BigInteger | Amount in paise |
| `due_days` | Integer | Days overdue |
| `status` | String(30) | suggested/copied/skipped/followup_done/snoozed |
| `snoozed_until` | DateTime TZ, nullable | Snooze expiry |
| `last_action_at` | DateTime TZ, nullable | Last action timestamp |
| `created_by_user_id` | Integer FK | Who created |
| `created_at` | DateTime TZ | Created timestamp |
| `updated_at` | DateTime TZ | Updated timestamp |

---

## Files Changed

### Backend

| File | Change |
|---|---|
| `apps/api/models.py` | Added `RecoveryFollowup` class |
| `apps/api/alembic/versions/20260619_0029_recovery_followups.py` | New migration for `recovery_followups` table |
| `apps/api/services/recovery_automation.py` | New — suggestions, reminder text, 4 action functions |
| `apps/api/routers/dashboard.py` | Added 5 new API endpoints for recovery actions |
| `apps/api/routers/telegram_actions.py` | Added R1 callback dispatch for recovery actions |

### Frontend

| File | Change |
|---|---|
| `apps/web/src/lib/api.ts` | Added 4 new API functions (getRecoverySuggestions, copyReminder, markDone, snoozeCustomer) |
| `apps/web/src/pages/CollectionWarRoomPage.tsx` | Added Copy Reminder, Mark Done, Snooze 3d buttons per customer row |

### Tests

| File | Tests |
|---|---|
| `apps/api/tests/test_recovery_automation.py` | 7 tests (all pass) |

---

## API Endpoints

### New Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/dashboard/collection-war-room/suggestions` | Returns recovery suggestions for high-risk customers |
| POST | `/api/dashboard/collection-war-room/actions/copy-reminder/{customer_id}` | Logs followup as "copied" |
| POST | `/api/dashboard/collection-war-room/actions/skip/{customer_id}` | Skips followup |
| POST | `/api/dashboard/collection-war-room/actions/mark-done/{customer_id}` | Marks followup done |
| POST | `/api/dashboard/collection-war-room/actions/snooze/{customer_id}` | Snoozes for N days (default 3) |

### Telegram Callbacks

| Callback | Description |
|---|---|
| `R1:send_reminder:<customer_id>` | Copy reminder text |
| `R1:skip:<customer_id>` | Skip this customer |
| `R1:done:<customer_id>` | Mark follow-up done |
| `R1:snooze:<customer_id>` | Snooze 3 days |

---

## Test Results

```
tests/test_recovery_automation.py ........ 7 passed
tests/test_telegram_action_alerts.py .... 18 passed
tests/test_collection_war_room.py ........ 2 passed
tests/test_invoice_intelligence.py ....... 3 passed
--------------------------------------------------
TOTAL .................................. 30 passed in 22.34s
```

### Recovery Automation Tests

| Test | Result |
|---|---|
| `test_high_risk_generates_suggestions` | PASS |
| `test_reminder_text_generated_correctly` | PASS |
| `test_copy_action_logs_followup` | PASS |
| `test_snooze_hides_suggestion` | PASS |
| `test_followup_done_status_persists` | PASS |
| `test_cross_factory_customer_blocked` | PASS |
| `test_skip_action` | PASS |

---

## Deployment Steps

1. Run validation gate: `./validate-and-test.sh`
2. Create pre-migration backup
3. Apply Alembic migration 0029: `alembic upgrade head`
4. Verify: `SELECT count(*) FROM recovery_followups;`
5. Rebuild API container
6. Rebuild Web container
7. Recreate Caddy

## Rules Enforced

- ❌ No WhatsApp API integration
- ❌ No auto-calling
- ❌ No automatic customer messaging
- ❌ No payment gateway collection links
- ✅ Owner/Sub-Owner can view suggestions based on permission
- ✅ Only Owner can mark final follow-up action
- ✅ Tenant isolation on every query
- ✅ Copy-able reminder text, not auto-sent
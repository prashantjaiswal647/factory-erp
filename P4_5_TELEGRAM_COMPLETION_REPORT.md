# MUNSHI AI — Sprint P4.5: Telegram Assistant Completion Report

Date: 2026-06-09
Author: Chief Product Architect
Sprint Priority Score: 4,859,990 (Must-have, rank #2)
Source roadmap: MUNSHI_AI_PRIORITY_ROADMAP.md §3

---

## 0. Honest Premise

A non-trivial portion of P4.5 is already shipped across two prior
sprints (Z2.7A backend unification, Z2.7B frontend card, plus earlier
`render_welcome_message` + menu code). This report does not pretend
those were never built. It:

  - Maps each of the 10 spec items to the current code.
  - Marks DONE / PARTIAL / NEW.
  - Designs only the NEW + PARTIAL items.
  - Refuses to redo work that is already tested and live.

The acceptance gate for P4.5 is: owner opens Telegram daily for 14
consecutive days after this sprint ships.

---

## 1. Spec Item Status (10 of 10)

| # | Spec item                                | Status   | Evidence                                        |
|---|------------------------------------------|----------|-------------------------------------------------|
| 1 | Welcome Message                          | DONE     | render_welcome_message (telegram_onboarding.py) |
| 2 | Role-specific onboarding message         | DONE     | Owner vs Sub-Owner branch in render_welcome_message |
| 3 | Owner/Sub-Owner separate channels        | DONE     | telegram_user_bindings row per user (AGENTS §15A) |
| 4 | Inline buttons (6 Owner, 5 Sub-Owner)    | DONE     | OWNER_MENU + SUB_OWNER_MENU + inline_keyboard() |
| 5 | /menu command                            | DONE     | integrations.py:554-571                         |
| 6 | Telegram status tracking                 | PARTIAL  | last_message_at, last_message_status exist; missing delivered/failed split + delivery_attempts |
| 7 | Welcome delivery tracking                | PARTIAL  | welcome_sent_at exists; missing welcome_status, welcome_failure_reason, welcome_delivery_attempts, welcome_delivered_at |
| 8 | Role-based action alerts                 | NEW      | Mentioned in welcome copy ("important dashboard actions ki suchna") but not implemented |
| 9 | Test message button                      | DONE     | telegram_test_message callback + /api/integrations/telegram/test-message endpoint |
| 10| Connection health monitoring             | NEW      | No dead-chat detection, no last_health_check_at, no health_state column |

Net: 6 DONE, 2 PARTIAL, 2 NEW. The "completion" framing in the spec
is therefore aspirational, not literal.

---

## 2. Already Shipped (6 items — touch lightly, do not refactor)

### 2.1 Welcome message

File: apps/api/services/telegram_onboarding.py:49-78

Owner copy is bilingual Hinglish + Devanagari mixed. Sub-Owner copy
exists with the same structure, includes the explicit "Owner ke
dashboard actions aapko Telegram par nahi bheje jayenge" line per
AGENTS §15A.

### 2.2 Role-specific onboarding message

Branch on user.role in render_welcome_message. Already differentiates:
  - heading tone
  - bullet list of what bot will send
  - staff action alert copy (Owner only)
  - Owner-vs-Sub-Owner action reciprocity line

### 2.3 Separate Owner / Sub-Owner channels

telegram_user_bindings is keyed on (factory_id, user_id) with a
unique constraint. Owner and Sub-Owner are separate rows. Sub-Owner
binding can never overwrite factory.telegram_chat_id (enforced in
_finalize_binding in integrations.py — only Owner touches
Factory.telegram_chat_id). No code change required.

### 2.4 Inline buttons

File: apps/api/services/telegram_onboarding.py:24-46

OWNER_MENU has 6 buttons across 3 rows:
  [Today Summary, Production Status]
  [Inventory Alert, Due Payments]
  [Staff Actions, Test Message]

SUB_OWNER_MENU has 5 buttons across 3 rows:
  [Today Summary, Production Status]
  [Inventory Alert, Payment Summary]
  [Test Message]

Both call inline_keyboard(role) which returns Telegram-shaped
inline_keyboard payload. callback_data values:
  owner_today_summary, owner_production_status, owner_inventory_alert,
  owner_due_payments, owner_staff_actions, subowner_today_summary,
  subowner_production_status, subowner_inventory_alert,
  subowner_payment_summary, telegram_test_message

Webhook resolves them in render_callback_response.

### 2.5 /menu command

File: apps/api/routers/integrations.py:553-571

User types /menu. Webhook looks up binding by chat_id, validates
binding.role matches user.role, sends inline_keyboard(binding.role)
to chat. Records last_message_at + last_message_status="sent".

Cross-binding protection:
  - /menu from a chat_id without binding -> "not connected"
  - /menu from a chat_id with binding.role != user.role -> rejected
  - Supervisor role has no binding, gets rejected

### 2.6 Test message button

callback_data=telegram_test_message handled in
render_callback_response:88-89 -> "✅ Telegram test successful. Munshi
AI alerts are active." Also reachable via
POST /api/integrations/telegram/test-message (integrations.py:433).

---

## 3. Partial Items (2 — finish them in this sprint)

### 3.1 Telegram status tracking (PARTIAL → DONE)

Current state: last_message_at + last_message_status exist. Status is
free-form string. No delivery_attempts, no delivered/failed split.

Gap: cannot answer "what is the last successful delivery" vs "what
is the last attempted delivery" reliably. Affects /diagnostics and
Owner trust.

Schema additions to telegram_user_bindings (migration 0026):
  - delivered_message_count     BIGINT default 0
  - failed_message_count        BIGINT default 0
  - last_delivery_attempt_at    TIMESTAMPTZ nullable
  - last_delivery_failure_code  VARCHAR(40) nullable
                                  values: 403_blocked_by_user,
                                          400_chat_not_found,
                                          429_rate_limited,
                                          500_server,
                                          timeout,
                                          unknown
  - last_delivery_failure_at    TIMESTAMPTZ nullable
  - last_delivery_failure_msg   TEXT nullable

Code changes in services/telegram_delivery.py:
  - Wrap send_telegram_message so every call:
      1. attempts send
      2. on 2xx -> binding.delivered_message_count += 1,
                   binding.last_message_at = now,
                   binding.last_message_status = "sent",
                   binding.last_delivery_attempt_at = now
      3. on non-2xx -> binding.failed_message_count += 1,
                       binding.last_message_status = "failed",
                       binding.last_delivery_attempt_at = now,
                       binding.last_delivery_failure_code + at + msg
      4. on 403/400 -> binding.is_active = False (dead chat)
      5. commit
  - Errors stay as TelegramDeliveryError; only binding side-effects
    are best-effort (do not propagate DB errors out of the send path)

Acceptance: GET /api/integrations/telegram/status returns
delivered_message_count > 0, last_delivery_attempt_at set within
last 24h, last_delivery_failure_code null for healthy bindings.

### 3.2 Welcome delivery tracking (PARTIAL → DONE)

Current state: welcome_sent_at exists, but it is set on FIRST attempt
regardless of whether the welcome actually reached the user. If the
chat_id is dead, welcome_sent_at is still recorded, which is a lie.

Schema additions to telegram_user_bindings (migration 0026):
  - welcome_status             VARCHAR(20) nullable
                                  values: pending, sent, failed
                                  default: pending
  - welcome_delivered_at       TIMESTAMPTZ nullable
  - welcome_failure_code       VARCHAR(40) nullable
  - welcome_failure_message    TEXT nullable
  - welcome_delivery_attempts  INTEGER default 0

Code changes in _finalize_binding (integrations.py):
  - Before send_welcome: set welcome_status="pending",
                         welcome_delivery_attempts += 1
  - After send: on 2xx -> welcome_status="sent",
                          welcome_delivered_at=now,
                          welcome_sent_at=now
                on err -> welcome_status="failed",
                          welcome_failure_code/message
  - The auto test message (also fired in _finalize_binding) gets the
    same treatment against last_message_status.

Acceptance: a successful bind shows
welcome_status="sent", welcome_delivered_at within last 60s, both
delivered counters incremented.

---

## 4. New Items (2 — design + build in this sprint)

### 4.1 Role-based action alerts (NEW)

Spec: when a Sub-Owner or Supervisor performs an important dashboard
action, the Owner gets a one-liner alert on Telegram.

Per AGENTS §15A: best-effort, must never roll back the underlying
ERP transaction. This is a side-effect only.

#### 4.1.1 Trigger surfaces

Hook into the existing ActivityLog writers. Action types that fire
an alert to Owner:

  - production.daily.create    -> "Sub-Owner X ne production entry dali, Y boxes."
  - production.daily.delete    -> "Sub-Owner X ne production entry delete ki, -Y boxes."
  - sales.invoice.create       -> "Sub-Owner X ne sale entry ki, ₹Y, customer Z."
  - sales.invoice.delete       -> "Sub-Owner X ne sale entry delete ki, -₹Y."
  - payment.create             -> "Sub-Owner X ne payment receive ki, ₹Y from Z."
  - inventory.update           -> "Sub-Owner X ne raw material adjust ki, item A, qty B."
  - worker.create / update     -> "Sub-Owner X ne worker add/update ki, name Y."
  - customer.create / update   -> "Sub-Owner X ne customer add/update ki, name Y."

Any action NOT on this list does not trigger a Telegram alert (chatty
alerts = owner mutes everything).

#### 4.1.2 Delivery

Service: services/telegram_action_alerts.py (new)

  def send_action_alert(
      db: Session,
      factory: Factory,
      actor_user: User,
      action_type: str,
      payload: dict,
  ) -> None:
      """Best-effort. Never raises."""
      try:
          if actor_user.role == "Owner":
              return  # Owner's own actions do not alert
          owner = db.query(User).filter(
              User.factory_id == factory.id,
              User.role == "Owner",
              User.is_active.is_(True),
          ).first()
          if not owner:
              return
          owner_binding = db.query(TelegramUserBinding).filter(
              TelegramUserBinding.factory_id == factory.id,
              TelegramUserBinding.user_id == owner.id,
              TelegramUserBinding.is_active.is_(True),
          ).first()
          if not owner_binding:
              return
          text = _format_action_alert(actor_user, action_type, payload)
          factory_obj = _factory_proxy(factory, owner_binding.telegram_chat_id)
          send_telegram_message(factory_obj, text)
      except Exception as exc:
          # Log + swallow. AGENTS §15A: must never roll back the
          # underlying ERP transaction.
          logger.warning("action alert failed", exc_info=exc, extra={
              "factory_id": factory.id,
              "action_type": action_type,
          })

Hook: in services/activity_logger.py::log_activity, after the row is
written, call send_action_alert in a BackgroundTask (or inline + best-
effort try/except). The action must be recorded even if the alert
fails.

#### 4.1.3 Throttling

Owner alerts get noisy fast. Per-(factory, actor, action_type, hour)
throttle: max 5 alerts per actor per hour. Excess alerts are
collapsed into a single "and 4 more actions this hour" summary.

Table: telegram_action_alert_throttle
  factory_id, actor_user_id, action_type, hour_bucket
  Unique (factory_id, actor_user_id, action_type, hour_bucket)
  count INTEGER default 0

Pure insert-or-increment; no row churn.

#### 4.1.4 Template (Hinglish, deterministic)

Format: "{actor_name} ({actor_role}) ne {action_verb} ki, {detail}."

Examples:
  "Suresh (Sub-Owner) ne production entry dali, 250 boxes, machine Paper Cup Line 1."
  "Ramesh (Supervisor) ne payment receive ki, ₹12,500 from Suresh Tea Stall."
  "Kavita (Sub-Owner) ne customer add ki, New Tea Corner (Delhi)."

No exclamation marks. No "good job". No emoji. Boring is correct.

### 4.2 Connection health monitoring (NEW)

Spec: detect dead chat_ids, stale bindings, surface to /diagnostics.

#### 4.2.1 Failure modes

  - User blocked the bot -> Telegram returns 403 Forbidden
  - User deleted Telegram account -> 400 chat not found
  - User's chat_id is temporarily unreachable -> 429 or timeout
  - Welcome never delivered (chat_id valid but unreachable at bind time)
  - Binding is_active=True but no successful send in 14+ days -> stale

#### 4.2.2 Detection

  - Reactive: send_telegram_message handler already flips is_active
    to False on 403/400 (added in 3.1).
  - Proactive: services/telegram_health_poller.py runs every 6h.
    For every binding with is_active=True:
      1. If last_delivery_attempt_at within 14 days -> skip
      2. Else: send a tiny health ping ("Munshi AI connection check")
         to the chat_id.
            2xx -> binding.last_health_check_at=now,
                   last_health_state="healthy"
            403/400 -> binding.is_active=False,
                       last_health_state="dead",
                       last_health_failure_code=403 or 400,
                       last_health_failure_at=now
            5xx/timeout -> binding.last_health_state="degraded",
                            retry on next 6h tick

#### 4.2.3 Schema additions (migration 0026)

  - last_health_check_at        TIMESTAMPTZ nullable
  - last_health_state           VARCHAR(20) nullable
                                   values: healthy, degraded, dead,
                                           untested
  - last_health_failure_code    VARCHAR(40) nullable
  - last_health_failure_at      TIMESTAMPTZ nullable
  - last_health_failure_message TEXT nullable

#### 4.2.4 /diagnostics endpoint extension

Already shipped (AGENTS §3 Z2.1). Add section:

  GET /api/integrations/telegram/diagnostics
  returns:
    binding: { is_active, telegram_username, telegram_first_name,
               connected_at, delivered_message_count, failed_message_count,
               last_delivery_attempt_at, last_delivery_failure_code,
               last_health_check_at, last_health_state }
    health_summary: {
       total_active_bindings: int,
       total_dead_bindings: int,
       total_stale_bindings: int (active but no send in 14d),
       dead_chat_ids: list[str]    (for super-admin view only)
    }

Acceptance: a dead chat_id is detected within 6h of the user blocking
the bot, the Owner sees the badge on /diagnostics, and the next
attempt to send a briefing skips dead bindings.

---

## 5. Migration Plan

### 5.1 Alembic migration 0026 — P4.5 telegram delivery + health

  apps/api/alembic/versions/2026XXXX_0026_telegram_delivery_health.py

  Alter table telegram_user_bindings, add columns:
    delivered_message_count, failed_message_count,
    last_delivery_attempt_at, last_delivery_failure_code,
    last_delivery_failure_at, last_delivery_failure_msg,
    welcome_status, welcome_delivered_at, welcome_failure_code,
    welcome_failure_message, welcome_delivery_attempts,
    last_health_check_at, last_health_state, last_health_failure_code,
    last_health_failure_at, last_health_failure_message

  Create table telegram_action_alert_throttle:
    id, factory_id, actor_user_id, action_type, hour_bucket, count
    UNIQUE (factory_id, actor_user_id, action_type, hour_bucket)
    INDEX (factory_id, hour_bucket)

  No destructive changes. Existing rows get defaults (0 / null /
  "untested"). No data loss. Backward compatible with the Z2.7A
  binding flow.

### 5.2 Compatibility note

  - welcome_sent_at stays as a quick filter, but the source of truth
    becomes welcome_status + welcome_delivered_at.
  - last_message_status stays as a one-line summary, but
    last_delivery_failure_code becomes the source of truth for
    "what went wrong".
  - Existing test_telegram_self_service.py continues to pass; new
    test cases assert the new columns.

---

## 6. Router / API Changes

### 6.1 New endpoint

  GET  /api/integrations/telegram/diagnostics
  Auth: any role that owns the binding (Owner / Sub-Owner)
  Returns: the diagnostics shape above (factory-scoped)

### 6.2 Extended endpoint

  GET  /api/integrations/telegram/status
  New fields in response:
    delivered_message_count
    failed_message_count
    last_delivery_attempt_at
    last_delivery_failure_code
    last_health_check_at
    last_health_state

  Old fields kept (backward compatible):
    connected, role, telegram_username, telegram_first_name,
    chat_id_verified, welcome_sent_at, last_message_at,
    last_message_status

### 6.3 New service

  apps/api/services/telegram_action_alerts.py
  apps/api/services/telegram_health_poller.py

### 6.4 Modified service

  apps/api/services/telegram_delivery.py
  - Wrap every send in delivery tracking
  - Persist to telegram_user_bindings after the call (best-effort)
  - 403 / 400 -> is_active=False

### 6.5 Modified router

  apps/api/routers/integrations.py::_finalize_binding
  - Set welcome_status="pending" before send
  - Set welcome_status="sent"/"failed" after send
  - Persist auto test message outcome against last_message_*

---

## 7. Test Plan

### 7.1 New pytest file

  apps/api/tests/test_p4_5_telegram_completion.py

Test cases (in order):

  test_owner_and_subowner_have_separate_bindings
    Owner binds chat_id 100 -> binding row factory_user_owner
    Sub-Owner binds chat_id 200 -> binding row factory_user_subowner
    Each binding has its own row, distinct chat_id, no cross-write
    factory.telegram_chat_id is set to Owner's chat only

  test_supervisor_cannot_bind_telegram
    Supervisor signup -> /connect-code -> 403
    Confirm no binding row exists

  test_welcome_message_uses_owner_copy
    Owner bind -> captured send text contains "Munshi AI aapko kya
    bhejega" + "Sub Owner ya Supervisor ke important dashboard actions"

  test_welcome_message_uses_subowner_copy
    Sub-Owner bind -> captured send text contains "aapko kya milega"
    and "Owner ke dashboard actions aapko Telegram par nahi bheje
    jayenge"

  test_owner_menu_has_six_buttons
    inline_keyboard("Owner") -> 3 rows, 6 buttons, exact texts

  test_subowner_menu_has_five_buttons
    inline_keyboard("Sub-Owner") -> 3 rows, 5 buttons,
    no "Staff Actions" button

  test_menu_command_sends_role_specific_keyboard
    Owner /menu -> captured send includes OWNER_MENU
    Sub-Owner /menu -> captured send includes SUB_OWNER_MENU
    Supervisor /menu -> rejected

  test_callback_today_summary_returns_four_numbers
    callback owner_today_summary -> text contains
    Production, Sales, Collection, Expenses, Net Snapshot

  test_callback_inventory_alert_lists_low_stock
    seed 2 items with quantity <= 0 -> text contains both

  test_callback_due_payments_shows_top_5_customers
    seed 6 customers with decreasing total_due -> text shows
    top 5 sorted by due desc

  test_callback_test_message_returns_ack
    callback telegram_test_message -> text contains
    "Telegram test successful"

  test_welcome_status_pending_then_sent_on_successful_bind
    before bind: welcome_status null
    after bind success: welcome_status="sent",
                       welcome_delivered_at within last 60s,
                       delivered_message_count >= 2
                                  (welcome + auto test)

  test_welcome_status_failed_when_chat_unreachable
    monkeypatch send_telegram_message -> raise TelegramDeliveryError
    after bind attempt: welcome_status="failed",
                        welcome_failure_code="unknown",
                        welcome_delivery_attempts >= 1
    binding.is_active stays True (failed welcome is not a dead chat)

  test_dead_chat_marks_binding_inactive
    monkeypatch send_telegram_message -> raise 403-style
    TelegramDeliveryError(retryable=False, http_status=403)
    assert binding.is_active == False
    assert last_delivery_failure_code == "403_blocked_by_user"

  test_role_based_action_alert_fires_to_owner
    Sub-Owner creates a production entry -> ActionAlert fired
    captured text contains "production entry dali" + box count

  test_owner_self_action_does_not_fire_alert
    Owner creates production entry -> no Telegram send to Owner
    (only the production writes happen)

  test_action_alert_throttled_to_5_per_actor_per_hour
    Sub-Owner creates 7 production entries in 1h
    assert: 5 action alerts sent, 2 throttled,
    throttle row count == 7 (rows persisted, but only 5 sent)

  test_health_poller_marks_dead_chats
    seed binding with is_active=True and last_delivery_attempt_at
    older than 14 days
    monkeypatch send_telegram_message -> raise 403
    run poller
    assert: binding.is_active == False
    assert: last_health_state == "dead"

  test_health_poller_marks_healthy_when_send_succeeds
    seed binding, is_active=True, last_delivery_attempt_at old
    send succeeds
    run poller
    assert: last_health_state == "healthy"

  test_diagnostics_endpoint_returns_new_fields
    Owner GET /api/integrations/telegram/diagnostics
    response has all new fields, no 500, factory-scoped

  test_status_endpoint_returns_new_fields
    GET /api/integrations/telegram/status includes
    delivered_message_count, failed_message_count,
    last_delivery_failure_code, last_health_state

  test_factory_isolation_for_action_alerts
    factory A Sub-Owner creates production
    factory B Owner must NOT receive an alert about factory A
    captured sends to factory B are unchanged

  test_supervisor_action_does_not_crash_underlying_erp
    monkeypatch send_telegram_message -> raise
    Supervisor creates production
    production row is committed regardless of alert failure

  test_send_telegram_message_never_propagates_db_errors
    monkeypatch db.commit -> raise
    send_telegram_message does not raise; caller (webhook) returns
    the standard TelegramActionResponse

### 7.2 Regression sweep (must stay green)

  tests/test_telegram_self_service.py          21 cases
  tests/test_role_based_telegram_alerts.py     varies
  tests/test_pilot_zero_touch_acceptance.py    1 case (Z2.7A flow)
  tests/test_finished_goods_sync.py            varies

  New test_p4_5_telegram_completion.py         ~22 cases

  Total: ~50+ cases. All green = P4.5 done.

---

## 8. Sprint Sequencing (within P4.5)

Day 1 morning — schema + tracking:
  P4.5.1  Alembic 0026 (add 15 columns + 1 new table)        0.25d
  P4.5.2  Pydantic schemas for new fields                     0.1d
  P4.5.3  Wrap send_telegram_message with delivery tracking   0.5d
  P4.5.4  Update _finalize_binding welcome_status flow       0.25d
  P4.5.5  Extend GET /status response                         0.1d
  P4.5.6  Add /diagnostics endpoint                           0.25d

Day 1 afternoon — action alerts:
  P4.5.7  services/telegram_action_alerts.py                  0.5d
  P4.5.8  Hook into services/activity_logger.py               0.25d
  P4.5.9  Throttle table + service                            0.25d
  P4.5.10 Hinglish template for action alert                  0.1d

Day 2 morning — health poller:
  P4.5.11 services/telegram_health_poller.py                  0.5d
  P4.5.12 Register in main.py lifespan                        0.1d
  P4.5.13 /diagnostics: health_summary section                 0.25d

Day 2 afternoon — tests:
  P4.5.14 test_p4_5_telegram_completion.py (~22 cases)        0.5d
  P4.5.15 Regression sweep                                    0.25d
  P4.5.16 validate-and-test.sh                                 0.25d

Total: 2 days, 1 engineer.

---

## 9. Risk Map

  Risk                                          Mitigation
  --------------------------------------------  --------------------------------
  Schema change touches a live table           Add columns with defaults
                                               (no destructive ALTER)
  403 detection depends on Telegram error      send_telegram_message already
  shape from python-telegram-bot or httpx      raises TelegramDeliveryError;
                                               we map 403/400 from exc
  Action alert spams Owner                     Throttle table, max 5 per
                                               actor per hour
  Health poller pings dead chats forever       is_active=False cuts the loop
  Best-effort swallows errors silently         Log to logger.warning with
                                               factory_id + action_type;
                                               /diagnostics shows count
  Welcome sent but bot unblocked later         welcome_status="sent" is the
                                               truthful state; rerun welcome
                                               flow not required
  Cross-factory leak in action alerts          send_action_alert always
                                               filters owner binding by
                                               factory_id of the actor
  /menu fires for non-binding chat             Reject if user.role !=
                                               binding.role (already done)
  Health poller rate-limited by Telegram       6h cadence, no burst, single
                                               ping per binding per tick
  Existing test_pilot_zero_touch_acceptance    6-char code binding unchanged;
  breaks on schema change                      only additive columns

---

## 10. Acceptance Criteria

This sprint is DONE only when:

  [ ] pytest apps/api/tests/test_p4_5_telegram_completion.py -> 22 green
  [ ] pytest apps/api/tests/test_telegram_self_service.py -> 21 still green
  [ ] pytest apps/api/tests/test_pilot_zero_touch_acceptance.py -> 1 still green
  [ ] npm run build in apps/web -> success
  [ ] alembic upgrade head on disposable DB -> no errors
  [ ] alembic downgrade -1 -> clean rollback
  [ ] ./validate-and-test.sh -> 0 failures
  [ ] Manual: Owner binds Telegram, gets welcome, taps every button,
      gets correct text, taps Test Message, gets ack
  [ ] Manual: Sub-Owner binds from a different phone, gets
      Sub-Owner copy + 5-button menu
  [ ] Manual: Supervisor account has no /connect-code option in UI
  [ ] Manual: Sub-Owner creates production; Owner phone receives
      one-liner within 5 seconds
  [ ] Manual: Owner blocks bot; next briefing poller marks binding
      is_active=False within 6 hours; /diagnostics shows dead
  [ ] Manual: Owner /menu -> 6 buttons; Sub-Owner /menu -> 5 buttons

---

## 11. What P4.5 Does NOT Do (deferred)

  - No bilingual Devanagari replies (Hinglish only)
  - No Telegram group chat support
  - No image / voice / document handling
  - No read receipts (Telegram standard bots cannot track reads)
  - No per-factory template override
  - No Snooze / Acknowledge buttons (next sprint)
  - No Markdown V2 rendering
  - No Hindi (Devanagari) action alert template
  - No Jinja2 / templating engine upgrade

---

## 12. Pilot vs Enterprise (this sprint)

  Feature                          Pilot (P4.5)         Enterprise
  -------------------------------- -------------------- ----------------------
  Languages                        Hinglish only         + Hindi + Tamil
  Welcome message types            2 (Owner, Sub-Owner)  per-role templates
  Button counts                    6 / 5 (Owner/Sub)    configurable per role
  Action alert throttling          5/actor/hour         configurable
  Health poller cadence            6 hours              1 hour
  /diagnostics audience            binding owner only   super-admin aggregate
  Dead-chat handling               mark inactive        + owner email fallback
  Per-factory template             none                 factory.template_set
  Cost                             ~12 sprints of work  6-week build w/ 2 eng

  P4.5 = Pilot column. Plain Hinglish, fixed buttons, fixed
  throttling, factory-local diagnostics.

---

## 13. Single Recommendation

Build P4.5 in 2 days. Three PRs:

  PR 1: migration 0026 + delivery tracking + welcome status
         (apps/api/alembic/versions/...0026,
          apps/api/services/telegram_delivery.py,
          apps/api/routers/integrations.py,
          apps/api/services/telegram_onboarding.py tests)
  PR 2: action alerts + throttling + health poller
         (apps/api/services/telegram_action_alerts.py,
          apps/api/services/telegram_health_poller.py,
          apps/api/services/activity_logger.py hook)
  PR 3: /diagnostics + /status extension + tests
         (apps/api/routers/integrations.py,
          apps/api/tests/test_p4_5_telegram_completion.py)

After P4.5 ships, the morning briefing (P4.8) becomes a 6-day build
instead of a 2-week build, because the channel is now trustworthy
and traceable.

---

Source: apps/api/services/telegram_onboarding.py, apps/api/routers/integrations.py,
apps/api/models.py:1717, AGENTS.md §3 §15A §15, Z2.7A + Z2.7B
deliveries, MUNSHI_AI_PRIORITY_ROADMAP.md §3.

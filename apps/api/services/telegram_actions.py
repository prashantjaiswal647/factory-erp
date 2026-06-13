"""
Telegram Action Layer – service handlers (P4.1).

All state transitions live here.  The router calls exactly one handler per
callback; each handler returns a TelegramActionResult that tells the router
what text to send back and which inline keyboard (if any) to attach.

Handler naming convention
  handle_<action>_<step>  — e.g.  handle_outstanding_view

Supported actions (A-number matches architecture report):
  A1  outstanding   view
  A2  inventory     view
  A3  production    start / size / machine / boxes / confirm / cancel
  A4  attendance    start / worker / status / confirm / cancel
  A5  briefing      full
  A6  ask           start  (read-only stub)

Factory isolation is enforced exclusively by the router before any handler
is called.  Handlers may trust that factory_id is correct.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from models import (
    ActivityLog,
    Factory,
    Machine,
    User,
    Worker,
)
from services.telegram_action_renderer import (
    format_attendance_preview,
    format_inventory_for_telegram,
    format_outstanding_for_telegram,
    format_production_preview,
)
from services.telegram_action_session import (
    TelegramActionSession,
    create_session,
    get_session,
    update_session,
)
from services.timezone_utils import KOLKATA_ZONE, get_kolkata_now

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type returned by every handler
# ---------------------------------------------------------------------------

@dataclass
class InlineButton:
    """A single Telegram inline-keyboard button."""
    text: str
    callback_data: str


@dataclass
class TelegramActionResult:
    """What the router sends back to Telegram."""
    message: str
    buttons: List[List[InlineButton]] = field(default_factory=list)
    # When True, the router should answer answerCallbackQuery with 'no toast'
    silent: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _audit(
    db: Session,
    factory_id: int,
    action_type: str,
    summary: str,
    *,
    user_id: Optional[int] = None,
    user_name: str = "Telegram",
    entity_type: str = "telegram_action",
    entity_id: Optional[int] = None,
) -> None:
    """Write one ActivityLog row for every callback action."""
    try:
        log = ActivityLog(
            factory_id=factory_id,
            event_type="telegram_action",
            description=summary[:2000],
            log_date=get_kolkata_now().date(),
            user_id=user_id,
            user_name=user_name[:255] if user_name else "Telegram",
            user_role="telegram",
            action_type=action_type[:100],
            action_summary=summary[:2000],
            entity_type=entity_type,
            entity_id=entity_id,
            short_statement=summary[:500],
            committed_at=datetime.now(KOLKATA_ZONE),
        )
        db.add(log)
        db.flush()
    except Exception:
        logger.exception("Audit log failure for telegram action %s – suppressed", action_type)


def _owner_for_factory(db: Session, factory_id: int) -> Optional[User]:
    return (
        db.query(User)
        .filter(User.factory_id == factory_id, User.role == "Owner", User.is_active.is_(True))
        .order_by(User.id.asc())
        .first()
    )


def _main_buttons() -> List[List[InlineButton]]:
    """Standard action keyboard appended to most replies."""
    return [
        [
            InlineButton("💵 Outstanding", "A1:view"),
            InlineButton("📦 Inventory",   "A2:view"),
        ],
        [
            InlineButton("📋 Full Briefing", "A5:full"),
            InlineButton("🤖 Ask Munshi",    "A6:start"),
        ],
    ]


# ---------------------------------------------------------------------------
# A1 – Outstanding view
# ---------------------------------------------------------------------------

def handle_outstanding_view(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    user: Optional[User] = None,
) -> TelegramActionResult:
    """Fetch outstanding and format for Telegram."""
    try:
        from routers.sales import get_sales_outstanding as _get_outstanding
        from models import OutstandingBill, Order
        from sqlalchemy.orm import joinedload

        # ── re-use the business logic directly (no HTTP) ──────────────────
        # We replicate the core query from get_sales_outstanding here to avoid
        # FastAPI dependency injection machinery.
        from decimal import Decimal
        from models import OutstandingBill

        bills = (
            db.query(OutstandingBill)
            .options(joinedload(OutstandingBill.customer))
            .filter(OutstandingBill.factory_id == factory_id)
            .filter(OutstandingBill.balance_amount > 0)
            .filter(OutstandingBill.status.in_(["active", "partial"]))
            .order_by(OutstandingBill.customer_id.asc())
            .all()
        )

        # Build a minimal DTO the renderer understands
        from types import SimpleNamespace

        customer_map: Dict[int, Any] = {}
        grand_total = Decimal("0.00")
        is_sub_owner = user is not None and hasattr(user, "role") and user.role == "Sub-Owner"

        for bill in bills:
            if not bill.customer:
                continue
            cid = bill.customer.id
            if cid not in customer_map:
                customer_map[cid] = SimpleNamespace(
                    customer_name=bill.customer.name,
                    current_pending_balance=Decimal("0.00"),
                )
            if not is_sub_owner:
                customer_map[cid].current_pending_balance += Decimal(str(bill.balance_amount or 0))
                grand_total += Decimal(str(bill.balance_amount or 0))

        if is_sub_owner:
            uniq_customers = {b.customer.name for b in bills if b.customer}
            text = "💵 *Outstanding Balances*\nTotal Outstanding: [Masked]\n\n*Top Customers:*\n"
            for idx, name in enumerate(list(uniq_customers)[:5], 1):
                text += f"{idx}. *{name}*: [Masked]\n"
            if not uniq_customers:
                text += "No outstanding payments."
        else:
            outstanding = SimpleNamespace(
                grand_total_outstanding=grand_total,
                customers=list(customer_map.values()),
            )
            text = format_outstanding_for_telegram(outstanding)

    except Exception:
        logger.exception("Outstanding view failed factory_id=%s", factory_id)
        text = "❌ Could not load outstanding data. Please try again."

    _audit(db, factory_id, "A1_OUTSTANDING_VIEW", "Viewed outstanding balances via Telegram", user_name="telegram-action")
    return TelegramActionResult(message=text, buttons=_main_buttons())


# ---------------------------------------------------------------------------
# A2 – Inventory view
# ---------------------------------------------------------------------------

def handle_inventory_view(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
) -> TelegramActionResult:
    """Fetch raw material / finished goods stock for Telegram."""
    try:
        from models import Inventory

        items = (
            db.query(Inventory)
            .filter(Inventory.factory_id == str(factory_id))
            .order_by(Inventory.item_name.asc().nullslast())
            .limit(20)
            .all()
        )
        rows = [
            {
                "item_name": i.item_name or "Unknown",
                "current_quantity": float(i.current_quantity or i.quantity or 0),
                "unit": i.unit or "pieces",
            }
            for i in items
        ]
        text = format_inventory_for_telegram(rows)

    except Exception:
        logger.exception("Inventory view failed factory_id=%s", factory_id)
        text = "❌ Could not load inventory data. Please try again."

    _audit(db, factory_id, "A2_INVENTORY_VIEW", "Viewed inventory stock via Telegram", user_name="telegram-action")
    return TelegramActionResult(message=text, buttons=_main_buttons())


# ---------------------------------------------------------------------------
# A3 – Production (guided, multi-step, requires confirmation)
# ---------------------------------------------------------------------------

ACTION_PRODUCTION = "production"


def handle_production_start(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
) -> TelegramActionResult:
    """Step 0 – ask user to choose size."""
    sizes = (
        db.query(Machine.mould_size_ml)
        .filter(Machine.factory_id == str(factory_id), Machine.mould_size_ml.isnot(None))
        .distinct()
        .order_by(Machine.mould_size_ml.asc())
        .all()
    )
    size_buttons = [
        [InlineButton(f"{row[0]} ml", f"A3:size:{row[0]}")]
        for row in sizes
        if row[0]
    ]
    if not size_buttons:
        return TelegramActionResult(
            message="⚠️ No machines found for this factory. Please add machines first.",
            buttons=_main_buttons(),
        )
    create_session(db, factory_id, chat_id, ACTION_PRODUCTION, "size", {})
    _audit(db, factory_id, "A3_PRODUCTION_START", "Started guided production entry via Telegram")
    return TelegramActionResult(
        message="📋 *Record Production*\n\nSelect the cup size:",
        buttons=size_buttons + [[InlineButton("❌ Cancel", "A3:cancel")]],
    )


def handle_production_size(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    size_ml: int,
) -> TelegramActionResult:
    """Step 1 – size chosen → ask which machine."""
    machines = (
        db.query(Machine)
        .filter(
            Machine.factory_id == str(factory_id),
            Machine.mould_size_ml == size_ml,
        )
        .order_by(Machine.name.asc())
        .all()
    )
    if not machines:
        return TelegramActionResult(
            message=f"⚠️ No machines found for {size_ml} ml. Try a different size.",
            buttons=[[InlineButton("🔙 Back", "A3:start"), InlineButton("❌ Cancel", "A3:cancel")]],
        )
    session = get_session(db, factory_id, chat_id, ACTION_PRODUCTION)
    if session:
        update_session(db, session.session_id, "machine", {"size_ml": size_ml})
    else:
        create_session(db, factory_id, chat_id, ACTION_PRODUCTION, "machine", {"size_ml": size_ml})

    machine_buttons = [
        [InlineButton(m.name, f"A3:machine:{m.id}")]
        for m in machines
    ]
    return TelegramActionResult(
        message=f"✅ Size: *{size_ml} ml*\n\nSelect the machine:",
        buttons=machine_buttons + [[InlineButton("❌ Cancel", "A3:cancel")]],
    )


def handle_production_machine(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    machine_id: int,
) -> TelegramActionResult:
    """Step 2 – machine chosen → ask boxes count."""
    machine = (
        db.query(Machine)
        .filter(Machine.factory_id == str(factory_id), Machine.id == machine_id)
        .first()
    )
    if not machine:
        return TelegramActionResult(
            message="⚠️ Machine not found. Please start again.",
            buttons=[[InlineButton("🔙 Start Over", "A3:start"), InlineButton("❌ Cancel", "A3:cancel")]],
        )
    session = get_session(db, factory_id, chat_id, ACTION_PRODUCTION)
    new_payload = dict(session.payload_json) if session else {}
    new_payload["machine_id"] = machine_id
    new_payload["machine_name"] = machine.name
    if session:
        update_session(db, session.session_id, "boxes", new_payload)
    else:
        create_session(db, factory_id, chat_id, ACTION_PRODUCTION, "boxes", new_payload)

    box_options = [25, 50, 100, 150, 200, 300]
    box_buttons = [
        [InlineButton(str(b), f"A3:boxes:{b}") for b in box_options[:3]],
        [InlineButton(str(b), f"A3:boxes:{b}") for b in box_options[3:]],
        [InlineButton("❌ Cancel", "A3:cancel")],
    ]
    return TelegramActionResult(
        message=f"✅ Machine: *{machine.name}*\n\nHow many boxes were produced today?",
        buttons=box_buttons,
    )


def handle_production_boxes(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    boxes: int,
) -> TelegramActionResult:
    """Step 3 – boxes count → show confirmation."""
    session = get_session(db, factory_id, chat_id, ACTION_PRODUCTION)
    if not session:
        return TelegramActionResult(
            message="⚠️ Session expired. Please start again.",
            buttons=[[InlineButton("🔙 Start Over", "A3:start")]],
        )
    new_payload = dict(session.payload_json)
    new_payload["boxes"] = boxes
    update_session(db, session.session_id, "confirm", new_payload)

    size_ml = new_payload.get("size_ml", "?")
    machine_name = new_payload.get("machine_name", "?")
    preview = format_production_preview(size_ml, machine_name, boxes)
    return TelegramActionResult(
        message=preview,
        buttons=[
            [
                InlineButton("✅ Confirm", "A3:confirm"),
                InlineButton("❌ Cancel", "A3:cancel"),
            ]
        ],
    )


def handle_production_confirm(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    owner: Optional[User],
) -> TelegramActionResult:
    """Step 4 – commit production entry."""
    session = get_session(db, factory_id, chat_id, ACTION_PRODUCTION)
    if not session:
        return TelegramActionResult(
            message="⚠️ Session expired. Please start again.",
            buttons=_main_buttons(),
        )
    sess_payload = dict(session.payload_json)
    update_session(db, session.session_id, "committed", sess_payload, status="committed")

    machine_id = sess_payload.get("machine_id")
    size_ml = sess_payload.get("size_ml")
    boxes = sess_payload.get("boxes", 0)
    machine_name = sess_payload.get("machine_name", "?")

    if not machine_id or not size_ml or not boxes:
        return TelegramActionResult(
            message="⚠️ Incomplete data. Please start again.",
            buttons=_main_buttons(),
        )

    try:
        from schemas import DailyProductionCreate
        from routers.operations import create_daily_production
        from fastapi import BackgroundTasks
        from types import SimpleNamespace

        # Resolve a worker: use the first active worker for this factory as operator
        worker = (
            db.query(Worker)
            .filter(Worker.factory_id == str(factory_id), Worker.is_active.is_(True))
            .order_by(Worker.id.asc())
            .first()
        )
        if not worker:
            update_session(db, session.session_id, "failed", sess_payload, status="cancelled")
            return TelegramActionResult(
                message="⚠️ No active workers found. Please add workers first.",
                buttons=_main_buttons(),
            )

        today = get_kolkata_now().date()
        prod_payload = DailyProductionCreate(
            factory_id=str(factory_id),
            date=today,
            worker_id=worker.id,
            machine_id=machine_id,
            product_size_ml=size_ml,
            total_boxes_made=boxes,
            loose_packets_made=0,
        )
        # Synthesize a minimal user object the router function trusts
        fake_user = SimpleNamespace(
            id=owner.id if owner else 0,
            factory_id=factory_id,
            full_name=(owner.full_name or owner.username) if owner else "Telegram",
            username=owner.username if owner else "telegram",
            role=owner.role if owner else "Owner",
        )
        fake_bt = BackgroundTasks()
        create_daily_production(prod_payload, fake_bt, current_user=fake_user, db=db)

        _audit(
            db, factory_id, "A3_PRODUCTION_COMMITTED",
            f"Production recorded via Telegram: {boxes} boxes of {size_ml}ml on {machine_name}",
            user_id=owner.id if owner else None,
            user_name=(owner.full_name or owner.username) if owner else "telegram",
        )
        return TelegramActionResult(
            message=f"✅ *Production Recorded!*\n\n• Size: {size_ml} ml\n• Machine: {machine_name}\n• Boxes: {boxes}\n• Date: {today.isoformat()}",
            buttons=_main_buttons(),
        )

    except Exception as exc:
        logger.exception("Production commit failed factory_id=%s", factory_id)
        update_session(db, session.session_id, "failed", sess_payload, status="cancelled")
        safe_msg = str(exc)[:200] if str(exc) else "unknown error"
        return TelegramActionResult(
            message=f"❌ Failed to record production: {safe_msg}\n\nPlease use the app to record manually.",
            buttons=_main_buttons(),
        )


def handle_production_cancel(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_PRODUCTION)
    if session:
        update_session(db, session.session_id, "cancelled", {}, status="cancelled")
    _audit(db, factory_id, "A3_PRODUCTION_CANCELLED", "Production entry cancelled via Telegram")
    return TelegramActionResult(
        message="❌ Production entry cancelled.",
        buttons=_main_buttons(),
    )


# ---------------------------------------------------------------------------
# A4 – Attendance (guided, multi-step, requires confirmation)
# ---------------------------------------------------------------------------

ACTION_ATTENDANCE = "attendance"


def handle_attendance_start(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
) -> TelegramActionResult:
    """List active workers for selection."""
    workers = (
        db.query(Worker)
        .filter(Worker.factory_id == str(factory_id), Worker.is_active.is_(True))
        .order_by(Worker.name.asc())
        .limit(20)
        .all()
    )
    if not workers:
        return TelegramActionResult(
            message="⚠️ No active workers found. Please add workers first.",
            buttons=_main_buttons(),
        )
    create_session(db, factory_id, chat_id, ACTION_ATTENDANCE, "worker", {})
    _audit(db, factory_id, "A4_ATTENDANCE_START", "Started guided attendance entry via Telegram")
    worker_buttons = [[InlineButton(w.name[:30], f"A4:worker:{w.id}")] for w in workers]
    return TelegramActionResult(
        message="📅 *Mark Attendance*\n\nSelect a worker:",
        buttons=worker_buttons + [[InlineButton("❌ Cancel", "A4:cancel")]],
    )


def handle_attendance_worker(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    worker_id: int,
) -> TelegramActionResult:
    """Worker selected → ask status."""
    worker = (
        db.query(Worker)
        .filter(Worker.factory_id == str(factory_id), Worker.id == worker_id)
        .first()
    )
    if not worker:
        return TelegramActionResult(
            message="⚠️ Worker not found. Please start again.",
            buttons=[[InlineButton("🔙 Start Over", "A4:start"), InlineButton("❌ Cancel", "A4:cancel")]],
        )
    session = get_session(db, factory_id, chat_id, ACTION_ATTENDANCE)
    new_payload = {"worker_id": worker_id, "worker_name": worker.name}
    if session:
        update_session(db, session.session_id, "status", new_payload)
    else:
        create_session(db, factory_id, chat_id, ACTION_ATTENDANCE, "status", new_payload)

    return TelegramActionResult(
        message=f"✅ Worker: *{worker.name}*\n\nSelect attendance status:",
        buttons=[
            [
                InlineButton("✅ Present",  f"A4:status:Present:{worker_id}"),
                InlineButton("❌ Absent",   f"A4:status:Absent:{worker_id}"),
                InlineButton("½ Half-day", f"A4:status:Half-day:{worker_id}"),
            ],
            [InlineButton("❌ Cancel", "A4:cancel")],
        ],
    )


def handle_attendance_status(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    worker_id: int,
    attendance_status: str,
) -> TelegramActionResult:
    """Status selected → show confirmation."""
    if attendance_status not in ("Present", "Absent", "Half-day"):
        return TelegramActionResult(
            message="⚠️ Invalid status. Please start again.",
            buttons=_main_buttons(),
        )
    session = get_session(db, factory_id, chat_id, ACTION_ATTENDANCE)
    new_payload = dict(session.payload_json) if session else {}
    new_payload["worker_id"] = worker_id
    new_payload["status"] = attendance_status

    worker = (
        db.query(Worker)
        .filter(Worker.factory_id == str(factory_id), Worker.id == worker_id)
        .first()
    )
    worker_name = worker.name if worker else new_payload.get("worker_name", "?")
    new_payload["worker_name"] = worker_name

    if session:
        update_session(db, session.session_id, "confirm", new_payload)
    else:
        create_session(db, factory_id, chat_id, ACTION_ATTENDANCE, "confirm", new_payload)

    preview = format_attendance_preview(worker_name, attendance_status)
    return TelegramActionResult(
        message=preview,
        buttons=[
            [
                InlineButton("✅ Confirm", "A4:confirm"),
                InlineButton("❌ Cancel", "A4:cancel"),
            ]
        ],
    )


def handle_attendance_confirm(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    owner: Optional[User],
) -> TelegramActionResult:
    """Commit attendance."""
    session = get_session(db, factory_id, chat_id, ACTION_ATTENDANCE)
    if not session:
        return TelegramActionResult(
            message="⚠️ Session expired. Please start again.",
            buttons=_main_buttons(),
        )
    sess_payload = dict(session.payload_json)
    update_session(db, session.session_id, "committed", sess_payload, status="committed")

    worker_id = sess_payload.get("worker_id")
    worker_name = sess_payload.get("worker_name", "?")
    att_status = sess_payload.get("status", "Present")

    if not worker_id:
        return TelegramActionResult(
            message="⚠️ Incomplete data. Please start again.",
            buttons=_main_buttons(),
        )

    try:
        from routers.attendance import upsert_attendance, AttendanceUpsert
        from fastapi import BackgroundTasks
        from types import SimpleNamespace

        today = get_kolkata_now().date()
        att_payload = AttendanceUpsert(date=today, status=att_status)
        fake_user = SimpleNamespace(
            id=owner.id if owner else 0,
            factory_id=factory_id,
            full_name=(owner.full_name or owner.username) if owner else "Telegram",
            username=owner.username if owner else "telegram",
            role=owner.role if owner else "Owner",
        )
        fake_bt = BackgroundTasks()
        upsert_attendance(
            worker_id=worker_id,
            payload=att_payload,
            background_tasks=fake_bt,
            current_user=fake_user,
            db=db,
        )
        _audit(
            db, factory_id, "A4_ATTENDANCE_COMMITTED",
            f"Attendance marked {att_status} for {worker_name} on {today.isoformat()} via Telegram",
            user_id=owner.id if owner else None,
            user_name=(owner.full_name or owner.username) if owner else "telegram",
        )
        return TelegramActionResult(
            message=(
                f"✅ *Attendance Marked!*\n\n"
                f"• Worker: {worker_name}\n"
                f"• Status: {att_status}\n"
                f"• Date: {today.isoformat()}"
            ),
            buttons=_main_buttons(),
        )

    except Exception as exc:
        logger.exception("Attendance commit failed factory_id=%s", factory_id)
        update_session(db, session.session_id, "failed", sess_payload, status="cancelled")
        safe_msg = str(exc)[:200] if str(exc) else "unknown error"
        return TelegramActionResult(
            message=f"❌ Failed to mark attendance: {safe_msg}\n\nPlease use the app to record manually.",
            buttons=_main_buttons(),
        )


def handle_attendance_cancel(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_ATTENDANCE)
    if session:
        update_session(db, session.session_id, "cancelled", {}, status="cancelled")
    _audit(db, factory_id, "A4_ATTENDANCE_CANCELLED", "Attendance entry cancelled via Telegram")
    return TelegramActionResult(
        message="❌ Attendance entry cancelled.",
        buttons=_main_buttons(),
    )


# ---------------------------------------------------------------------------
# A5 – Full briefing
# ---------------------------------------------------------------------------

def handle_briefing_full(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    owner: Optional[User],
) -> TelegramActionResult:
    """Rebuild today's briefing on-demand (read-only, no AI)."""
    try:
        from services.briefing_service import build_briefing
        from services.timezone_utils import get_kolkata_now

        today = get_kolkata_now().date()
        briefing_date = today
        name = (owner.full_name or owner.username) if owner else "Factory"
        language = owner.preferred_language if (owner and hasattr(owner, "preferred_language")) else "hinglish"
        result = build_briefing(db, factory_id, briefing_date, name, language, summary_mode=False)
        text = result.get("message_text", "Briefing not available.")

    except Exception:
        logger.exception("Full briefing failed factory_id=%s", factory_id)
        text = "❌ Could not generate briefing. Please check the app."

    _audit(db, factory_id, "A5_BRIEFING_FULL", "Viewed full briefing via Telegram", user_name="telegram-action")
    # Telegram has a 4096 char message limit; truncate with indicator
    if len(text) > 4000:
        text = text[:3990] + "\n\n…(truncated)"
    return TelegramActionResult(message=text, buttons=_main_buttons())


# ---------------------------------------------------------------------------
# A6 – Ask Munshi (read-only stub)
# ---------------------------------------------------------------------------

def handle_ask_start(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
) -> TelegramActionResult:
    """
    Placeholder for conversational Q&A.
    Currently a read-only stub that redirects the user to the app.
    No queries are executed, no data modified.
    """
    _audit(db, factory_id, "A6_ASK_START", "Ask Munshi stub triggered via Telegram")
    return TelegramActionResult(
        message=(
            "🤖 *Ask Munshi*\n\n"
            "Conversational AI queries are coming soon!\n\n"
            "For now, please open the app to ask questions about your factory data."
        ),
        buttons=_main_buttons(),
    )


# ---------------------------------------------------------------------------
# Additional Read Actions (Role Masking & Services)
# ---------------------------------------------------------------------------

def handle_dashboard_summary_view(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    user: Optional[User],
) -> TelegramActionResult:
    from models import DailyProduction, OutstandingBill, SalesInvoice, UnifiedAlert, AttendanceLog, BillPayment
    from sqlalchemy import func
    from datetime import date
    
    today = date.today()
    
    boxes_today = db.query(func.coalesce(func.sum(DailyProduction.total_boxes_made), 0)).filter(
        DailyProduction.factory_id == str(factory_id),
        DailyProduction.date == today,
        DailyProduction.status == "ACTIVE"
    ).scalar() or 0
    
    workers_present = db.query(func.count(AttendanceLog.id)).filter(
        AttendanceLog.factory_id == factory_id,
        AttendanceLog.date == today,
        AttendanceLog.status == "Present"
    ).scalar() or 0
    
    open_alerts = db.query(func.count(UnifiedAlert.id)).filter(
        UnifiedAlert.factory_id == factory_id,
        UnifiedAlert.status == "OPEN"
    ).scalar() or 0

    is_sub_owner = user is not None and user.role == "Sub-Owner"
    
    if is_sub_owner:
        revenue_str = "[Masked]"
        collections_str = "[Masked]"
        outstanding_str = "[Masked]"
    else:
        revenue_today = db.query(func.coalesce(func.sum(SalesInvoice.total_amount), 0)).filter(
            SalesInvoice.factory_id == factory_id,
            SalesInvoice.date == today
        ).scalar() or 0
        revenue_str = f"₹{float(revenue_today):,.2f}"
        
        collections_today = db.query(func.coalesce(func.sum(BillPayment.amount_allocated), 0)).filter(
            BillPayment.factory_id == factory_id,
            BillPayment.payment_date == today
        ).scalar() or 0
        collections_str = f"₹{float(collections_today):,.2f}"
        
        outstanding_total = db.query(func.coalesce(func.sum(OutstandingBill.balance_amount), 0)).filter(
            OutstandingBill.factory_id == factory_id,
            OutstandingBill.status.in_(["active", "partial"])
        ).scalar() or 0
        outstanding_str = f"₹{float(outstanding_total):,.2f}"
        
    msg = (
        "📈 *Munshi AI Dashboard Summary*\n\n"
        f"• *Production Today:* {boxes_today} boxes\n"
        f"• *Workers Present:* {workers_present}\n"
        f"• *Open Alerts:* {open_alerts}\n"
        f"• *Today's Revenue:* {revenue_str}\n"
        f"• *Today's Collections:* {collections_str}\n"
        f"• *Total Outstanding:* {outstanding_str}"
    )
    _audit(db, factory_id, "A10_DASHBOARD_SUMMARY", "Viewed dashboard summary via Telegram", user_name="telegram-action")
    return TelegramActionResult(message=msg, buttons=_main_buttons())


def handle_inventory_rm_view(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
) -> TelegramActionResult:
    from models import BlankStock, BottomStock, BoxStock
    
    blanks = db.query(BlankStock).filter(BlankStock.factory_id == str(factory_id)).all()
    bottoms = db.query(BottomStock).filter(BottomStock.factory_id == str(factory_id)).all()
    boxes = db.query(BoxStock).filter(BoxStock.factory_id == str(factory_id)).all()
    
    lines = ["📦 *Raw Material Stock Levels*", ""]
    
    if blanks:
        lines.append("*Blanks:*")
        for b in blanks[:5]:
            qty = (b.total_boras or 0) * (b.weight_per_bora_kg or 0) if (b.total_boras or 0) > 0 else (b.total_qty_kg or 0)
            lines.append(f"• {b.blank_size_ml}ml ({b.variety or 'Plain'}): {float(qty):,.1f} kg ({b.total_boras or 0} boras)")
            
    if bottoms:
        lines.append("\n*Bottom Rolls:*")
        for b in bottoms[:5]:
            lines.append(f"• {b.bottom_size_mm}mm ({b.variety or 'Plain'}): {float(b.total_qty_kg or 0):,.1f} kg ({b.total_rolls or 0} rolls)")
            
    if boxes:
        lines.append("\n*Boxes / Cartons:*")
        for b in boxes[:5]:
            lines.append(f"• {b.box_type or b.packaging_size_name}: {b.quantity or 0} pcs")
            
    if not blanks and not bottoms and not boxes:
        lines.append("No raw material inventory found.")
        
    _audit(db, factory_id, "A2_INVENTORY_RM_VIEW", "Viewed raw material stock via Telegram", user_name="telegram-action")
    return TelegramActionResult(message="\n".join(lines), buttons=_main_buttons())


def handle_inventory_fg_view(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
) -> TelegramActionResult:
    from models import FinalProductStock
    from routers.inventory import calculate_live_sku_stock
    
    fg_items = db.query(FinalProductStock).filter(FinalProductStock.factory_id == str(factory_id)).all()
    lines = ["📦 *Finished Goods Stock Levels*", ""]
    
    for item in fg_items[:15]:
        live_boxes, live_loose = calculate_live_sku_stock(
            db=db,
            factory_id=str(factory_id),
            product_size_ml=item.product_size_ml,
            variety=item.variety,
            packaging_size_name=item.packaging_size_name,
            onboarding_boxes=item.total_boxes or 0,
            onboarding_loose=item.loose_packets or 0,
            packets_per_box_limit=item.packets_per_box_limit or 1000,
        )
        lines.append(f"• *{item.product_size_ml}ml {item.variety}* ({item.packaging_size_name}): {live_boxes} boxes")
        
    if not fg_items:
        lines.append("No finished goods stock found.")
        
    _audit(db, factory_id, "A2_INVENTORY_FG_VIEW", "Viewed finished goods stock via Telegram", user_name="telegram-action")
    return TelegramActionResult(message="\n".join(lines), buttons=_main_buttons())


def handle_production_summary_view(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
) -> TelegramActionResult:
    from models import DailyProduction
    from datetime import date
    
    today = date.today()
    prods = db.query(DailyProduction).filter(
        DailyProduction.factory_id == str(factory_id),
        DailyProduction.date == today,
        DailyProduction.status == "ACTIVE"
    ).all()
    
    lines = ["📋 *Today's Production Summary*", f"Date: {today.isoformat()}", ""]
    for p in prods:
        m_name = p.machine.name if p.machine else f"Machine {p.machine_id}"
        w_name = p.worker.name if p.worker else "Unknown"
        lines.append(f"• *{p.product_size_ml}ml* on {m_name} (Worker: {w_name}): {p.total_boxes_made} boxes")
        
    if not prods:
        lines.append("No production recorded today yet.")
        
    _audit(db, factory_id, "A11_PRODUCTION_VIEW", "Viewed daily production summary via Telegram", user_name="telegram-action")
    return TelegramActionResult(message="\n".join(lines), buttons=_main_buttons())


def handle_attendance_summary_view(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
) -> TelegramActionResult:
    from models import AttendanceLog
    from datetime import date
    
    today = date.today()
    records = db.query(AttendanceLog).filter(
        AttendanceLog.factory_id == factory_id,
        AttendanceLog.date == today
    ).all()
    
    lines = ["📅 *Today's Attendance Summary*", f"Date: {today.isoformat()}", ""]
    p_count = sum(1 for r in records if r.status == "Present")
    a_count = sum(1 for r in records if r.status == "Absent")
    h_count = sum(1 for r in records if r.status == "Half-day")
    
    lines.append(f"• *Present:* {p_count}")
    lines.append(f"• *Absent:* {a_count}")
    lines.append(f"• *Half-day:* {h_count}")
    lines.append("")
    lines.append("*Details:*")
    for r in records:
        w_name = r.worker.name if r.worker else f"Worker {r.worker_id}"
        lines.append(f"• {w_name}: {r.status}")
        
    if not records:
        lines.append("No attendance marked today.")
        
    _audit(db, factory_id, "A4_ATTENDANCE_SUMMARY_VIEW", "Viewed worker attendance via Telegram", user_name="telegram-action")
    return TelegramActionResult(message="\n".join(lines), buttons=_main_buttons())


def handle_invoices_search_start(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    user: Optional[User],
) -> TelegramActionResult:
    if user and user.role == "Sub-Owner":
        return TelegramActionResult(message="⚠️ Unauthorized: Financial access restricted.", buttons=_main_buttons())
        
    create_session(db, factory_id, chat_id, "invoices", "search_query", {})
    return TelegramActionResult(
        message="🧾 *Search Invoices*\n\nPlease reply directly to this message or send the Customer Name or Invoice Number to search.",
        buttons=[[InlineButton("❌ Cancel", "A12:cancel")]],
    )


def handle_invoices_search_query(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    query_text: str,
    user: Optional[User],
) -> TelegramActionResult:
    if user and user.role == "Sub-Owner":
        return TelegramActionResult(message="⚠️ Unauthorized: Financial access restricted.", buttons=_main_buttons())
        
    from models import SalesInvoice, Customer
    from sqlalchemy import or_
    
    invoices = db.query(SalesInvoice).filter(
        SalesInvoice.factory_id == factory_id
    ).filter(
        or_(
            SalesInvoice.invoice_number.ilike(f"%{query_text}%"),
            SalesInvoice.customer.has(Customer.name.ilike(f"%{query_text}%"))
        )
    ).order_by(SalesInvoice.date.desc()).limit(5).all()
    
    lines = [f"🧾 *Invoice Search Results for '{query_text}':*", ""]
    for inv in invoices:
        c_name = inv.customer.name if inv.customer else "Unknown"
        lines.append(
            f"• *{inv.invoice_number}* - {c_name}\n"
            f"  Date: {inv.date.isoformat()} | Amount: ₹{float(inv.total_amount):,.2f}\n"
            f"  [PDF Download](https://munshiai.co.in/api/invoices/{inv.id}/pdf)"
        )
        
    if not invoices:
        lines.append("No matching invoices found.")
        
    _audit(db, factory_id, "A12_INVOICE_SEARCH", f"Searched invoices for query: {query_text}", user_name="telegram-action")
    return TelegramActionResult(message="\n".join(lines), buttons=_main_buttons())


def handle_payments_summary_view(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    user: Optional[User],
) -> TelegramActionResult:
    if user and user.role == "Sub-Owner":
        return TelegramActionResult(message="⚠️ Unauthorized: Financial access restricted.", buttons=_main_buttons())
        
    from models import BillPayment
    from datetime import date
    
    today = date.today()
    payments = db.query(BillPayment).filter(
        BillPayment.factory_id == factory_id,
        BillPayment.payment_date == today
    ).all()
    
    lines = ["💸 *Today's Collection Summary*", f"Date: {today.isoformat()}", ""]
    total = sum(p.amount_allocated for p in payments)
    lines.append(f"Total Collections: *₹{float(total):,.2f}*")
    lines.append("")
    
    for p in payments:
        cust_name = p.bill.customer.name if p.bill and p.bill.customer else "Unknown"
        lines.append(f"• {cust_name}: ₹{float(p.amount_allocated):,.2f} (Received by: {p.received_by_name or 'System'})")
        
    if not payments:
        lines.append("No payment collection recorded today.")
        
    _audit(db, factory_id, "A13_PAYMENT_VIEW", "Viewed payment collection summary via Telegram", user_name="telegram-action")
    return TelegramActionResult(message="\n".join(lines), buttons=_main_buttons())


def handle_wastage_summary_view(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
) -> TelegramActionResult:
    from models import ShiftWastage
    from datetime import date
    
    today = date.today()
    records = db.query(ShiftWastage).filter(
        ShiftWastage.factory_id == factory_id,
        ShiftWastage.date == today
    ).all()
    
    lines = ["🗑️ *Today's Wastage Summary*", f"Date: {today.isoformat()}", ""]
    day_w = sum(r.wastage_kg for r in records if r.shift.lower() == "day")
    night_w = sum(r.wastage_kg for r in records if r.shift.lower() == "night")
    
    lines.append(f"• *Day Shift:* {float(day_w):,.3f} kg")
    lines.append(f"• *Night Shift:* {float(night_w):,.3f} kg")
    lines.append(f"• *Total Wastage:* {float(day_w + night_w):,.3f} kg")
    
    _audit(db, factory_id, "A14_WASTAGE_VIEW", "Viewed wastage summary via Telegram", user_name="telegram-action")
    return TelegramActionResult(message="\n".join(lines), buttons=_main_buttons())


# ---------------------------------------------------------------------------
# Additional Write Actions (State Machines, Confirm/Rollback)
# ---------------------------------------------------------------------------

ACTION_WASTAGE = "wastage"

def handle_wastage_start(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
) -> TelegramActionResult:
    create_session(db, factory_id, chat_id, ACTION_WASTAGE, "shift", {})
    return TelegramActionResult(
        message="🗑️ *Record Shift Wastage*\n\nSelect Shift:",
        buttons=[
            [InlineButton("☀️ Day", "W2:shift:Day"), InlineButton("🌙 Night", "W2:shift:Night")],
            [InlineButton("❌ Cancel", "W2:cancel")]
        ]
    )

def handle_wastage_shift(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    shift: str,
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_WASTAGE)
    new_payload = dict(session.payload_json) if session else {}
    new_payload["shift"] = shift
    update_session(db, session.session_id if session else None, "kg", new_payload)
    
    return TelegramActionResult(
        message=f"✅ Shift: *{shift}*\n\nSelect wastage amount (kg):",
        buttons=[
            [InlineButton("5 kg", "W2:kg:5"), InlineButton("10 kg", "W2:kg:10"), InlineButton("15 kg", "W2:kg:15")],
            [InlineButton("20 kg", "W2:kg:20"), InlineButton("25 kg", "W2:kg:25"), InlineButton("30 kg", "W2:kg:30")],
            [InlineButton("❌ Cancel", "W2:cancel")]
        ]
    )

def handle_wastage_kg(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    kg: float,
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_WASTAGE)
    if not session:
        return TelegramActionResult(message="⚠️ Session expired.", buttons=_main_buttons())
    new_payload = dict(session.payload_json)
    new_payload["wastage_kg"] = kg
    update_session(db, session.session_id, "confirm", new_payload)
    
    preview = (
        "📝 *Confirm Wastage Entry*\n\n"
        f"• *Shift:* {new_payload.get('shift')}\n"
        f"• *Weight:* {kg} kg\n\n"
        "Do you want to confirm this entry?"
    )
    return TelegramActionResult(
        message=preview,
        buttons=[
            [InlineButton("✅ Confirm", "W2:confirm"), InlineButton("❌ Cancel", "W2:cancel")]
        ]
    )

def handle_wastage_confirm(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    user: Optional[User],
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_WASTAGE)
    if not session:
        return TelegramActionResult(message="⚠️ Session expired.", buttons=_main_buttons())
    
    sess_payload = dict(session.payload_json)
    update_session(db, session.session_id, "committed", sess_payload, status="committed")
    
    shift = sess_payload.get("shift")
    kg = sess_payload.get("wastage_kg", 0)
    
    try:
        from models import ShiftWastage
        from datetime import date
        from decimal import Decimal
        today = date.today()
        
        existing = db.query(ShiftWastage).filter(
            ShiftWastage.factory_id == factory_id,
            ShiftWastage.date == today,
            ShiftWastage.shift == shift
        ).first()
        
        if existing:
            existing.wastage_kg = Decimal(str(kg))
        else:
            db.add(ShiftWastage(
                factory_id=factory_id,
                date=today,
                shift=shift,
                wastage_kg=Decimal(str(kg))
            ))
        db.flush()
        
        _audit(
            db, factory_id, "W2_WASTAGE_COMMITTED",
            f"Wastage recorded via Telegram: {kg} kg for {shift} shift",
            user_id=user.id if user else None,
            user_name=user.username if user else "telegram"
        )
        return TelegramActionResult(
            message=f"✅ *Wastage Recorded!*\n\n• Shift: {shift}\n• Weight: {kg} kg\n• Date: {today.isoformat()}",
            buttons=_main_buttons()
        )
    except Exception as exc:
        logger.exception("Wastage commit failed")
        update_session(db, session.session_id, "failed", sess_payload, status="cancelled")
        return TelegramActionResult(message=f"❌ Error: {str(exc)[:100]}", buttons=_main_buttons())

def handle_wastage_cancel(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_WASTAGE)
    if session:
        update_session(db, session.session_id, "cancelled", {}, status="cancelled")
    return TelegramActionResult(message="❌ Wastage entry cancelled.", buttons=_main_buttons())


ACTION_INVOICE = "invoice"

def handle_invoice_start(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    user: Optional[User],
) -> TelegramActionResult:
    if user and user.role == "Sub-Owner":
        return TelegramActionResult(message="⚠️ Unauthorized: Financial access restricted.", buttons=_main_buttons())
        
    from models import Customer
    customers = db.query(Customer).filter(Customer.factory_id == factory_id).limit(5).all()
    if not customers:
        return TelegramActionResult(message="⚠️ No customers found.", buttons=_main_buttons())
        
    create_session(db, factory_id, chat_id, ACTION_INVOICE, "customer", {})
    buttons = [[InlineButton(c.name, f"W3:customer:{c.id}")] for c in customers]
    return TelegramActionResult(
        message="🧾 *Create Invoice*\n\nSelect Customer:",
        buttons=buttons + [[InlineButton("❌ Cancel", "W3:cancel")]]
    )

def handle_invoice_customer(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    customer_id: int,
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_INVOICE)
    new_payload = dict(session.payload_json) if session else {}
    new_payload["customer_id"] = customer_id
    
    from models import Customer
    cust = db.query(Customer).filter(Customer.id == customer_id, Customer.factory_id == factory_id).first()
    new_payload["customer_name"] = cust.name if cust else "Unknown"
    update_session(db, session.session_id if session else None, "size", new_payload)
    
    from models import Machine
    sizes = db.query(Machine.mould_size_ml).filter(Machine.factory_id == str(factory_id)).distinct().all()
    buttons = [[InlineButton(f"{r[0]} ml", f"W3:size:{r[0]}")] for r in sizes if r[0]]
    return TelegramActionResult(
        message=f"✅ Customer: *{new_payload['customer_name']}*\n\nSelect cup size:",
        buttons=buttons + [[InlineButton("❌ Cancel", "W3:cancel")]]
    )

def handle_invoice_size(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    size: int,
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_INVOICE)
    new_payload = dict(session.payload_json) if session else {}
    new_payload["size_ml"] = size
    update_session(db, session.session_id if session else None, "boxes", new_payload)
    
    return TelegramActionResult(
        message=f"✅ Size: *{size} ml*\n\nSelect quantity (boxes):",
        buttons=[
            [InlineButton("10 boxes", "W3:boxes:10"), InlineButton("20 boxes", "W3:boxes:20")],
            [InlineButton("50 boxes", "W3:boxes:50"), InlineButton("100 boxes", "W3:boxes:100")],
            [InlineButton("❌ Cancel", "W3:cancel")]
        ]
    )

def handle_invoice_boxes(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    boxes: int,
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_INVOICE)
    if not session:
        return TelegramActionResult(message="⚠️ Session expired.", buttons=_main_buttons())
    new_payload = dict(session.payload_json)
    new_payload["boxes"] = boxes
    update_session(db, session.session_id, "confirm", new_payload)
    
    preview = (
        "📝 *Confirm Invoice Creation*\n\n"
        f"• *Customer:* {new_payload.get('customer_name')}\n"
        f"• *Cup Size:* {new_payload.get('size_ml')} ml\n"
        f"• *Boxes:* {boxes}\n\n"
        "Do you want to confirm invoice creation?"
    )
    return TelegramActionResult(
        message=preview,
        buttons=[
            [InlineButton("✅ Confirm", "W3:confirm"), InlineButton("❌ Cancel", "W3:cancel")]
        ]
    )

def handle_invoice_confirm(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    user: Optional[User],
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_INVOICE)
    if not session:
        return TelegramActionResult(message="⚠️ Session expired.", buttons=_main_buttons())
        
    sess_payload = dict(session.payload_json)
    update_session(db, session.session_id, "committed", sess_payload, status="committed")
    
    customer_id = sess_payload.get("customer_id")
    size_ml = sess_payload.get("size_ml")
    boxes = sess_payload.get("boxes", 0)
    
    try:
        from models import SalesInvoice, PackagingProfile
        from datetime import date
        from decimal import Decimal
        
        profile = db.query(PackagingProfile).filter(
            PackagingProfile.factory_id == str(factory_id),
            PackagingProfile.cup_size_ml == size_ml
        ).first()
        
        if not profile:
            return TelegramActionResult(message="⚠️ Packaging profile not found for size.", buttons=_main_buttons())
            
        today = date.today()
        import random
        invoice_num = f"INV-{today.strftime('%Y%m%d')}-{random.randint(100, 999)}"
        invoice = SalesInvoice(
            factory_id=factory_id,
            customer_id=customer_id,
            invoice_number=invoice_num,
            date=today,
            cup_size_ml=size_ml,
            packaging_profile_id=profile.id,
            boxes_sold=boxes,
            total_amount=Decimal(str(boxes * 1200)),
            amount_paid=Decimal("0.00"),
            payment_status="Unpaid"
        )
        db.add(invoice)
        db.flush()
        
        from models import OutstandingBill
        bill = OutstandingBill(
            factory_id=factory_id,
            customer_id=customer_id,
            sales_invoice_id=invoice.id,
            bill_date=today,
            total_amount=invoice.total_amount,
            balance_amount=invoice.total_amount,
            status="active"
        )
        db.add(bill)
        db.flush()
        
        _audit(
            db, factory_id, "W3_INVOICE_COMMITTED",
            f"Created Sales Invoice {invoice_num} for customer {sess_payload.get('customer_name')}",
            user_id=user.id if user else None,
            user_name=user.username if user else "telegram"
        )
        
        return TelegramActionResult(
            message=f"✅ *Invoice Created!*\n\n• Invoice: {invoice_num}\n• Customer: {sess_payload.get('customer_name')}\n• Amount: ₹{float(invoice.total_amount):,.2f}",
            buttons=_main_buttons()
        )
    except Exception as exc:
        logger.exception("Invoice creation failed")
        update_session(db, session.session_id, "failed", sess_payload, status="cancelled")
        return TelegramActionResult(message=f"❌ Error: {str(exc)[:100]}", buttons=_main_buttons())

def handle_invoice_cancel(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_INVOICE)
    if session:
        update_session(db, session.session_id, "cancelled", {}, status="cancelled")
    return TelegramActionResult(message="❌ Invoice creation cancelled.", buttons=_main_buttons())


ACTION_PAYMENT = "payment"

def handle_payment_start(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    user: Optional[User],
) -> TelegramActionResult:
    if user and user.role == "Sub-Owner":
        return TelegramActionResult(message="⚠️ Unauthorized: Financial access restricted.", buttons=_main_buttons())
        
    from models import Customer, OutstandingBill
    
    customers = db.query(Customer).join(OutstandingBill).filter(
        OutstandingBill.factory_id == factory_id,
        OutstandingBill.balance_amount > 0,
        OutstandingBill.status.in_(["active", "partial"])
    ).group_by(Customer.id).limit(5).all()
    
    if not customers:
        return TelegramActionResult(message="⚠️ No customers with outstanding balance found.", buttons=_main_buttons())
        
    create_session(db, factory_id, chat_id, ACTION_PAYMENT, "customer", {})
    buttons = [[InlineButton(c.name, f"W4:customer:{c.id}")] for c in customers]
    return TelegramActionResult(
        message="💰 *Record Collection*\n\nSelect Customer:",
        buttons=buttons + [[InlineButton("❌ Cancel", "W4:cancel")]]
    )

def handle_payment_customer(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    customer_id: int,
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_PAYMENT)
    new_payload = dict(session.payload_json) if session else {}
    new_payload["customer_id"] = customer_id
    
    from models import Customer
    cust = db.query(Customer).filter(Customer.id == customer_id, Customer.factory_id == factory_id).first()
    new_payload["customer_name"] = cust.name if cust else "Unknown"
    
    from models import OutstandingBill
    from sqlalchemy import func
    total_due = db.query(func.coalesce(func.sum(OutstandingBill.balance_amount), 0)).filter(
        OutstandingBill.customer_id == customer_id,
        OutstandingBill.factory_id == factory_id,
        OutstandingBill.status.in_(["active", "partial"])
    ).scalar() or 0
    
    new_payload["total_due"] = float(total_due)
    update_session(db, session.session_id if session else None, "amount", new_payload)
    
    return TelegramActionResult(
        message=f"👤 Customer: *{new_payload['customer_name']}*\nOutstanding Balance: *₹{float(total_due):,.2f}*\n\nSelect payment amount:",
        buttons=[
            [InlineButton("₹5,000", "W4:amount:5000"), InlineButton("₹10,000", "W4:amount:10000")],
            [InlineButton("₹20,000", "W4:amount:20000"), InlineButton("₹50,000", "W4:amount:50000")],
            [InlineButton("❌ Cancel", "W4:cancel")]
        ]
    )

def handle_payment_amount(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    amount: float,
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_PAYMENT)
    if not session:
        return TelegramActionResult(message="⚠️ Session expired.", buttons=_main_buttons())
    new_payload = dict(session.payload_json)
    new_payload["amount"] = amount
    update_session(db, session.session_id, "confirm", new_payload)
    
    preview = (
        "📝 *Confirm Payment Collection*\n\n"
        f"• *Customer:* {new_payload.get('customer_name')}\n"
        f"• *Amount:* ₹{amount:,.2f}\n\n"
        "Do you want to confirm this payment?"
    )
    return TelegramActionResult(
        message=preview,
        buttons=[
            [InlineButton("✅ Confirm", "W4:confirm"), InlineButton("❌ Cancel", "W4:cancel")]
        ]
    )

def handle_payment_confirm(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    user: Optional[User],
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_PAYMENT)
    if not session:
        return TelegramActionResult(message="⚠️ Session expired.", buttons=_main_buttons())
        
    sess_payload = dict(session.payload_json)
    update_session(db, session.session_id, "committed", sess_payload, status="committed")
    
    customer_id = sess_payload.get("customer_id")
    amount = Decimal(str(sess_payload.get("amount", 0)))
    
    try:
        from models import OutstandingBill, BillPayment
        from datetime import date
        from decimal import Decimal
        
        bills = db.query(OutstandingBill).filter(
            OutstandingBill.customer_id == customer_id,
            OutstandingBill.factory_id == factory_id,
            OutstandingBill.balance_amount > 0,
            OutstandingBill.status.in_(["active", "partial"])
        ).order_by(OutstandingBill.bill_date.asc()).all()
        
        remaining = amount
        today = date.today()
        
        for bill in bills:
            if remaining <= 0:
                break
            allocation = min(bill.balance_amount, remaining)
            bill.balance_amount -= allocation
            if bill.balance_amount == 0:
                bill.status = "paid"
            else:
                bill.status = "partial"
                
            db.add(BillPayment(
                factory_id=factory_id,
                bill_id=bill.id,
                amount_allocated=allocation,
                payment_date=today,
                received_by_name=user.username if user else "Telegram"
            ))
            remaining -= allocation
            
        db.flush()
        
        _audit(
            db, factory_id, "W4_PAYMENT_COMMITTED",
            f"Recorded payment of ₹{float(amount):,.2f} for customer {sess_payload.get('customer_name')}",
            user_id=user.id if user else None,
            user_name=user.username if user else "telegram"
        )
        
        return TelegramActionResult(
            message=f"✅ *Payment Recorded!*\n\n• Customer: {sess_payload.get('customer_name')}\n• Amount: ₹{float(amount):,.2f}",
            buttons=_main_buttons()
        )
    except Exception as exc:
        logger.exception("Payment commit failed")
        update_session(db, session.session_id, "failed", sess_payload, status="cancelled")
        return TelegramActionResult(message=f"❌ Error: {str(exc)[:100]}", buttons=_main_buttons())

def handle_payment_cancel(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_PAYMENT)
    if session:
        update_session(db, session.session_id, "cancelled", {}, status="cancelled")
    return TelegramActionResult(message="❌ Payment entry cancelled.", buttons=_main_buttons())


ACTION_EDIT_PRODUCTION = "edit_production"

def handle_edit_production_start(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
) -> TelegramActionResult:
    from models import DailyProduction
    
    prods = db.query(DailyProduction).filter(
        DailyProduction.factory_id == str(factory_id),
        DailyProduction.status == "ACTIVE"
    ).order_by(DailyProduction.date.desc(), DailyProduction.id.desc()).limit(3).all()
    
    if not prods:
        return TelegramActionResult(message="⚠️ No recent active production entries found.", buttons=_main_buttons())
        
    create_session(db, factory_id, chat_id, ACTION_EDIT_PRODUCTION, "select", {})
    buttons = []
    for p in prods:
        m_name = p.machine.name if p.machine else f"Machine {p.machine_id}"
        label = f"{p.date.strftime('%d-%b')} | {p.product_size_ml}ml | {m_name} ({p.total_boxes_made} boxes)"
        buttons.append([InlineButton(label, f"W5:prod:{p.id}")])
        
    return TelegramActionResult(
        message="✏️ *Edit Daily Production*\n\nSelect entry to update:",
        buttons=buttons + [[InlineButton("❌ Cancel", "W5:cancel")]]
    )

def handle_edit_production_select(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    prod_id: int,
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_EDIT_PRODUCTION)
    new_payload = dict(session.payload_json) if session else {}
    new_payload["prod_id"] = prod_id
    
    from models import DailyProduction
    p = db.query(DailyProduction).filter(DailyProduction.id == prod_id, DailyProduction.factory_id == str(factory_id)).first()
    if not p:
        return TelegramActionResult(message="⚠️ Entry not found.", buttons=_main_buttons())
        
    m_name = p.machine.name if p.machine else f"Machine {p.machine_id}"
    new_payload["old_boxes"] = p.total_boxes_made
    new_payload["label"] = f"{p.date.strftime('%d-%b')} | {p.product_size_ml}ml | {m_name}"
    
    new_payload["product_size_ml"] = p.product_size_ml
    new_payload["variety"] = p.variety
    new_payload["packaging_size_name"] = p.packaging_size_name
    
    update_session(db, session.session_id if session else None, "new_boxes", new_payload)
    
    return TelegramActionResult(
        message=f"✏️ Entry: *{new_payload['label']}*\nCurrent Boxes: *{p.total_boxes_made}*\n\nSelect new boxes quantity:",
        buttons=[
            [InlineButton("25 boxes", "W5:boxes:25"), InlineButton("50 boxes", "W5:boxes:50")],
            [InlineButton("100 boxes", "W5:boxes:100"), InlineButton("200 boxes", "W5:boxes:200")],
            [InlineButton("❌ Cancel", "W5:cancel")]
        ]
    )

def handle_edit_production_boxes(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    boxes: int,
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_EDIT_PRODUCTION)
    if not session:
        return TelegramActionResult(message="⚠️ Session expired.", buttons=_main_buttons())
    new_payload = dict(session.payload_json)
    new_payload["new_boxes"] = boxes
    update_session(db, session.session_id, "confirm", new_payload)
    
    preview = (
        "📝 *Confirm Production Update*\n\n"
        f"• *Entry:* {new_payload.get('label')}\n"
        f"• *Old Boxes:* {new_payload.get('old_boxes')}\n"
        f"• *New Boxes:* {boxes}\n\n"
        "Do you want to confirm this update?"
    )
    return TelegramActionResult(
        message=preview,
        buttons=[
            [InlineButton("✅ Confirm", "W5:confirm"), InlineButton("❌ Cancel", "W5:cancel")]
        ]
    )

def handle_edit_production_confirm(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
    user: Optional[User],
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_EDIT_PRODUCTION)
    if not session:
        return TelegramActionResult(message="⚠️ Session expired.", buttons=_main_buttons())
        
    sess_payload = dict(session.payload_json)
    update_session(db, session.session_id, "committed", sess_payload, status="committed")
    
    prod_id = sess_payload.get("prod_id")
    new_boxes = sess_payload.get("new_boxes", 0)
    old_boxes = sess_payload.get("old_boxes", 0)
    
    try:
        from models import DailyProduction
        p = db.query(DailyProduction).filter(DailyProduction.id == prod_id, DailyProduction.factory_id == str(factory_id)).first()
        if not p:
            return TelegramActionResult(message="⚠️ Entry not found.", buttons=_main_buttons())
            
        p.total_boxes_made = new_boxes
        db.flush()
        
        from routers.inventory import recalculate_and_sync_sku_stock
        recalculate_and_sync_sku_stock(
            db=db,
            factory_id=str(factory_id),
            product_size_ml=sess_payload.get("product_size_ml"),
            variety=sess_payload.get("variety"),
            packaging_size_name=sess_payload.get("packaging_size_name")
        )
        
        _audit(
            db, factory_id, "W5_PRODUCTION_EDITED",
            f"Updated Daily Production ID {prod_id} boxes from {old_boxes} to {new_boxes}",
            user_id=user.id if user else None,
            user_name=user.username if user else "telegram"
        )
        
        return TelegramActionResult(
            message=f"✅ *Production Updated!*\n\n• Entry: {sess_payload.get('label')}\n• New Quantity: {new_boxes} boxes",
            buttons=_main_buttons()
        )
    except Exception as exc:
        logger.exception("Production edit failed")
        update_session(db, session.session_id, "failed", sess_payload, status="cancelled")
        return TelegramActionResult(message=f"❌ Error: {str(exc)[:100]}", buttons=_main_buttons())

def handle_edit_production_cancel(
    db: Session,
    factory_id: int,
    chat_id: str,
    payload: Dict[str, Any],
) -> TelegramActionResult:
    session = get_session(db, factory_id, chat_id, ACTION_EDIT_PRODUCTION)
    if session:
        update_session(db, session.session_id, "cancelled", {}, status="cancelled")
    return TelegramActionResult(message="❌ Production update cancelled.", buttons=_main_buttons())


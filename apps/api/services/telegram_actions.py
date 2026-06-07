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
        for bill in bills:
            if not bill.customer:
                continue
            cid = bill.customer.id
            if cid not in customer_map:
                customer_map[cid] = SimpleNamespace(
                    customer_name=bill.customer.name,
                    current_pending_balance=Decimal("0.00"),
                )
            customer_map[cid].current_pending_balance += Decimal(str(bill.balance_amount or 0))
            grand_total += Decimal(str(bill.balance_amount or 0))

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

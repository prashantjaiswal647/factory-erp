"""
Telegram Action Router — P4.1

POST /api/v1/telegram/action

Accepts Telegram callback_query payloads from n8n (or the bot webhook bridge),
resolves the factory from chat_id, enforces deduplication, dispatches to the
correct service handler, and sends the reply text back.

Security:
  - Protected by X-N8N-API-KEY (same guard as all n8n bridge endpoints)
  - chat_id MUST map to a verified factory.telegram_chat_id; unknowns → reject
  - callback_id deduplication prevents replay of the same button press
  - Mutating actions (A3, A4) require explicit confirm step via session state
  - All callbacks are audit-logged to ActivityLog

No new business endpoints are added; all data operations are delegated to
existing service functions from routers/operations.py and routers/attendance.py.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from datetime import date

from models import Customer, Factory, OutstandingBill, User, TelegramUserBinding
from routers.integrations import require_n8n_api_key
from services.telegram_callback_dedupe import dedupe_check
from services.telegram_actions import (
    _audit,
    _main_buttons,
    TelegramActionResult,
    InlineButton,
    handle_outstanding_view,
    handle_inventory_view,
    handle_production_start,
    handle_production_size,
    handle_production_machine,
    handle_production_boxes,
    handle_production_confirm,
    handle_production_cancel,
    handle_attendance_start,
    handle_attendance_worker,
    handle_attendance_status,
    handle_attendance_confirm,
    handle_attendance_cancel,
    handle_briefing_full,
    handle_ask_start,
    handle_dashboard_summary_view,
    handle_inventory_rm_view,
    handle_inventory_fg_view,
    handle_production_summary_view,
    handle_attendance_summary_view,
    handle_invoices_search_start,
    handle_invoices_search_query,
    handle_payments_summary_view,
    handle_wastage_summary_view,
    handle_wastage_start,
    handle_wastage_shift,
    handle_wastage_kg,
    handle_wastage_confirm,
    handle_wastage_cancel,
    handle_invoice_start,
    handle_invoice_customer,
    handle_invoice_size,
    handle_invoice_boxes,
    handle_invoice_confirm,
    handle_invoice_cancel,
    handle_payment_start,
    handle_payment_customer,
    handle_payment_amount,
    handle_payment_confirm,
    handle_payment_cancel,
    handle_edit_production_start,
    handle_edit_production_select,
    handle_edit_production_boxes,
    handle_edit_production_confirm,
    handle_edit_production_cancel,
)
from telegram_crypto import decrypt_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["telegram-actions"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TelegramActionRequest(BaseModel):
    """Payload sent by n8n / Telegram bridge on each callback_query."""
    callback_id: str = Field(..., max_length=128, description="Unique Telegram callback_query.id")
    chat_id: str = Field(..., max_length=64, description="Telegram chat.id as string")
    callback_data: str = Field(..., max_length=256, description="Data field from InlineKeyboardButton")
    bot_token: Optional[str] = Field(default=None, max_length=255)


class TelegramActionResponse(BaseModel):
    status: str                   # "ok" | "error" | "duplicate"
    message: Optional[str] = None
    action: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_inline_keyboard(buttons: List[List[InlineButton]]) -> List[List[Dict[str, str]]]:
    """Convert our domain buttons to Telegram API inline_keyboard format."""
    return [
        [{"text": b.text, "callback_data": b.callback_data} for b in row]
        for row in buttons
    ]


def _send_reply(
    factory: Factory,
    chat_id: str,
    result: TelegramActionResult,
) -> None:
    """Send a Telegram message with optional inline keyboard."""
    token = decrypt_token(factory.telegram_token) if factory.telegram_token else (factory.telegram_bot_token or "")
    if not token:
        logger.warning("No Telegram token for factory_id=%s, reply not sent", factory.id)
        return

    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": result.message,
        "parse_mode": "Markdown",
    }
    if result.buttons:
        payload["reply_markup"] = {"inline_keyboard": _build_inline_keyboard(result.buttons)}

    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
            timeout=15.0,
        )
        if not resp.json().get("ok"):
            logger.warning("Telegram sendMessage failed: %s", resp.text[:200])
    except Exception:
        logger.exception("Telegram reply send failed factory_id=%s chat_id=%s", factory.id, chat_id)


def _answer_callback(factory: Factory, callback_id: str, text: str = "") -> None:
    """answerCallbackQuery — removes the loading spinner on the button."""
    token = decrypt_token(factory.telegram_token) if factory.telegram_token else (factory.telegram_bot_token or "")
    if not token:
        return
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json={"callback_query_id": callback_id, "text": text},
            timeout=10.0,
        )
    except Exception:
        logger.debug("answerCallbackQuery failed callback_id=%s", callback_id)


def _resolve_factory(db: Session, chat_id: str) -> Optional[Factory]:
    """Resolve the factory associated with a given Telegram chat_id."""
    return (
        db.query(Factory)
        .filter(Factory.telegram_chat_id == chat_id, Factory.is_active.is_(True))
        .first()
    )


def _owner_for_factory(db: Session, factory_id: int) -> Optional[User]:
    return (
        db.query(User)
        .filter(User.factory_id == factory_id, User.role == "Owner", User.is_active.is_(True))
        .order_by(User.id.asc())
        .first()
    )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/api/v1/telegram/action", response_model=TelegramActionResponse)
def telegram_action_callback(
    body: TelegramActionRequest,
    _: None = Depends(require_n8n_api_key),
    db: Session = Depends(get_db),
) -> TelegramActionResponse:
    """
    Central handler for all Telegram inline-button callbacks.
    """
    chat_id = body.chat_id.strip()
    callback_id = body.callback_id.strip()
    callback_data = body.callback_data.strip()

    # 1. Resolve factory from chat_id
    factory = _resolve_factory(db, chat_id)
    binding = None
    if not factory:
        binding = db.query(TelegramUserBinding).filter(
            TelegramUserBinding.telegram_chat_id == chat_id,
            TelegramUserBinding.is_active.is_(True)
        ).first()
        if binding:
            factory = db.query(Factory).filter(Factory.id == binding.factory_id, Factory.is_active.is_(True)).first()

    if not factory:
        logger.warning("Telegram callback from unknown chat_id=%s action=%s — rejected", chat_id, callback_data)
        return TelegramActionResponse(
            status="error",
            message="This Telegram account is not linked to any factory. Please bind your account first.",
        )

    factory_id = factory.id

    # 2. Replay / deduplication guard
    action_label = callback_data.split(":")[0] if ":" in callback_data else callback_data
    if not dedupe_check(db, callback_id, factory_id, action_label):
        logger.info("Duplicate callback_id=%s factory_id=%s — skipped", callback_id, factory_id)
        return TelegramActionResponse(status="duplicate", message="Already processed")

    # 3. Resolve user role / details
    if not binding:
        binding = db.query(TelegramUserBinding).filter(
            TelegramUserBinding.telegram_chat_id == chat_id,
            TelegramUserBinding.is_active.is_(True)
        ).first()

    user = None
    if binding and binding.factory_id == factory.id:
        user = db.query(User).filter(User.id == binding.user_id, User.is_active.is_(True)).first()
    if not user:
        user = _owner_for_factory(db, factory.id)

    result: Optional[TelegramActionResult] = None
    parts = callback_data.split(":")

    try:
        action = parts[0]

        if action == "A1":
            result = handle_outstanding_view(db, factory_id, chat_id, {}, user)

        elif action == "A2":
            step = parts[1] if len(parts) > 1 else ""
            if step == "view_rm":
                result = handle_inventory_rm_view(db, factory_id, chat_id, {})
            elif step == "view_fg":
                result = handle_inventory_fg_view(db, factory_id, chat_id, {})
            else:
                result = handle_inventory_view(db, factory_id, chat_id, {})

        elif action == "A3":
            step = parts[1] if len(parts) > 1 else ""
            if step == "start":
                result = handle_production_start(db, factory_id, chat_id, {})
            elif step == "size" and len(parts) > 2:
                try:
                    size_ml = int(parts[2])
                except ValueError:
                    size_ml = 0
                result = handle_production_size(db, factory_id, chat_id, {}, size_ml)
            elif step == "machine" and len(parts) > 2:
                try:
                    machine_id = int(parts[2])
                except ValueError:
                    machine_id = 0
                result = handle_production_machine(db, factory_id, chat_id, {}, machine_id)
            elif step == "boxes" and len(parts) > 2:
                try:
                    boxes = int(parts[2])
                except ValueError:
                    boxes = 0
                result = handle_production_boxes(db, factory_id, chat_id, {}, boxes)
            elif step == "confirm":
                result = handle_production_confirm(db, factory_id, chat_id, {}, user)
            elif step == "cancel":
                result = handle_production_cancel(db, factory_id, chat_id, {})
            else:
                result = handle_production_start(db, factory_id, chat_id, {})

        elif action == "A4":
            step = parts[1] if len(parts) > 1 else ""
            if step == "start":
                result = handle_attendance_start(db, factory_id, chat_id, {})
            elif step == "worker" and len(parts) > 2:
                try:
                    worker_id = int(parts[2])
                except ValueError:
                    worker_id = 0
                result = handle_attendance_worker(db, factory_id, chat_id, {}, worker_id)
            elif step == "status" and len(parts) > 3:
                att_status = parts[2]
                try:
                    worker_id = int(parts[3])
                except ValueError:
                    worker_id = 0
                result = handle_attendance_status(db, factory_id, chat_id, {}, worker_id, att_status)
            elif step == "confirm":
                result = handle_attendance_confirm(db, factory_id, chat_id, {}, user)
            elif step == "cancel":
                result = handle_attendance_cancel(db, factory_id, chat_id, {})
            elif step == "view_summary":
                result = handle_attendance_summary_view(db, factory_id, chat_id, {})
            else:
                result = handle_attendance_start(db, factory_id, chat_id, {})

        elif action == "A5":
            result = handle_briefing_full(db, factory_id, chat_id, {}, user)

        elif action == "A6":
            result = handle_ask_start(db, factory_id, chat_id, {})

        elif action == "A10":
            result = handle_dashboard_summary_view(db, factory_id, chat_id, {}, user)

        elif action == "A11":
            result = handle_production_summary_view(db, factory_id, chat_id, {})

        elif action == "A12":
            step = parts[1] if len(parts) > 1 else ""
            if step == "start":
                result = handle_invoices_search_start(db, factory_id, chat_id, {}, user)
            elif step == "query" and len(parts) > 2:
                q_text = parts[2]
                result = handle_invoices_search_query(db, factory_id, chat_id, {}, q_text, user)
            elif step == "cancel":
                result = TelegramActionResult(message="❌ Invoice search cancelled.", buttons=_main_buttons())
            else:
                result = handle_invoices_search_start(db, factory_id, chat_id, {}, user)

        elif action == "A13":
            result = handle_payments_summary_view(db, factory_id, chat_id, {}, user)

        elif action == "A14":
            result = handle_wastage_summary_view(db, factory_id, chat_id, {})

        elif action == "W2":
            step = parts[1] if len(parts) > 1 else ""
            if step == "start":
                result = handle_wastage_start(db, factory_id, chat_id, {})
            elif step == "shift" and len(parts) > 2:
                result = handle_wastage_shift(db, factory_id, chat_id, {}, parts[2])
            elif step == "kg" and len(parts) > 2:
                try:
                    kg_val = float(parts[2])
                except ValueError:
                    kg_val = 0.0
                result = handle_wastage_kg(db, factory_id, chat_id, {}, kg_val)
            elif step == "confirm":
                result = handle_wastage_confirm(db, factory_id, chat_id, {}, user)
            elif step == "cancel":
                result = handle_wastage_cancel(db, factory_id, chat_id, {})
            else:
                result = handle_wastage_start(db, factory_id, chat_id, {})

        elif action == "W3":
            step = parts[1] if len(parts) > 1 else ""
            if step == "start":
                result = handle_invoice_start(db, factory_id, chat_id, {}, user)
            elif step == "customer" and len(parts) > 2:
                try:
                    cust_id = int(parts[2])
                except ValueError:
                    cust_id = 0
                result = handle_invoice_customer(db, factory_id, chat_id, {}, cust_id)
            elif step == "size" and len(parts) > 2:
                try:
                    sz_ml = int(parts[2])
                except ValueError:
                    sz_ml = 0
                result = handle_invoice_size(db, factory_id, chat_id, {}, sz_ml)
            elif step == "boxes" and len(parts) > 2:
                try:
                    bx_cnt = int(parts[2])
                except ValueError:
                    bx_cnt = 0
                result = handle_invoice_boxes(db, factory_id, chat_id, {}, bx_cnt)
            elif step == "confirm":
                result = handle_invoice_confirm(db, factory_id, chat_id, {}, user)
            elif step == "cancel":
                result = handle_invoice_cancel(db, factory_id, chat_id, {})
            else:
                result = handle_invoice_start(db, factory_id, chat_id, {}, user)

        elif action == "W4":
            step = parts[1] if len(parts) > 1 else ""
            if step == "start":
                result = handle_payment_start(db, factory_id, chat_id, {}, user)
            elif step == "customer" and len(parts) > 2:
                try:
                    cust_id = int(parts[2])
                except ValueError:
                    cust_id = 0
                result = handle_payment_customer(db, factory_id, chat_id, {}, cust_id)
            elif step == "amount" and len(parts) > 2:
                try:
                    amt_val = float(parts[2])
                except ValueError:
                    amt_val = 0.0
                result = handle_payment_amount(db, factory_id, chat_id, {}, amt_val)
            elif step == "confirm":
                result = handle_payment_confirm(db, factory_id, chat_id, {}, user)
            elif step == "cancel":
                result = handle_payment_cancel(db, factory_id, chat_id, {})
            else:
                result = handle_payment_start(db, factory_id, chat_id, {}, user)

        elif action == "W5":
            step = parts[1] if len(parts) > 1 else ""
            if step == "start":
                result = handle_edit_production_start(db, factory_id, chat_id, {})
            elif step == "prod" and len(parts) > 2:
                try:
                    pr_id = int(parts[2])
                except ValueError:
                    pr_id = 0
                result = handle_edit_production_select(db, factory_id, chat_id, {}, pr_id)
            elif step == "boxes" and len(parts) > 2:
                try:
                    bx_cnt = int(parts[2])
                except ValueError:
                    bx_cnt = 0
                result = handle_edit_production_boxes(db, factory_id, chat_id, {}, bx_cnt)
            elif step == "confirm":
                result = handle_edit_production_confirm(db, factory_id, chat_id, {}, user)
            elif step == "cancel":
                result = handle_edit_production_cancel(db, factory_id, chat_id, {})
            else:
                result = handle_edit_production_start(db, factory_id, chat_id, {})

        elif action == "R1":
            sub_action = parts[1] if len(parts) > 1 else ""
            customer_id = int(parts[2]) if len(parts) > 2 else 0

            if sub_action == "send_reminder":
                from services.recovery_automation import action_copy_reminder
                from services.recovery_automation import render_reminder_text
                customer = db.query(Customer).filter(Customer.id == customer_id, Customer.factory_id == factory_id).first()
                if customer:
                    action_copy_reminder(db, factory_id, customer_id, user.id if user else 0)
                    factory_obj = db.query(Factory).filter(Factory.id == factory_id).first()
                    factory_name = factory_obj.name if factory_obj else "Factory"
                    from sqlalchemy import func
                    total = db.query(func.coalesce(func.sum(OutstandingBill.balance_amount), 0)).filter(
                        OutstandingBill.customer_id == customer_id,
                        OutstandingBill.factory_id == factory_id,
                        OutstandingBill.status.in_(["active", "partial"]),
                        OutstandingBill.balance_amount > 0
                    ).scalar()
                    amount_paise = int(float(total or 0) * 100)
                    days = (date.today() - db.query(func.min(OutstandingBill.bill_date)).filter(
                        OutstandingBill.customer_id == customer_id,
                        OutstandingBill.factory_id == factory_id,
                        OutstandingBill.status.in_(["active", "partial"])
                    ).scalar()).days if db.query(func.min(OutstandingBill.bill_date)).filter(
                        OutstandingBill.customer_id == customer_id,
                        OutstandingBill.factory_id == factory_id,
                        OutstandingBill.status.in_(["active", "partial"])
                    ).scalar() else 0
                    reminder_text = render_reminder_text(customer.name, amount_paise, days, factory_name)
                    result = TelegramActionResult(
                        message=f"📋 Copy this reminder:\n\n{reminder_text}\n\nOwner can copy and send manually.",
                        buttons=[]
                    )

            elif sub_action == "skip":
                from services.recovery_automation import action_skip
                action_skip(db, factory_id, customer_id, user.id if user else 0)
                result = TelegramActionResult(message="✅ Skipped. No reminder sent.", buttons=[])

            elif sub_action == "done":
                from services.recovery_automation import action_mark_done
                action_mark_done(db, factory_id, customer_id, user.id if user else 0)
                result = TelegramActionResult(message="✅ Marked follow-up done.", buttons=[])

            elif sub_action == "snooze":
                from services.recovery_automation import action_snooze
                action_snooze(db, factory_id, customer_id, user.id if user else 0, days=3)
                result = TelegramActionResult(message="🔇 Snoozed for 3 days.", buttons=[])

            else:
                result = TelegramActionResult(message="⚠️ Unknown recovery action.", buttons=[])

        else:
            result = TelegramActionResult(
                message="⚠️ Unknown action. Please use the buttons below.",
                buttons=[
                    [
                        InlineButton("💵 Outstanding", "A1:view"),
                        InlineButton("📦 Inventory",   "A2:view"),
                    ],
                    [
                        InlineButton("📝 Production", "A3:start"),
                        InlineButton("📅 Attendance",  "A4:start"),
                    ],
                ],
            )

        db.commit()

    except Exception:
        db.rollback()
        logger.exception("Telegram action handler crashed factory_id=%s action=%s", factory_id, callback_data)
        result = TelegramActionResult(
            message="❌ An internal error occurred. Please try again or use the app.",
            buttons=[],
        )

    # 4. Send reply via Telegram Bot API
    if result:
        _send_reply(factory, chat_id, result)
        _answer_callback(factory, callback_id)

    return TelegramActionResponse(
        status="ok",
        message=result.message if result else "",
        action=action_label,
    )

"""P4.5 Deliverable 1: Telegram Action Alerts.

Owner is informed in real time when Sub-Owner or Supervisor perform
important operational actions. Owner is never alerted about their own
actions. Supervisor never receives alerts. Sub-Owner never receives
alerts about Owner actions.

Per AGENTS §15A:
  - Best-effort delivery. Never propagates failure to the caller.
  - Factory-scoped via TenantMixin on the throttle table.
  - Role-aware routing: only Owner receives.
  - Rate-limited: max 5 alerts per actor per hour per action_type.

Public API:
  send_action_alert(db, factory, actor, action_type, payload)
  notify_sale_created(db, sale_row, actor)
  notify_payment_received(db, payment_row, actor)
  notify_production_created(db, production_row, actor)
  notify_production_deleted(db, production_row, actor)
  notify_inventory_adjusted(db, factory, actor, item, qty_delta, ...)
  notify_worker_advance(db, advance_row, actor)
  notify_expense_above_threshold(db, expense_row, actor, threshold)
  notify_customer_created(db, customer_row, actor)
  notify_outstanding_threshold_crossed(db, customer_row, actor,
                                       new_total_paise, threshold)

Templates are deterministic Hinglish. No LLM. No fabrication.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

from models import (
    Factory,
    TelegramActionAlertThrottle,
    TelegramUserBinding,
    User,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Max alerts per actor per hour per action_type. 5 = spec.
MAX_ALERTS_PER_ACTOR_PER_HOUR = 5

# Owner outstanding threshold (paise). Rs 1,00,000 = 10,000,000 paise.
DEFAULT_OUTSTANDING_THRESHOLD_PAISE = 10_000_000

# Owner expense threshold (paise). Rs 5,000 = 500,000 paise.
DEFAULT_EXPENSE_THRESHOLD_PAISE = 500_000


# All 9 action types, in one canonical place.
ACTION_SALE_CREATED = "sale_created"
ACTION_PAYMENT_RECEIVED = "payment_received"
ACTION_PRODUCTION_CREATED = "production_created"
ACTION_PRODUCTION_DELETED = "production_deleted"
ACTION_INVENTORY_ADJUSTED = "inventory_adjusted"
ACTION_WORKER_ADVANCE = "worker_advance"
ACTION_EXPENSE_ABOVE_THRESHOLD = "expense_above_threshold"
ACTION_CUSTOMER_CREATED = "customer_created"
ACTION_OUTSTANDING_THRESHOLD_CROSSED = "outstanding_threshold_crossed"

ACTION_TYPES = frozenset({
    ACTION_SALE_CREATED,
    ACTION_PAYMENT_RECEIVED,
    ACTION_PRODUCTION_CREATED,
    ACTION_PRODUCTION_DELETED,
    ACTION_INVENTORY_ADJUSTED,
    ACTION_WORKER_ADVANCE,
    ACTION_EXPENSE_ABOVE_THRESHOLD,
    ACTION_CUSTOMER_CREATED,
    ACTION_OUTSTANDING_THRESHOLD_CROSSED,
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _money_rupees(paise: int | None) -> str:
    if paise is None:
        return "—"
    rupees = Decimal(int(paise)) / Decimal(100)
    return f"₹{rupees:,.0f}"


def _hour_bucket(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return current.strftime("%Y-%m-%dT%H")  # 13 chars, IST aligned in caller


def _actor_display(actor: User) -> str:
    full = (actor.full_name or "").strip() if hasattr(actor, "full_name") else ""
    if not full and hasattr(actor, "username"):
        full = (actor.username or "").strip()
    role = (actor.role or "").strip()
    if full and role:
        return f"{role} {full}"
    return role or full or "Unknown"


def _resolve_owner_binding(db: Session, factory: Factory) -> Optional[TelegramUserBinding]:
    """Get the active Owner telegram binding for this factory.

    Returns None silently if no Owner is bound (owner has not
    connected Telegram yet). This is the most common case for the
    first week of pilot; we must never crash the ERP write because
    the owner has not connected Telegram.
    """
    owner_user = (
        db.query(User)
        .filter(
            User.factory_id == factory.id,
            User.role == "Owner",
            User.is_active.is_(True),
        )
        .first()
    )
    if owner_user is None:
        return None
    binding = (
        db.query(TelegramUserBinding)
        .filter(
            TelegramUserBinding.factory_id == factory.id,
            TelegramUserBinding.user_id == owner_user.id,
            TelegramUserBinding.is_active.is_(True),
        )
        .first()
    )
    return binding


# ---------------------------------------------------------------------------
# Throttle
# ---------------------------------------------------------------------------

def _throttle_and_send(
    db: Session,
    factory: Factory,
    actor: User,
    action_type: str,
    message_text: str,
) -> bool:
    """Atomic insert-or-increment of the throttle bucket.

    Returns True if the message was sent, False if throttled or
    delivery failed. Never raises.
    """
    try:
        if actor.role == "Owner":
            # Owner's own actions never alert (per spec).
            return False
        if actor.role not in {"Sub-Owner", "Supervisor"}:
            # Unknown role; conservative no-op.
            return False

        binding = _resolve_owner_binding(db, factory)
        if binding is None:
            return False

        bucket = _hour_bucket()

        # Find or create throttle row.
        row = (
            db.query(TelegramActionAlertThrottle)
            .filter(
                TelegramActionAlertThrottle.factory_id == factory.id,
                TelegramActionAlertThrottle.actor_user_id == actor.id,
                TelegramActionAlertThrottle.action_type == action_type,
                TelegramActionAlertThrottle.hour_bucket == bucket,
            )
            .with_for_update()
            .first()
        )
        if row is None:
            row = TelegramActionAlertThrottle(
                factory_id=factory.id,
                actor_user_id=actor.id,
                action_type=action_type,
                hour_bucket=bucket,
                count=0,
            )
            db.add(row)
        row.count = (row.count or 0) + 1
        db.commit()
        if row.count > MAX_ALERTS_PER_ACTOR_PER_HOUR:
            # Throttled. Don't send this one, but the bucket still
            # records the attempt for auditability.
            logger.info(
                "action alert throttled",
                extra={
                    "factory_id": factory.id,
                    "actor_user_id": actor.id,
                    "action_type": action_type,
                    "bucket": bucket,
                    "count": row.count,
                },
            )
            return False

        # Deliver. We import here to avoid a circular import at module
        # load (telegram_delivery imports from services.* too).
        from services.telegram_delivery import send_telegram_message

        factory_proxy = factory
        factory_proxy._telegram_target_chat_id = binding.telegram_chat_id
        try:
            send_telegram_message(factory_proxy, message_text)
            row.last_sent_at = datetime.now(timezone.utc)
            db.commit()
            return True
        except Exception as exc:
            # Failure must never bubble out. Log + continue.
            logger.warning(
                "action alert telegram send failed",
                exc_info=exc,
                extra={
                    "factory_id": factory.id,
                    "actor_user_id": actor.id,
                    "action_type": action_type,
                },
            )
            return False
    except Exception as exc:
        logger.warning(
            "action alert throttle/db error",
            exc_info=exc,
            extra={
                "factory_id": factory.id,
                "action_type": action_type,
            },
        )
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False


# ---------------------------------------------------------------------------
# Public API: dispatcher
# ---------------------------------------------------------------------------

def send_action_alert(
    db: Session,
    factory: Factory,
    actor: User,
    action_type: str,
    payload: dict[str, Any],
) -> bool:
    """Format and dispatch an action alert to the Owner.

    Returns True if delivered, False otherwise. Never raises.
    """
    if action_type not in ACTION_TYPES:
        logger.warning("unknown action_type", extra={"action_type": action_type})
        return False
    text_msg = _format_action_alert(actor, action_type, payload)
    return _throttle_and_send(db, factory, actor, action_type, text_msg)


# ---------------------------------------------------------------------------
# Templates (deterministic, no LLM)
# ---------------------------------------------------------------------------

def _format_action_alert(actor: User, action_type: str, payload: dict[str, Any]) -> str:
    actor_label = _actor_display(actor)
    t = datetime.now().strftime("%I:%M %p").lstrip("0")

    if action_type == ACTION_SALE_CREATED:
        return (
            "💰 Sale Created\n\n"
            f"Customer: {payload.get('customer_name', '—')}\n"
            f"Amount: {_money_rupees(payload.get('amount_paise'))}\n"
            f"By: {actor_label}\n"
            f"Time: {t}"
        )

    if action_type == ACTION_PAYMENT_RECEIVED:
        return (
            "💵 Payment Received\n\n"
            f"Customer: {payload.get('customer_name', '—')}\n"
            f"Amount: {_money_rupees(payload.get('amount_paise'))}\n"
            f"Collected By: {actor_label}\n"
            f"Time: {t}"
        )

    if action_type == ACTION_PRODUCTION_CREATED:
        boxes = payload.get("boxes")
        machine = payload.get("machine_name", "—")
        return (
            "🏭 Production Entry\n\n"
            f"Machine: {machine}\n"
            f"Boxes: {boxes if boxes is not None else '—'}\n"
            f"By: {actor_label}\n"
            f"Time: {t}"
        )

    if action_type == ACTION_PRODUCTION_DELETED:
        boxes = payload.get("boxes")
        machine = payload.get("machine_name", "—")
        return (
            "🗑 Production Entry Deleted\n\n"
            f"Machine: {machine}\n"
            f"Boxes removed: {boxes if boxes is not None else '—'}\n"
            f"By: {actor_label}\n"
            f"Time: {t}"
        )

    if action_type == ACTION_INVENTORY_ADJUSTED:
        item = payload.get("item_name", "—")
        delta = payload.get("qty_delta", "—")
        unit = payload.get("unit", "")
        return (
            "📦 Inventory Adjustment\n\n"
            f"Item: {item}\n"
            f"Change: {delta} {unit}\n"
            f"By: {actor_label}\n"
            f"Time: {t}"
        )

    if action_type == ACTION_WORKER_ADVANCE:
        worker = payload.get("worker_name", "—")
        amount = _money_rupees(payload.get("amount_paise"))
        return (
            "👷 Worker Advance\n\n"
            f"Worker: {worker}\n"
            f"Amount: {amount}\n"
            f"By: {actor_label}\n"
            f"Time: {t}"
        )

    if action_type == ACTION_EXPENSE_ABOVE_THRESHOLD:
        category = payload.get("category", "—")
        amount = _money_rupees(payload.get("amount_paise"))
        threshold = _money_rupees(payload.get("threshold_paise"))
        return (
            "💸 Expense Above Threshold\n\n"
            f"Category: {category}\n"
            f"Amount: {amount}\n"
            f"Threshold: {threshold}\n"
            f"By: {actor_label}\n"
            f"Time: {t}"
        )

    if action_type == ACTION_CUSTOMER_CREATED:
        return (
            "👤 Customer Created\n\n"
            f"Name: {payload.get('customer_name', '—')}\n"
            f"Place: {payload.get('place', '—')}\n"
            f"By: {actor_label}\n"
            f"Time: {t}"
        )

    if action_type == ACTION_OUTSTANDING_THRESHOLD_CROSSED:
        total = _money_rupees(payload.get("new_total_paise"))
        threshold = _money_rupees(payload.get("threshold_paise"))
        return (
            "🚨 High Risk Customer\n\n"
            f"Customer: {payload.get('customer_name', '—')}\n"
            f"Outstanding: {total}\n"
            f"Threshold: {threshold}\n"
            f"By: {actor_label}\n"
            f"Time: {t}"
        )

    return f"Action: {action_type} by {actor_label}"


# ---------------------------------------------------------------------------
# Convenience hooks called by routers
# ---------------------------------------------------------------------------

def notify_sale_created(
    db: Session,
    factory: Factory,
    actor: User,
    customer_name: str,
    amount_paise: int,
) -> bool:
    return send_action_alert(
        db, factory, actor, ACTION_SALE_CREATED,
        {"customer_name": customer_name, "amount_paise": amount_paise},
    )


def notify_payment_received(
    db: Session,
    factory: Factory,
    actor: User,
    customer_name: str,
    amount_paise: int,
) -> bool:
    return send_action_alert(
        db, factory, actor, ACTION_PAYMENT_RECEIVED,
        {"customer_name": customer_name, "amount_paise": amount_paise},
    )


def notify_production_created(
    db: Session,
    factory: Factory,
    actor: User,
    machine_name: str,
    boxes: int,
) -> bool:
    return send_action_alert(
        db, factory, actor, ACTION_PRODUCTION_CREATED,
        {"machine_name": machine_name, "boxes": boxes},
    )


def notify_production_deleted(
    db: Session,
    factory: Factory,
    actor: User,
    machine_name: str,
    boxes: int,
) -> bool:
    return send_action_alert(
        db, factory, actor, ACTION_PRODUCTION_DELETED,
        {"machine_name": machine_name, "boxes": boxes},
    )


def notify_inventory_adjusted(
    db: Session,
    factory: Factory,
    actor: User,
    item_name: str,
    qty_delta,
    unit: str = "",
) -> bool:
    return send_action_alert(
        db, factory, actor, ACTION_INVENTORY_ADJUSTED,
        {"item_name": item_name, "qty_delta": str(qty_delta), "unit": unit},
    )


def notify_worker_advance(
    db: Session,
    factory: Factory,
    actor: User,
    worker_name: str,
    amount_paise: int,
) -> bool:
    return send_action_alert(
        db, factory, actor, ACTION_WORKER_ADVANCE,
        {"worker_name": worker_name, "amount_paise": amount_paise},
    )


def notify_expense_above_threshold(
    db: Session,
    factory: Factory,
    actor: User,
    category: str,
    amount_paise: int,
    threshold_paise: int = DEFAULT_EXPENSE_THRESHOLD_PAISE,
) -> bool:
    return send_action_alert(
        db, factory, actor, ACTION_EXPENSE_ABOVE_THRESHOLD,
        {
            "category": category,
            "amount_paise": amount_paise,
            "threshold_paise": threshold_paise,
        },
    )


def notify_customer_created(
    db: Session,
    factory: Factory,
    actor: User,
    customer_name: str,
    place: str = "—",
) -> bool:
    return send_action_alert(
        db, factory, actor, ACTION_CUSTOMER_CREATED,
        {"customer_name": customer_name, "place": place},
    )


def notify_outstanding_threshold_crossed(
    db: Session,
    factory: Factory,
    actor: User,
    customer_name: str,
    new_total_paise: int,
    threshold_paise: int = DEFAULT_OUTSTANDING_THRESHOLD_PAISE,
) -> bool:
    return send_action_alert(
        db, factory, actor, ACTION_OUTSTANDING_THRESHOLD_CROSSED,
        {
            "customer_name": customer_name,
            "new_total_paise": new_total_paise,
            "threshold_paise": threshold_paise,
        },
    )

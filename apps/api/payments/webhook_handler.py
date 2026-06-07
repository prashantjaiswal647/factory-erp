from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from models import Factory, SubscriptionPayment


def _data(payload: dict) -> dict:
    value = payload.get("data")
    return value if isinstance(value, dict) else payload


def _subscription(data: dict) -> dict:
    value = data.get("subscription_details") or data.get("subscription")
    return value if isinstance(value, dict) else data


def _payment(data: dict) -> dict:
    value = data.get("payment_details") or data.get("payment")
    return value if isinstance(value, dict) else data


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def process_cashfree_event(db: Session, event_type: str, payload: dict) -> dict:
    data = _data(payload)
    order = data.get("order") if isinstance(data.get("order"), dict) else {}
    subscription = _subscription(data)
    payment = _payment(data)
    order_id = str(order.get("order_id") or data.get("order_id") or "")
    order_payment = (
        db.query(SubscriptionPayment)
        .filter(SubscriptionPayment.cf_order_id == order_id, SubscriptionPayment.provider == "cashfree")
        .first()
        if order_id
        else None
    )
    if order_payment is not None:
        payment_status = str(payment.get("payment_status") or "").upper()
        cf_payment_id = str(payment.get("cf_payment_id") or "")
        if event_type == "PAYMENT_SUCCESS_WEBHOOK" and payment_status == "SUCCESS":
            amount_paise = int(round(float(payment.get("payment_amount") or 0) * 100))
            currency = str(payment.get("payment_currency") or order.get("order_currency") or "").upper()
            if amount_paise != order_payment.amount_paise or currency != order_payment.currency:
                raise ValueError("Cashfree payment amount or currency mismatch")
            duplicate = db.query(SubscriptionPayment).filter(
                SubscriptionPayment.cf_payment_id == cf_payment_id,
                SubscriptionPayment.id != order_payment.id,
            ).first()
            if duplicate is not None:
                return {"processed": True, "factory_id": duplicate.factory_id, "subscription_payment_id": duplicate.id}
            factory = db.get(Factory, order_payment.factory_id)
            if factory is None:
                raise ValueError("Factory for Cashfree order not found")
            if order_payment.payment_status != "paid":
                paid_at = _parse_datetime(payment.get("payment_time")) or datetime.now(timezone.utc)
                existing_end = factory.subscription_end_date or factory.plan_expires_at
                if existing_end is not None and existing_end.tzinfo is None:
                    existing_end = existing_end.replace(tzinfo=timezone.utc)
                cycle_start = existing_end if existing_end and existing_end > paid_at else paid_at
                cycle_end = cycle_start + timedelta(days=365 if order_payment.billing_cycle == "yearly" else 30)
                factory.subscription_status = "active"
                factory.payment_status = "paid"
                factory.active_plan = order_payment.plan_code
                factory.plan_name = order_payment.plan_code
                factory.billing_cycle = order_payment.billing_cycle
                factory.subscription_start_date = cycle_start
                factory.subscription_end_date = cycle_end
                factory.subscription_start = cycle_start
                factory.subscription_end = cycle_end
                factory.plan_expires_at = cycle_end
                factory.current_period_start = cycle_start
                factory.current_period_end = cycle_end
                factory.cashfree_plan_code = order_payment.plan_code
                order_payment.payment_status = "paid"
                order_payment.provider_payment_id = cf_payment_id
                order_payment.cf_payment_id = cf_payment_id
                order_payment.cf_event_id = str(payload.get("event_id") or data.get("event_id") or "") or None
                order_payment.subscription_start_date = cycle_start
                order_payment.subscription_end_date = cycle_end
            db.flush()
            return {"processed": True, "factory_id": order_payment.factory_id, "subscription_payment_id": order_payment.id}
        if event_type in {"PAYMENT_FAILED_WEBHOOK", "PAYMENT_USER_DROPPED_WEBHOOK"} and order_payment.payment_status != "paid":
            order_payment.payment_status = "failed" if event_type == "PAYMENT_FAILED_WEBHOOK" else "user_dropped"
            db.flush()
        return {"processed": True, "factory_id": order_payment.factory_id, "subscription_payment_id": order_payment.id}

    subscription_id = (
        subscription.get("subscription_id")
        or data.get("subscription_id")
        or payment.get("subscription_id")
    )
    factory = (
        db.query(Factory)
        .filter(Factory.cashfree_subscription_id == str(subscription_id))
        .first()
        if subscription_id
        else None
    )
    if factory is None:
        return {"processed": True, "factory_id": None, "subscription_payment_id": None}

    now = datetime.now(timezone.utc)
    payment_record = None
    current_status = str(
        subscription.get("subscription_status")
        or data.get("subscription_status")
        or ""
    ).upper()
    success_events = {"SUBSCRIPTION_PAYMENT_SUCCESS", "SUBSCRIPTION_CHARGED_SUCCESS", "PAYMENT_SUCCESS"}
    failed_events = {"SUBSCRIPTION_PAYMENT_FAILED", "SUBSCRIPTION_CHARGED_FAILED", "PAYMENT_FAILED"}
    cancelled_statuses = {"CANCELLED", "CUSTOMER_CANCELLED", "EXPIRED", "COMPLETED"}

    if event_type in {"SUBSCRIPTION_ACTIVATED", "SUBSCRIPTION_AUTH_STATUS"} or (
        event_type == "SUBSCRIPTION_STATUS_CHANGED" and current_status == "ACTIVE"
    ):
        factory.subscription_status = "active"
        factory.payment_status = "paid"
        factory.current_period_start = _parse_datetime(
            subscription.get("current_period_start") or subscription.get("subscription_first_charge_time")
        ) or now
        factory.current_period_end = _parse_datetime(
            subscription.get("current_period_end") or subscription.get("subscription_expiry_time")
        )
        factory.next_billing_at = _parse_datetime(subscription.get("next_schedule_date"))
    elif event_type in success_events:
        period_start = _parse_datetime(payment.get("payment_time")) or now
        period_end = _parse_datetime(
            payment.get("period_end") or subscription.get("current_period_end")
        ) or period_start + timedelta(days=30)
        factory.subscription_status = "active"
        factory.payment_status = "paid"
        factory.current_period_start = period_start
        factory.current_period_end = period_end
        factory.next_billing_at = _parse_datetime(
            payment.get("next_schedule_date") or subscription.get("next_schedule_date")
        )
        amount_value = payment.get("payment_amount") or payment.get("amount") or 0
        payment_record = SubscriptionPayment(
            factory_id=factory.id,
            plan_code=factory.cashfree_plan_code or "monthly",
            billing_cycle=factory.cashfree_plan_code or "monthly",
            amount_paise=int(round(float(amount_value) * 100)),
            currency=str(payment.get("payment_currency") or "INR"),
            payment_status="paid",
            provider="cashfree",
            provider_payment_id=str(payment.get("cf_payment_id") or payment.get("payment_id") or ""),
            subscription_start_date=period_start,
            subscription_end_date=period_end,
            cf_order_id=str(payment.get("cf_order_id") or "") or None,
            cf_payment_id=str(payment.get("cf_payment_id") or payment.get("payment_id") or "") or None,
            cf_invoice_id=str(payment.get("cf_invoice_id") or payment.get("invoice_id") or "") or None,
            cf_event_id=str(payload.get("event_id") or data.get("event_id") or ""),
        )
        db.add(payment_record)
        db.flush()
    elif event_type in failed_events:
        factory.subscription_status = "past_due"
        factory.payment_status = "failed"
    elif event_type in {"SUBSCRIPTION_CANCELLED", "SUBSCRIPTION_EXPIRED"} or (
        event_type == "SUBSCRIPTION_STATUS_CHANGED" and current_status in cancelled_statuses
    ):
        factory.subscription_status = "cancelled"
        factory.cancelled_at = now

    db.flush()
    return {
        "processed": True,
        "factory_id": factory.id,
        "subscription_payment_id": payment_record.id if payment_record else None,
    }

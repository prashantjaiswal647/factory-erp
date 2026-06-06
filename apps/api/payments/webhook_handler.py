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
    subscription = _subscription(data)
    payment = _payment(data)
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

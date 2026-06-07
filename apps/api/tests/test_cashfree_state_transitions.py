from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import Factory, SubscriptionPayment
from payments.webhook_handler import process_cashfree_event


def make_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Factory(id=1, name="Factory", cashfree_subscription_id="sub_1", cashfree_plan_code="monthly"))
    db.commit()
    return db


def test_current_cashfree_status_and_payment_events():
    db = make_db()
    activated = {
        "data": {
            "event_id": "evt_active",
            "subscription_details": {
                "subscription_id": "sub_1",
                "subscription_status": "ACTIVE",
                "current_period_start": datetime.now(timezone.utc).isoformat(),
                "current_period_end": datetime.now(timezone.utc).isoformat(),
            },
        }
    }
    process_cashfree_event(db, "SUBSCRIPTION_STATUS_CHANGED", activated)
    assert db.get(Factory, 1).subscription_status == "active"

    paid = {
        "event_id": "evt_paid",
        "data": {
            "subscription_id": "sub_1",
            "payment_details": {"cf_payment_id": "pay_1", "payment_amount": 999},
        },
    }
    process_cashfree_event(db, "SUBSCRIPTION_PAYMENT_SUCCESS", paid)
    assert db.query(SubscriptionPayment).one().cf_payment_id == "pay_1"


def test_failed_cancelled_and_orphan_events():
    db = make_db()
    process_cashfree_event(db, "SUBSCRIPTION_PAYMENT_FAILED", {"data": {"subscription_id": "sub_1"}})
    assert db.get(Factory, 1).subscription_status == "past_due"
    process_cashfree_event(
        db,
        "SUBSCRIPTION_STATUS_CHANGED",
        {"data": {"subscription_details": {"subscription_id": "sub_1", "subscription_status": "CANCELLED"}}},
    )
    assert db.get(Factory, 1).subscription_status == "cancelled"
    result = process_cashfree_event(db, "SUBSCRIPTION_PAYMENT_SUCCESS", {"data": {"subscription_id": "missing"}})
    assert result["factory_id"] is None


def test_payment_gateway_success_activates_pending_order_once():
    db = make_db()
    now = datetime.now(timezone.utc)
    pending = SubscriptionPayment(
        factory_id=1,
        plan_code="growth",
        billing_cycle="yearly",
        amount_paise=1999900,
        currency="INR",
        payment_status="pending",
        provider="cashfree",
        provider_payment_id="order_1",
        cf_order_id="order_1",
        cf_payment_session_id="session_1",
        subscription_start_date=now,
        subscription_end_date=now,
    )
    db.add(pending)
    db.commit()
    payload = {
        "type": "PAYMENT_SUCCESS_WEBHOOK",
        "data": {
            "order": {"order_id": "order_1", "order_amount": 19999, "order_currency": "INR"},
            "payment": {
                "cf_payment_id": "pay_order_1",
                "payment_status": "SUCCESS",
                "payment_amount": 19999,
                "payment_currency": "INR",
                "payment_time": now.isoformat(),
            },
        },
    }

    first = process_cashfree_event(db, "PAYMENT_SUCCESS_WEBHOOK", payload)
    second = process_cashfree_event(db, "PAYMENT_SUCCESS_WEBHOOK", payload)
    db.commit()

    factory = db.get(Factory, 1)
    payment = db.query(SubscriptionPayment).filter(SubscriptionPayment.cf_order_id == "order_1").one()
    assert first["subscription_payment_id"] == payment.id
    assert second["subscription_payment_id"] == payment.id
    assert payment.payment_status == "paid"
    assert payment.cf_payment_id == "pay_order_1"
    assert factory.subscription_status == "active"
    assert factory.active_plan == "growth"
    assert factory.billing_cycle == "yearly"
    assert factory.subscription_end_date > factory.subscription_start_date

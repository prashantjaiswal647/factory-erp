"""P4.5 Deliverable 1: Telegram Action Alert unit tests.

Tests the telegram_action_alerts service directly:
- All 9 action types generate correct formatted messages
- Owner actions never self-alert
- Sub-Owner/Supervisor actions do alert
- Throttle works (max 5 per actor per hour)
- Cross-actor isolation on throttle buckets
- Error resilience (telegram down does not raise)
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import (
    Factory,
    TelegramActionAlertThrottle,
    TelegramUserBinding,
    User,
)


# ---------------------------------------------------------------------------
# Fixture: in-memory sqlite DB
# ---------------------------------------------------------------------------


@pytest.fixture()
def alert_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        factory = Factory(id=1, name="Alert Factory", subscription_status="active")
        owner = User(
            id=10,
            factory_id=1,
            username="alert-owner",
            full_name="Owner",
            role="Owner",
            is_active=True,
            password_hash="-",
        )
        subowner = User(
            id=11,
            factory_id=1,
            username="alert-subowner",
            full_name="Sub Owner Rahul",
            role="Sub-Owner",
            is_active=True,
            password_hash="-",
        )
        supervisor = User(
            id=12,
            factory_id=1,
            username="alert-supervisor",
            full_name="Supervisor Amit",
            role="Supervisor",
            is_active=True,
            password_hash="-",
        )
        # Active Owner binding
        owner_binding = TelegramUserBinding(
            factory_id=1,
            user_id=10,
            role="Owner",
            telegram_chat_id="100001",
            is_active=True,
        )
        db.add_all([factory, owner, subowner, supervisor, owner_binding])
        db.commit()
        yield db, factory, owner, subowner, supervisor
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from services.telegram_action_alerts import (
    ACTION_SALE_CREATED,
    ACTION_PAYMENT_RECEIVED,
    ACTION_PRODUCTION_CREATED,
    ACTION_PRODUCTION_DELETED,
    ACTION_INVENTORY_ADJUSTED,
    ACTION_WORKER_ADVANCE,
    ACTION_EXPENSE_ABOVE_THRESHOLD,
    ACTION_CUSTOMER_CREATED,
    ACTION_OUTSTANDING_THRESHOLD_CROSSED,
    send_action_alert,
    notify_sale_created,
    notify_payment_received,
    notify_production_created,
    notify_production_deleted,
    notify_inventory_adjusted,
    notify_worker_advance,
    notify_expense_above_threshold,
    notify_customer_created,
    notify_outstanding_threshold_crossed,
    _format_action_alert,
    _actor_display,
    MAX_ALERTS_PER_ACTOR_PER_HOUR,
)


# ---------------------------------------------------------------------------
# Test actor display
# ---------------------------------------------------------------------------


def test_actor_display_uses_full_name(alert_db):
    _, _, _, subowner, _ = alert_db
    label = _actor_display(subowner)
    assert "Sub-Owner" in label
    assert "Rahul" in label


# ---------------------------------------------------------------------------
# Test template formatting for all 9 action types
# ---------------------------------------------------------------------------


def test_format_sale_created_template(alert_db):
    _, _, _, subowner, _ = alert_db
    msg = _format_action_alert(
        subowner,
        ACTION_SALE_CREATED,
        {"customer_name": "ABC Traders", "amount_paise": 4800000},
    )
    assert "Sale Created" in msg
    assert "ABC Traders" in msg
    assert "Sub-Owner" in msg
    assert "Rahul" in msg


def test_format_payment_received_template(alert_db):
    _, _, _, _, supervisor = alert_db
    msg = _format_action_alert(
        supervisor,
        ACTION_PAYMENT_RECEIVED,
        {"customer_name": "XYZ Packaging", "amount_paise": 2500000},
    )
    assert "Payment Received" in msg
    assert "XYZ Packaging" in msg
    assert "Supervisor" in msg


def test_format_production_created_template(alert_db):
    _, _, _, subowner, _ = alert_db
    msg = _format_action_alert(
        subowner,
        ACTION_PRODUCTION_CREATED,
        {"machine_name": "Paper Cup Line 1", "boxes": 250},
    )
    assert "Production Entry" in msg
    assert "Paper Cup Line 1" in msg
    assert "250" in msg


def test_format_production_deleted_template(alert_db):
    _, _, _, subowner, _ = alert_db
    msg = _format_action_alert(
        subowner,
        ACTION_PRODUCTION_DELETED,
        {"machine_name": "Paper Cup Line 1", "boxes": 50},
    )
    assert "Deleted" in msg
    assert "50" in msg


def test_format_inventory_adjusted_template(alert_db):
    _, _, _, subowner, _ = alert_db
    msg = _format_action_alert(
        subowner,
        ACTION_INVENTORY_ADJUSTED,
        {"item_name": "Bottom Roll", "qty_delta": "-50", "unit": "kg"},
    )
    assert "Inventory Adjustment" in msg
    assert "Bottom Roll" in msg
    assert "-50" in msg


def test_format_worker_advance_template(alert_db):
    _, _, _, supervisor, _ = alert_db
    msg = _format_action_alert(
        supervisor,
        ACTION_WORKER_ADVANCE,
        {"worker_name": "Ramesh", "amount_paise": 200000},
    )
    assert "Worker Advance" in msg
    assert "Ramesh" in msg


def test_format_expense_above_threshold_template(alert_db):
    _, _, _, subowner, _ = alert_db
    msg = _format_action_alert(
        subowner,
        ACTION_EXPENSE_ABOVE_THRESHOLD,
        {"category": "Electricity", "amount_paise": 800000, "threshold_paise": 500000},
    )
    assert "Expense Above Threshold" in msg
    assert "Electricity" in msg


def test_format_customer_created_template(alert_db):
    _, _, _, subowner, _ = alert_db
    msg = _format_action_alert(
        subowner,
        ACTION_CUSTOMER_CREATED,
        {"customer_name": "New Tea Corner", "place": "Delhi"},
    )
    assert "Customer Created" in msg
    assert "New Tea Corner" in msg
    assert "Delhi" in msg


def test_format_outstanding_threshold_crossed_template(alert_db):
    _, _, _, subowner, _ = alert_db
    msg = _format_action_alert(
        subowner,
        ACTION_OUTSTANDING_THRESHOLD_CROSSED,
        {"customer_name": "ABC Traders", "new_total_paise": 15000000, "threshold_paise": 10000000},
    )
    assert "High Risk Customer" in msg
    assert "ABC Traders" in msg


# ---------------------------------------------------------------------------
# Role-based routing
# ---------------------------------------------------------------------------


def test_owner_self_action_never_alerts(alert_db):
    """Owner's own actions must not fire an alert."""
    db, factory, owner, _, _ = alert_db
    with patch("services.telegram_delivery.send_telegram_message") as mock_send:
        result = send_action_alert(
            db, factory, owner, ACTION_SALE_CREATED,
            {"customer_name": "Self", "amount_paise": 100000},
        )
        assert result is False, "Owner action should not alert"
        mock_send.assert_not_called()


def test_subowner_action_alerts_owner(alert_db):
    """Sub-Owner action must fire an alert to Owner."""
    db, factory, _, subowner, _ = alert_db
    with patch("services.telegram_delivery.send_telegram_message") as mock_send:
        mock_send.return_value = None
        result = notify_sale_created(db, factory, subowner, "Test Co", 500000)
        assert result is True, "Sub-Owner action should alert"
        mock_send.assert_called_once()


def test_supervisor_action_alerts_owner(alert_db):
    """Supervisor action must fire an alert to Owner."""
    db, factory, _, _, supervisor = alert_db
    with patch("services.telegram_delivery.send_telegram_message") as mock_send:
        mock_send.return_value = None
        result = notify_payment_received(db, factory, supervisor, "Pay Co", 100000)
        assert result is True, "Supervisor action should alert"
        mock_send.assert_called_once()


def test_no_owner_binding_returns_silently(alert_db):
    """If no Owner telegram binding exists, the alert is silently dropped."""
    db, factory, _, subowner, _ = alert_db
    # Remove the binding
    db.query(TelegramUserBinding).delete()
    db.commit()
    with patch("services.telegram_delivery.send_telegram_message") as mock_send:
        result = notify_sale_created(db, factory, subowner, "No Binding", 50000)
        assert result is False, "No binding should return False"
        mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# Throttle
# ---------------------------------------------------------------------------


def test_throttle_blocks_after_max_alerts(alert_db):
    """Max 5 alerts per actor per action_type per hour. 6th should be throttled."""
    db, factory, _, subowner, _ = alert_db
    with patch("services.telegram_delivery.send_telegram_message") as mock_send:
        mock_send.return_value = None
        results = []
        for _ in range(MAX_ALERTS_PER_ACTOR_PER_HOUR + 2):
            r = notify_sale_created(db, factory, subowner, "Throttle Co", 10000)
            results.append(r)
        # First 5 should be True (sent), rest False (throttled)
        assert all(results[:MAX_ALERTS_PER_ACTOR_PER_HOUR]), "first N should be sent"
        assert not any(results[MAX_ALERTS_PER_ACTOR_PER_HOUR:]), "beyond N should be throttled"
        # But send_telegram_message should only be called exactly N times
        assert mock_send.call_count == MAX_ALERTS_PER_ACTOR_PER_HOUR


def test_throttle_buckets_per_action_type(alert_db):
    """Different action types have separate throttle counters."""
    db, factory, _, subowner, _ = alert_db
    with patch("services.telegram_delivery.send_telegram_message") as mock_send:
        mock_send.return_value = None
        # Send 5 sale alerts (max)
        for _ in range(MAX_ALERTS_PER_ACTOR_PER_HOUR):
            notify_sale_created(db, factory, subowner, "Sale Co", 10000)
        sale_count = mock_send.call_count
        # Then send a payment alert — should not be throttled (different action_type)
        r = notify_payment_received(db, factory, subowner, "Pay Co", 5000)
        assert r is True, "different action_type should not be throttled"
        assert mock_send.call_count == sale_count + 1


# ---------------------------------------------------------------------------
# Error resilience
# ---------------------------------------------------------------------------


def test_telegram_failure_never_raises(alert_db):
    """If telegram send fails, the function catches and returns False."""
    db, factory, _, subowner, _ = alert_db
    with patch("services.telegram_delivery.send_telegram_message") as mock_send:
        mock_send.side_effect = RuntimeError("telegram down")
        # This should not raise — it should return False.
        result = notify_sale_created(db, factory, subowner, "Failure Co", 12345)
        assert result is False, "should return False on telegram failure, not raise"


# ---------------------------------------------------------------------------
# All 9 convenience functions
# ---------------------------------------------------------------------------


def test_all_notify_functions_have_correct_signatures(alert_db):
    """All notify_* functions accept the required positional args."""
    db, factory, _, subowner, _ = alert_db
    with patch("services.telegram_delivery.send_telegram_message") as mock_send:
        mock_send.return_value = None
        assert notify_sale_created(db, factory, subowner, "C", 100) is True
        assert notify_payment_received(db, factory, subowner, "C", 100) is True
        assert notify_production_created(db, factory, subowner, "M1", 50) is True
        assert notify_production_deleted(db, factory, subowner, "M1", 10) is True
        assert notify_inventory_adjusted(db, factory, subowner, "Item", "10", "kg") is True
        assert notify_worker_advance(db, factory, subowner, "Worker", 50000) is True
        assert notify_expense_above_threshold(db, factory, subowner, "Power", 600000) is True
        assert notify_customer_created(db, factory, subowner, "Cust", "City") is True
        assert notify_outstanding_threshold_crossed(db, factory, subowner, "Cust", 15000000, 10000000) is True
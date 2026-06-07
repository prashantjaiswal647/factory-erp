from datetime import date, datetime, timedelta
from decimal import Decimal

from models import CostVarianceAlertLog, DailyVarianceSnapshot, Factory
from services.briefing_service import render_morning_briefing_message
from services.cost_scheduler import (
    deliver_cost_spike_alert,
    render_cost_spike_alert,
    seconds_until_next_run,
)
from services.cost_variance import classify_variance, compute_variance_summary, should_send_spike_alert
from services.timezone_utils import KOLKATA_ZONE
from tests.test_cost_per_cup import make_db, seed_production


TODAY = date.today()


def seed_weighted_history(db, factory_id: int = 1):
    seed_production(
        db,
        factory_id,
        TODAY - timedelta(days=2),
        boxes=1,
        material="100",
        labour="0",
        electricity="0",
    )
    seed_production(
        db,
        factory_id,
        TODAY - timedelta(days=1),
        boxes=3,
        material="600",
        labour="0",
        electricity="0",
    )
    seed_production(
        db,
        factory_id,
        TODAY,
        boxes=1,
        material="200",
        labour="0",
        electricity="0",
    )


def test_weighted_average_and_variance_calculation():
    engine, db = make_db()
    try:
        seed_weighted_history(db)
        result = compute_variance_summary(db, 1, TODAY)
        assert result["seven_day_cpc"] == "0.1750"
        assert result["today_cpc"] == "0.2000"
        assert result["variance_percent"] == "+14.2857"
        assert result["seven_day_cpc"] != "0.1500"
    finally:
        db.close()
        engine.dispose()


def test_variance_classification_boundaries():
    assert classify_variance(Decimal("3")) == "NORMAL"
    assert classify_variance(Decimal("3.0001")) == "WARNING"
    assert classify_variance(Decimal("8")) == "WARNING"
    assert classify_variance(Decimal("8.0001")) == "CRITICAL"
    assert classify_variance(Decimal("-9")) == "CRITICAL"


def test_primary_driver_detection():
    engine, db = make_db()
    try:
        seed_production(db, 1, TODAY - timedelta(days=1), boxes=1, material="100", labour="100", electricity="100")
        seed_production(db, 1, TODAY, boxes=1, material="180", labour="105", electricity="100")
        result = compute_variance_summary(db, 1, TODAY)
        assert result["primary_driver"] == "Material Cost"
        assert result["material_change_percent"] == "+80.0000"
        assert result["labour_change_percent"] == "+5.0000"
        assert result["electricity_change_percent"] == "+0.0000"
    finally:
        db.close()
        engine.dispose()


def test_spike_alert_threshold_is_positive_increase_only():
    assert should_send_spike_alert({"variance_percent": "+5.0000"}) is False
    assert should_send_spike_alert({"variance_percent": "+5.0001"}) is True
    assert should_send_spike_alert({"variance_percent": "-20.0000"}) is False
    assert should_send_spike_alert({"variance_percent": "Data not available"}) is False


def test_only_one_cost_alert_per_factory_per_day():
    engine, db = make_db()
    try:
        seed_weighted_history(db)
        factory = db.get(Factory, 1)
        summary = compute_variance_summary(db, 1, TODAY)
        sent_messages = []

        def sender(_, message):
            sent_messages.append(message)

        first, sent_first = deliver_cost_spike_alert(db, factory, summary, sender=sender)
        second, sent_second = deliver_cost_spike_alert(db, factory, summary, sender=sender)

        assert sent_first is True
        assert sent_second is False
        assert second.id == first.id
        assert len(sent_messages) == 1
        assert db.query(CostVarianceAlertLog).count() == 1
    finally:
        db.close()
        engine.dispose()


def test_variance_factory_isolation():
    engine, db = make_db()
    try:
        seed_weighted_history(db, 1)
        seed_production(db, 2, TODAY - timedelta(days=1), boxes=1, material="9000", labour="0", electricity="0")
        seed_production(db, 2, TODAY, boxes=1, material="100", labour="0", electricity="0")
        result = compute_variance_summary(db, 1, TODAY)
        assert result["today_cpc"] == "0.2000"
        assert result["seven_day_cpc"] == "0.1750"
        assert db.query(DailyVarianceSnapshot).filter_by(factory_id=2).count() == 0
    finally:
        db.close()
        engine.dispose()


def test_briefing_renders_variance_summary():
    snapshot = {
        "production": {"produced": 10, "target": 20, "gap": 10},
        "workers": {"present": 2, "absent": 1},
        "sales": {"invoice_count": 1, "amount": 100, "collections_received": 50, "outstanding_amount": 50},
        "risk_items": [],
        "variance_summary": {
            "today_cpc": "0.5800",
            "seven_day_cpc": "0.5300",
            "variance_percent": "+9.4340",
            "primary_driver": "Material Cost",
        },
    }
    message = render_morning_briefing_message(snapshot, "Owner", "en")
    assert "Cost Per Cup: ₹0.5800" in message
    assert "7 Day Average: ₹0.5300" in message
    assert "Change: +9.4%" in message
    assert "Primary Driver: Material Cost" in message


def test_dashboard_api_is_registered():
    from main import app

    paths = {route.path for route in app.routes}
    assert "/api/cost/variance/today" in paths


def test_alert_message_and_nightly_schedule():
    summary = {
        "today_cpc": "0.5800",
        "seven_day_cpc": "0.5300",
        "variance_percent": "+9.4340",
        "primary_driver": "Material Cost",
    }
    message = render_cost_spike_alert(summary)
    assert "⚠ Cost Spike Alert" in message
    assert "Increase:\n9.4340%" in message
    before = datetime(2026, 6, 6, 23, 50, tzinfo=KOLKATA_ZONE)
    after = datetime(2026, 6, 6, 23, 56, tzinfo=KOLKATA_ZONE)
    assert seconds_until_next_run(before) == 5 * 60
    assert seconds_until_next_run(after) == (23 * 60 + 59) * 60

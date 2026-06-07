from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy.orm import sessionmaker

from models import (
    Customer,
    DailyProfitSnapshot,
    Factory,
    ProfitAlertLog,
    PerSizeDaily,
    SalesInvoice,
)
from routers.profit import profit_history
from services.briefing_service import render_morning_briefing_message
from services.profit_intelligence import classify_profit_margin, compute_profit_snapshot
from services.profit_scheduler import deliver_profit_alert, run_profit_batch, seconds_until_next_run
from services.timezone_utils import KOLKATA_ZONE
from tests.test_cost_per_cup import make_db, seed_production


TODAY = date.today()


def seed_profit_fixture(
    db,
    factory_id: int = 1,
    *,
    revenue: str = "1000",
    paid: str = "1000",
    material: str = "400",
    labour: str = "100",
    electricity: str = "50",
):
    seed_production(
        db,
        factory_id,
        TODAY,
        boxes=1,
        material=material,
        labour=labour,
        electricity=electricity,
    )
    customer = Customer(factory_id=factory_id, name=f"Profit Customer {factory_id}")
    db.add(customer)
    db.flush()
    db.add(
        SalesInvoice(
            factory_id=factory_id,
            customer_id=customer.id,
            date=TODAY,
            cup_size_ml=100,
            packaging_profile_id=700 + factory_id,
            boxes_sold=1,
            total_amount=Decimal(revenue),
            amount_paid=Decimal(paid),
        )
    )
    db.commit()


def test_profit_and_margin_calculation():
    engine, db = make_db()
    try:
        seed_profit_fixture(db)
        result = compute_profit_snapshot(db, 1, TODAY)
        assert result["revenue_paise"] == 100000
        assert result["total_cost_paise"] == 55000
        assert result["gross_profit_paise"] == 45000
        assert result["profit_margin_percent"] == 45
        assert result["profit_status"] == "EXCELLENT"
    finally:
        db.close()
        engine.dispose()


def test_status_classification_boundaries():
    assert classify_profit_margin(Decimal("25.01")) == "EXCELLENT"
    assert classify_profit_margin(Decimal("25")) == "GOOD"
    assert classify_profit_margin(Decimal("15")) == "GOOD"
    assert classify_profit_margin(Decimal("5")) == "WARNING"
    assert classify_profit_margin(Decimal("4.99")) == "CRITICAL"
    assert classify_profit_margin(None) == "DATA_NOT_AVAILABLE"


def test_largest_risk_detection_includes_collections():
    engine, db = make_db()
    try:
        seed_profit_fixture(db, paid="0", material="100", labour="10", electricity="10")
        result = compute_profit_snapshot(db, 1, TODAY)
        assert result["largest_profit_risk"] == "Collections"
    finally:
        db.close()
        engine.dispose()


def test_no_revenue_returns_data_not_available():
    engine, db = make_db()
    try:
        seed_production(db, 1, TODAY, boxes=1)
        result = compute_profit_snapshot(db, 1, TODAY)
        assert result["data_available"] is False
        assert result["profit_margin_percent"] == "Data not available"
        assert result["profit_status"] == "DATA_NOT_AVAILABLE"
    finally:
        db.close()
        engine.dispose()


def test_upsert_and_factory_isolation():
    engine, db = make_db()
    try:
        seed_profit_fixture(db, 1)
        seed_profit_fixture(db, 2, revenue="999999", paid="0")
        first = compute_profit_snapshot(db, 1, TODAY)
        second = compute_profit_snapshot(db, 1, TODAY)
        assert first["id"] == second["id"]
        assert first["revenue_paise"] == 100000
        assert db.query(DailyProfitSnapshot).filter_by(factory_id=1, snapshot_date=TODAY).count() == 1
        assert db.query(DailyProfitSnapshot).filter_by(factory_id=2).count() == 0
    finally:
        db.close()
        engine.dispose()


def test_history_endpoint_is_factory_scoped():
    engine, db = make_db()
    try:
        seed_profit_fixture(db, 1)
        seed_profit_fixture(db, 2)
        compute_profit_snapshot(db, 1, TODAY)
        compute_profit_snapshot(db, 2, TODAY)
        response = profit_history(days=30, current_user=SimpleNamespace(factory_id=1), db=db)
        assert len(response["items"]) == 1
        assert response["items"][0]["factory_id"] == 1
    finally:
        db.close()
        engine.dispose()


def test_scheduler_execution_and_timing():
    engine, db = make_db()
    seed_profit_fixture(db, material="950", labour="100", electricity="50")
    db.close()
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    sent_messages = []
    metrics = run_profit_batch(
        TODAY,
        session_factory=factory,
        sender=lambda _factory, message: sent_messages.append(message),
    )
    verify = factory()
    try:
        assert metrics == {"total_factories": 1, "computed": 1, "alerts_sent": 1, "failed": 0}
        assert verify.query(DailyProfitSnapshot).count() == 1
        assert verify.query(PerSizeDaily).count() == 1
        assert len(sent_messages) == 1
        before = datetime(2026, 6, 7, 23, 58, tzinfo=KOLKATA_ZONE)
        assert seconds_until_next_run(before) == 60
    finally:
        verify.close()
        engine.dispose()


def test_alert_delivery_is_deduplicated():
    engine, db = make_db()
    try:
        seed_profit_fixture(db, material="950", labour="100", electricity="50")
        snapshot = compute_profit_snapshot(db, 1, TODAY)
        factory = db.get(Factory, 1)
        messages = []
        first, first_sent = deliver_profit_alert(db, factory, snapshot, sender=lambda _factory, message: messages.append(message))
        second, second_sent = deliver_profit_alert(db, factory, snapshot, sender=lambda _factory, message: messages.append(message))
        assert first.id == second.id
        assert first_sent is True
        assert second_sent is False
        assert len(messages) == 1
        assert db.query(ProfitAlertLog).filter_by(factory_id=1, snapshot_date=TODAY).count() == 1
    finally:
        db.close()
        engine.dispose()


def test_api_routes_and_dashboard_contract_are_registered():
    from main import app

    paths = {route.path for route in app.routes}
    assert "/api/profit/today" in paths
    assert "/api/profit/history" in paths
    assert "/api/profit/per-size" in paths
    assert "/api/profit/per-size/history" in paths
    assert "/api/admin/profit-leaderboard" in paths


def test_briefing_renders_profit_section():
    snapshot = {
        "production": {"produced": 10, "target": 20, "gap": 10},
        "workers": {"present": 2, "absent": 1},
        "sales": {"invoice_count": 1, "amount": 100, "collections_received": 50, "outstanding_amount": 50},
        "risk_items": [],
        "profit": {
            "data_available": True,
            "revenue": 48000,
            "total_cost": 37500,
            "gross_profit": 10500,
            "profit_margin_percent": 21.875,
            "largest_profit_risk": "Material Cost",
        },
    }
    message = render_morning_briefing_message(snapshot, "Owner", "en")
    assert "💰 Profit Intelligence" in message
    assert "Revenue: ₹48,000" in message
    assert "Cost: ₹37,500" in message
    assert "Profit: ₹10,500" in message
    assert "Margin: 21.9%" in message
    assert "Risk: Material Cost" in message

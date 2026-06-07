from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import sessionmaker

from models import (
    AttendanceLog,
    BlankStock,
    BottomStock,
    Customer,
    DailyFactoryHealthSnapshot,
    Factory,
    Machine,
    Payment,
    SalesInvoice,
    Worker,
)
from services.briefing_service import render_morning_briefing_message
from services.factory_health import classify_health, compute_factory_health, inventory_score_for_days
from services.factory_health_scheduler import run_factory_health_batch, seconds_until_next_run
from services.timezone_utils import KOLKATA_ZONE
from tests.test_cost_per_cup import make_db, seed_production


TODAY = date.today()


def seed_health_fixture(db, factory_id: int = 1):
    seed_production(db, factory_id, TODAY - timedelta(days=1), boxes=10, material="100", labour="0", electricity="0")
    seed_production(db, factory_id, TODAY, boxes=80, material="800", labour="0", electricity="0")
    machines = db.query(Machine).filter(Machine.factory_id == factory_id).order_by(Machine.id).all()
    machines[0].target_output_per_shift = 100
    machines[1].target_output_per_shift = 0
    workers = [
        Worker(factory_id=factory_id, name=f"Worker {factory_id}-{index}", daily_wage_rate=0)
        for index in range(4)
    ]
    customer = Customer(factory_id=factory_id, name=f"Health Customer {factory_id}")
    db.add_all(workers + [customer])
    db.flush()
    db.add_all(
        [
            AttendanceLog(
                factory_id=factory_id,
                date=TODAY,
                worker_id=worker.id,
                status="Present" if index < 3 else "Absent",
                is_present=index < 3,
            )
            for index, worker in enumerate(workers)
        ]
    )
    db.add_all(
        [
            SalesInvoice(
                factory_id=factory_id,
                customer_id=customer.id,
                date=TODAY,
                cup_size_ml=100,
                packaging_profile_id=900 + factory_id,
                boxes_sold=1,
                total_amount=Decimal("1000"),
                amount_paid=Decimal("500"),
            ),
            Payment(factory_id=factory_id, customer_phone="111", amount_paid=Decimal("500"), date=TODAY),
            BlankStock(
                factory_id=factory_id,
                blank_size_ml=100,
                variety="Health",
                linked_bottom_size_mm=45,
                total_qty_kg=Decimal("1400"),
            ),
            BottomStock(
                factory_id=factory_id,
                bottom_size_mm=45,
                variety="Health",
                total_qty_kg=Decimal("1000"),
            ),
        ]
    )
    db.commit()


def test_score_calculation_and_weight_correctness():
    engine, db = make_db()
    try:
        seed_health_fixture(db)
        result = compute_factory_health(db, 1, TODAY)
        assert result["production_score"] == 80
        assert result["attendance_score"] == 75
        assert result["collections_score"] == 50
        assert result["inventory_score"] == 80
        assert result["cost_score"] == 100
        assert result["overall_score"] == 77.25
    finally:
        db.close()
        engine.dispose()


def test_health_classification_boundaries():
    assert classify_health(Decimal("49.99")) == "CRITICAL"
    assert classify_health(Decimal("50")) == "WARNING"
    assert classify_health(Decimal("70")) == "GOOD"
    assert classify_health(Decimal("85")) == "EXCELLENT"


def test_strength_and_risk_detection():
    engine, db = make_db()
    try:
        seed_health_fixture(db)
        result = compute_factory_health(db, 1, TODAY)
        assert result["largest_strength"] == "Cost"
        assert result["largest_risk"] == "Collections"
        assert result["health_status"] == "GOOD"
    finally:
        db.close()
        engine.dispose()


def test_inventory_score_rules():
    assert inventory_score_for_days(Decimal("14")) == 100
    assert inventory_score_for_days(Decimal("7")) == 80
    assert inventory_score_for_days(Decimal("3")) == 60
    assert inventory_score_for_days(Decimal("2.9")) == 30
    assert inventory_score_for_days(None) == 0


def test_factory_isolation():
    engine, db = make_db()
    try:
        seed_health_fixture(db, 1)
        seed_health_fixture(db, 2)
        db.query(Payment).filter(Payment.factory_id == 2).update({Payment.amount_paid: Decimal("999999")})
        db.commit()
        result = compute_factory_health(db, 1, TODAY)
        assert result["collections_score"] == 50
        assert db.query(DailyFactoryHealthSnapshot).filter_by(factory_id=2).count() == 0
    finally:
        db.close()
        engine.dispose()


def test_scheduler_execution_and_timing():
    engine, db = make_db()
    seed_health_fixture(db)
    db.close()
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    metrics = run_factory_health_batch(TODAY, session_factory=factory)
    verify = factory()
    try:
        assert metrics == {"total_factories": 1, "computed": 1, "failed": 0}
        assert verify.query(DailyFactoryHealthSnapshot).count() == 1
        before = datetime(2026, 6, 7, 23, 57, tzinfo=KOLKATA_ZONE)
        assert seconds_until_next_run(before) == 60
    finally:
        verify.close()
        engine.dispose()


def test_dashboard_and_admin_apis_are_registered():
    from main import app

    paths = {route.path for route in app.routes}
    assert "/api/factory-health/today" in paths
    assert "/api/admin/factory-health/leaderboard" in paths


def test_briefing_health_rendering():
    snapshot = {
        "production": {"produced": 10, "target": 20, "gap": 10},
        "workers": {"present": 2, "absent": 1},
        "sales": {"invoice_count": 1, "amount": 100, "collections_received": 50, "outstanding_amount": 50},
        "risk_items": [],
        "factory_health": {
            "overall_score": 82,
            "health_status": "GOOD",
            "largest_strength": "Attendance",
            "largest_risk": "Collections",
        },
    }
    message = render_morning_briefing_message(snapshot, "Owner", "en")
    assert "🏭 Factory Health" in message
    assert "Score: 82/100" in message
    assert "Status: GOOD" in message
    assert "Biggest Strength: Attendance" in message
    assert "Biggest Risk: Collections" in message


def test_same_day_recompute_upserts_snapshot():
    engine, db = make_db()
    try:
        seed_health_fixture(db)
        first = compute_factory_health(db, 1, TODAY)
        second = compute_factory_health(db, 1, TODAY)
        assert first["id"] == second["id"]
        assert db.query(DailyFactoryHealthSnapshot).filter_by(factory_id=1, snapshot_date=TODAY).count() == 1
    finally:
        db.close()
        engine.dispose()

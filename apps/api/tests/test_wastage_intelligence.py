from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy.orm import sessionmaker

from models import (
    CostingMaster,
    DailyProduction,
    DailyWastageSnapshot,
    Factory,
    FinalProductStock,
    Machine,
    WastageAlertLog,
)
from routers.wastage import wastage_history
from services.briefing_service import render_morning_briefing_message
from services.timezone_utils import KOLKATA_ZONE
from services.wastage_intelligence import compute_wastage_snapshot
from services.wastage_scheduler import run_wastage_batch, seconds_until_next_run
from tests.test_cost_per_cup import make_db


TODAY = date.today()


def seed_day(
    db,
    factory_id: int,
    production_date: date,
    *,
    blank: str,
    bottom: str,
    wastage: str,
    boxes: int = 1,
):
    factory = db.get(Factory, factory_id)
    if factory is None:
        db.add(Factory(id=factory_id, name=f"Wastage Factory {factory_id}", subscription_status="active"))
        db.flush()
        db.add(
            FinalProductStock(
                factory_id=factory_id,
                product_size_ml=100,
                variety="White",
                packaging_size_name="Standard",
                pieces_per_packet=100,
                packets_per_box_limit=10,
            )
        )
        db.add(
            CostingMaster(
                factory_id=factory_id,
                paper_price_per_kg=Decimal("100"),
                bottom_roll_price_per_kg=Decimal("50"),
            )
        )
    machine = Machine(factory_id=factory_id, name=f"W-{factory_id}-{production_date}", machine_type="Cup")
    db.add(machine)
    db.flush()
    db.add(
        DailyProduction(
            factory_id=factory_id,
            date=production_date,
            machine_id=machine.id,
            product_size_ml=100,
            variety="White",
            packaging_size_name="Standard",
            packets_per_box_limit=10,
            total_boxes_made=boxes,
            blank_used_kg=Decimal(blank),
            bottom_used_kg=Decimal(bottom),
            wastage_kg=Decimal(wastage),
            total_raw_material_kg=Decimal(blank) + Decimal(bottom),
        )
    )
    db.commit()


def seed_baseline(db, factory_id: int = 1):
    for days_ago in (3, 2, 1):
        seed_day(
            db,
            factory_id,
            TODAY - timedelta(days=days_ago),
            blank="10",
            bottom="2",
            wastage="1",
        )
    seed_day(db, factory_id, TODAY, blank="15", bottom="2", wastage="2")


def test_weighted_baseline_status_and_estimated_loss():
    engine, db = make_db()
    try:
        seed_baseline(db)
        result = compute_wastage_snapshot(db, 1, TODAY)
        assert result["expected_wastage_percentage"] == 8.3333
        assert result["wastage_percentage"] == 11.7647
        assert result["extra_wastage_percentage"] == 3.4314
        assert result["wastage_status"] == "CRITICAL"
        assert result["primary_wastage_source"] == "Blank"
        assert result["estimated_loss_paise"] == 20000
    finally:
        db.close()
        engine.dispose()


def test_historical_material_baseline_infers_wastage_without_explicit_value():
    engine, db = make_db()
    try:
        seed_baseline(db)
        row = db.query(DailyProduction).filter_by(factory_id=1, date=TODAY).one()
        row.wastage_kg = 0
        db.commit()
        result = compute_wastage_snapshot(db, 1, TODAY)
        assert result["actual_wastage_kg"] == 5
        assert result["primary_wastage_source"] == "Blank"
        assert result["estimated_loss_paise"] == 50000
    finally:
        db.close()
        engine.dispose()


def test_sufficient_zero_wastage_history_uses_zero_percent_baseline():
    engine, db = make_db()
    try:
        for days_ago in (3, 2, 1):
            seed_day(
                db,
                1,
                TODAY - timedelta(days=days_ago),
                blank="10",
                bottom="2",
                wastage="0",
            )
        seed_day(db, 1, TODAY, blank="10", bottom="2", wastage="0")

        result = compute_wastage_snapshot(db, 1, TODAY)

        assert result["baseline_source"] == "factory_30_day"
        assert result["expected_wastage_percentage"] == 0
        assert result["expected_wastage_kg"] == 0
    finally:
        db.close()
        engine.dispose()


def test_same_day_upsert_and_alert_are_idempotent():
    engine, db = make_db()
    try:
        seed_baseline(db)
        first = compute_wastage_snapshot(db, 1, TODAY)
        second = compute_wastage_snapshot(db, 1, TODAY)
        assert first["id"] == second["id"]
        assert db.query(DailyWastageSnapshot).filter_by(factory_id=1, snapshot_date=TODAY).count() == 1
        assert db.query(WastageAlertLog).filter_by(factory_id=1, snapshot_date=TODAY).count() == 1
    finally:
        db.close()
        engine.dispose()


def test_factory_isolation():
    engine, db = make_db()
    try:
        seed_baseline(db, 1)
        seed_baseline(db, 2)
        other = db.query(DailyProduction).filter_by(factory_id=2, date=TODAY).one()
        other.wastage_kg = Decimal("999")
        db.commit()
        result = compute_wastage_snapshot(db, 1, TODAY)
        assert result["actual_wastage_kg"] == 2
        assert db.query(DailyWastageSnapshot).filter_by(factory_id=2).count() == 0
    finally:
        db.close()
        engine.dispose()


def test_history_endpoint_is_factory_scoped():
    engine, db = make_db()
    try:
        seed_baseline(db, 1)
        seed_baseline(db, 2)
        compute_wastage_snapshot(db, 1, TODAY)
        compute_wastage_snapshot(db, 2, TODAY)
        response = wastage_history(days=30, current_user=SimpleNamespace(factory_id=1), db=db)
        assert len(response["items"]) == 1
        assert response["items"][0]["actual_wastage_kg"] == 2
    finally:
        db.close()
        engine.dispose()


def test_scheduler_execution_and_timing():
    engine, db = make_db()
    seed_baseline(db)
    db.close()
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    metrics = run_wastage_batch(TODAY, session_factory=factory)
    verify = factory()
    try:
        assert metrics == {"total_factories": 1, "computed": 1, "failed": 0}
        assert verify.query(DailyWastageSnapshot).count() == 1
        before = datetime(2026, 6, 7, 5, 59, tzinfo=KOLKATA_ZONE)
        assert seconds_until_next_run(before) == 60
    finally:
        verify.close()
        engine.dispose()


def test_api_routes_and_dashboard_contract_are_registered():
    from main import app

    paths = {route.path for route in app.routes}
    assert "/api/wastage/today" in paths
    assert "/api/wastage/history" in paths
    assert "/api/admin/wastage/leaderboard" in paths


def test_briefing_renders_wastage_section():
    snapshot = {
        "production": {"produced": 10, "target": 20, "gap": 10},
        "workers": {"present": 2, "absent": 1},
        "sales": {"invoice_count": 1, "amount": 100, "collections_received": 50, "outstanding_amount": 50},
        "risk_items": [],
        "wastage": {
            "blank_used_kg": 100,
            "bottom_used_kg": 20,
            "wastage_percentage": 6.2,
            "expected_wastage_percentage": 3.0,
            "extra_wastage_percentage": 3.2,
            "estimated_loss": 1240,
            "primary_wastage_source": "Blank",
        },
    }
    message = render_morning_briefing_message(snapshot, "Owner", "en")
    assert "⚠ Wastage" in message
    assert "Yesterday: 6.2%" in message
    assert "Expected: 3.0%" in message
    assert "Extra: +3.2%" in message
    assert "Estimated Loss: ₹1,240" in message
    assert "Source: Blank Material" in message


def test_weighted_trends_are_returned():
    engine, db = make_db()
    try:
        seed_baseline(db)
        result = compute_wastage_snapshot(db, 1, TODAY)
        assert result["seven_day_trend"] == 11.7647
        assert result["thirty_day_trend"] == 11.7647
    finally:
        db.close()
        engine.dispose()


def test_historical_baseline_with_zero_wastage():
    engine, db = make_db()
    try:
        for days_ago in (3, 2, 1):
            seed_day(
                db,
                factory_id=3,
                production_date=TODAY - timedelta(days=days_ago),
                blank="10",
                bottom="2",
                wastage="0",
            )
        seed_day(db, factory_id=3, production_date=TODAY, blank="15", bottom="2", wastage="1")

        result = compute_wastage_snapshot(db, 3, TODAY)
        assert result["expected_wastage_percentage"] == 0.0
        assert result["baseline_source"] == "factory_30_day"

        for days_ago in (2, 1):
            seed_day(
                db,
                factory_id=4,
                production_date=TODAY - timedelta(days=days_ago),
                blank="10",
                bottom="2",
                wastage="0",
            )
        seed_day(db, factory_id=4, production_date=TODAY, blank="15", bottom="2", wastage="1")

        result_insufficient = compute_wastage_snapshot(db, 4, TODAY)
        assert result_insufficient["expected_wastage_percentage"] == 2.0
        assert result_insufficient["baseline_source"] == "onboarding_default"
    finally:
        db.close()
        engine.dispose()


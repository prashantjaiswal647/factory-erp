from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy.orm import sessionmaker

from models import DailyFactoryHealthSnapshot, DailyProduction, DailyProfitSnapshot, Factory, Machine, User, WeeklyDigestLog, Worker
from routers.weekly_digest import digest_history
from services.timezone_utils import KOLKATA_ZONE
from services.weekly_digest_scheduler import deliver_weekly_digest, run_weekly_digest_batch, seconds_until_next_run
from services.weekly_profit_digest import build_weekly_digest, compute_weekly_digest, render_weekly_digest
from tests.test_cost_per_cup import make_db


SUNDAY = date(2026, 6, 7)
MONDAY = SUNDAY - timedelta(days=6)


def seed_week(db, factory_id: int = 1):
    factory = Factory(id=factory_id, name=f"Digest Factory {factory_id}", subscription_status="active")
    owner = User(
        factory_id=factory_id,
        username=f"digest-owner-{factory_id}",
        full_name=f"Owner {factory_id}",
        password_hash="unused",
        role="Owner",
        preferred_language="en",
        is_active=True,
    )
    db.add_all([factory, owner])
    db.flush()
    profits = [10000, 30000, -5000, 20000, -10000, 15000, 5000]
    revenues = [50000, 100000, 50000, 80000, 40000, 60000, 70000]
    risks = ["Collections", "Material Cost", "Collections", "Wastage", "Collections", "Material Cost", "Wastage"]
    for offset in range(7):
        day = MONDAY + timedelta(days=offset)
        db.add(
            DailyProfitSnapshot(
                factory_id=factory_id,
                snapshot_date=day,
                revenue_paise=revenues[offset],
                total_cost_paise=revenues[offset] - profits[offset],
                gross_profit_paise=profits[offset],
                material_cost_paise=0,
                labour_cost_paise=0,
                electricity_cost_paise=0,
                overhead_cost_paise=0,
                profit_margin_percent=Decimal(profits[offset]) / Decimal(revenues[offset]) * 100,
                profit_status="GOOD",
                largest_profit_risk=risks[offset],
            )
        )
        db.add(
            DailyFactoryHealthSnapshot(
                factory_id=factory_id,
                snapshot_date=day,
                production_score=80,
                attendance_score=80,
                collections_score=80,
                inventory_score=80,
                cost_score=80,
                overall_score=80 + offset,
                health_status="GOOD",
                largest_strength="Production",
                largest_risk="Collections",
            )
        )
    db.commit()
    return factory, owner


def test_weighted_margin_best_worst_and_risk_aggregation():
    engine, db = make_db()
    try:
        seed_week(db)
        result = compute_weekly_digest(db, 1, MONDAY, SUNDAY)
        assert result["revenue_paise"] == 450000
        assert result["profit_paise"] == 65000
        assert result["margin"] == 14.4
        assert result["health_score"] == 83
        assert result["best_day"] == "Tuesday"
        assert result["worst_day"] == "Friday"
        assert result["largest_risk"] == "Collections"
    finally:
        db.close()
        engine.dispose()


def test_factory_isolation():
    engine, db = make_db()
    try:
        seed_week(db, 1)
        seed_week(db, 2)
        db.query(DailyProfitSnapshot).filter_by(factory_id=2).update({DailyProfitSnapshot.gross_profit_paise: 999999})
        db.commit()
        result = compute_weekly_digest(db, 1, MONDAY, SUNDAY)
        assert result["profit_paise"] == 65000
    finally:
        db.close()
        engine.dispose()


def test_duplicate_delivery_prevention():
    engine, db = make_db()
    try:
        factory, owner = seed_week(db)
        messages = []
        first, sent_first = deliver_weekly_digest(db, factory, owner, SUNDAY, sender=lambda _factory, message: messages.append(message))
        second, sent_second = deliver_weekly_digest(db, factory, owner, SUNDAY, sender=lambda _factory, message: messages.append(message))
        assert first.id == second.id
        assert sent_first is True
        assert sent_second is False
        assert len(messages) == 1
        assert db.query(WeeklyDigestLog).count() == 1
    finally:
        db.close()
        engine.dispose()


def test_sunday_scheduler_timing_and_execution():
    engine, db = make_db()
    seed_week(db)
    db.close()
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    metrics = run_weekly_digest_batch(SUNDAY, session_factory=factory, sender=lambda *_: None)
    verify = factory()
    try:
        assert metrics == {"total_factories": 1, "sent": 1, "failed": 0}
        assert verify.query(WeeklyDigestLog).count() == 1
        before = datetime(2026, 6, 7, 19, 59, tzinfo=KOLKATA_ZONE)
        assert seconds_until_next_run(before) == 60
    finally:
        verify.close()
        engine.dispose()


def test_history_endpoint_is_factory_scoped():
    engine, db = make_db()
    try:
        factory, owner = seed_week(db, 1)
        other_factory, other_owner = seed_week(db, 2)
        deliver_weekly_digest(db, factory, owner, SUNDAY, sender=lambda *_: None)
        deliver_weekly_digest(db, other_factory, other_owner, SUNDAY, sender=lambda *_: None)
        result = digest_history(limit=12, current_user=SimpleNamespace(factory_id=1), db=db)
        assert len(result["items"]) == 1
        assert result["items"][0]["factory_id"] == 1
    finally:
        db.close()
        engine.dispose()


def test_api_routes_and_dashboard_contract():
    from main import app

    paths = {route.path for route in app.routes}
    assert "/api/weekly-digest/latest" in paths
    assert "/api/weekly-digest/history" in paths
    assert "/api/admin/weekly-digest" in paths


def test_translation_rendering_is_deterministic():
    engine, db = make_db()
    try:
        seed_week(db)
        digest = compute_weekly_digest(db, 1, MONDAY, SUNDAY)
        english = render_weekly_digest(digest, "en")
        hindi = render_weekly_digest(digest, "hi")
        hinglish = render_weekly_digest(digest, "hinglish")
        assert english == render_weekly_digest(digest, "en")
        assert "📊 Weekly Factory Review" in english
        assert "📊 साप्ताहिक फैक्ट्री समीक्षा" in hindi
        assert "Is hafte pending payments ka follow-up karein." in hinglish
    finally:
        db.close()
        engine.dispose()


def test_build_digest_contains_message_and_week_bounds():
    engine, db = make_db()
    try:
        seed_week(db)
        result = build_weekly_digest(db, 1, SUNDAY, "en")
        assert result["week_start"] == MONDAY.isoformat()
        assert result["week_end"] == SUNDAY.isoformat()
        assert "Margin:\n14.4%" in result["message_text"]
    finally:
        db.close()
        engine.dispose()


def test_weekly_digest_includes_production_consumption_and_breakdowns():
    engine, db = make_db()
    try:
        seed_week(db)
        worker = Worker(factory_id=1, name="Raju", daily_wages=Decimal("500"))
        machine = Machine(factory_id=1, name="M1", machine_type="Cup")
        db.add_all([worker, machine])
        db.flush()
        db.add_all(
            [
                DailyProduction(
                    factory_id=1,
                    date=MONDAY,
                    worker_id=worker.id,
                    machine_id=machine.id,
                    product_size_ml=210,
                    variety="Cup",
                    packaging_size_name="210ml Box",
                    packets_per_box_limit=10,
                    total_boxes_made=50,
                    loose_packets_made=3,
                    boxes_from_loose=0,
                    blank_used_bora=Decimal("2"),
                    blank_weight_per_bora_kg=Decimal("40"),
                    blank_used_kg=Decimal("80"),
                    bottom_used_rolls=1,
                    bottom_used_kg=Decimal("5"),
                ),
                DailyProduction(
                    factory_id=1,
                    date=MONDAY + timedelta(days=1),
                    worker_id=worker.id,
                    machine_id=machine.id,
                    product_size_ml=250,
                    variety="Cup",
                    packaging_size_name="250ml Box",
                    packets_per_box_limit=10,
                    total_boxes_made=35,
                    loose_packets_made=2,
                    boxes_from_loose=0,
                    blank_used_bora=Decimal("1"),
                    blank_weight_per_bora_kg=Decimal("40"),
                    blank_used_kg=Decimal("40"),
                    bottom_used_rolls=2,
                    bottom_used_kg=Decimal("10"),
                ),
            ]
        )
        db.commit()

        result = build_weekly_digest(db, 1, SUNDAY, "en")

        assert result["blank_bora_used"] == 3
        assert result["blank_kg_used"] == 120
        assert result["bottom_rolls_used"] == 3
        assert result["boxes_produced"] == 85
        assert result["loose_packets_produced"] == 5
        assert result["top_worker"] == {"worker_name": "Raju", "boxes": 85}
        assert result["product_production"] == [
            {"product": "210ml Cup", "boxes": 50},
            {"product": "250ml Cup", "boxes": 35},
        ]
        assert "Blank Used: 3 bora / 120 KG" in result["message_text"]
        assert "Top Worker: Raju - 85 boxes" in result["message_text"]
    finally:
        db.close()
        engine.dispose()

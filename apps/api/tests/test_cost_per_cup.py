from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import (
    AttendanceLog,
    CostingMaster,
    CostPerCupDaily,
    DailyProduction,
    ExpenseLog,
    Factory,
    FinalProductStock,
    Machine,
    Worker,
)
from services.briefing_service import render_morning_briefing_message
from services.cost_engine import MISSING, compute_cost_window, compute_daily_cost


TODAY = date.today()


def make_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autocommit=False, autoflush=False)()


def seed_production(
    db,
    factory_id: int,
    production_date: date,
    *,
    boxes: int,
    material: str = "100",
    labour: str = "50",
    electricity: str = "25",
):
    factory = db.get(Factory, factory_id)
    if factory is None:
        factory = Factory(id=factory_id, name=f"Cost Factory {factory_id}", subscription_status="active")
        db.add(factory)
        db.flush()
    machine = Machine(
        factory_id=factory_id,
        name=f"Machine {factory_id}-{production_date}",
        machine_type="Cup",
    )
    db.add(machine)
    db.flush()
    stock = db.query(FinalProductStock).filter_by(factory_id=factory_id).first()
    if stock is None:
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
            raw_material_cost=Decimal(material),
            labor_cost=Decimal(labour),
            electricity_cost=Decimal(electricity),
        )
    )
    db.commit()


def test_daily_cost_calculation_and_upsert_are_deterministic():
    engine, db = make_db()
    try:
        seed_production(db, 1, TODAY, boxes=2)
        first = compute_daily_cost(db, 1, TODAY)
        second = compute_daily_cost(db, 1, TODAY)
        assert first["cups_produced_total"] == 2000
        assert first["total_production_cost_paise"] == 17500
        assert first["cost_per_cup"] == "0.0875"
        assert second["id"] == first["id"]
        assert db.query(CostPerCupDaily).filter_by(factory_id=1, production_date=TODAY).count() == 1
    finally:
        db.close()
        engine.dispose()


def test_factory_isolation():
    engine, db = make_db()
    try:
        seed_production(db, 1, TODAY, boxes=1, material="100")
        seed_production(db, 2, TODAY, boxes=9, material="900")
        result = compute_daily_cost(db, 1, TODAY)
        assert result["cups_produced_total"] == 1000
        assert result["total_material_cost_paise"] == 10000
        assert db.query(CostPerCupDaily).filter_by(factory_id=2).count() == 0
    finally:
        db.close()
        engine.dispose()


def test_zero_cups_returns_data_not_available():
    engine, db = make_db()
    try:
        seed_production(db, 1, TODAY, boxes=0)
        result = compute_daily_cost(db, 1, TODAY)
        assert result["cost_per_cup"] == MISSING
        assert result["loaded_cost_per_cup"] == MISSING
    finally:
        db.close()
        engine.dispose()


def test_missing_cost_fields_are_tracked():
    engine, db = make_db()
    try:
        seed_production(db, 1, TODAY, boxes=1, material="0", labour="0", electricity="0")
        result = compute_daily_cost(db, 1, TODAY)
        assert {"material_cost", "labour_cost", "electricity_cost"}.issubset(result["missing_fields"])
        assert result["source_quality"] == "partial"
    finally:
        db.close()
        engine.dispose()


def test_material_and_labour_fallback_hierarchy():
    engine, db = make_db()
    try:
        seed_production(db, 1, TODAY, boxes=1, material="0", labour="0", electricity="25")
        production = db.query(DailyProduction).filter_by(factory_id=1, date=TODAY).one()
        production.blank_used_kg = Decimal("2")
        production.bottom_used_kg = Decimal("1")
        worker = Worker(factory_id=1, name="Fallback Worker", daily_wage_rate=Decimal("300"))
        db.add_all(
            [
                CostingMaster(
                    factory_id=1,
                    paper_price_per_kg=Decimal("10"),
                    bottom_roll_price_per_kg=Decimal("20"),
                ),
                worker,
            ]
        )
        db.flush()
        db.add(
            AttendanceLog(
                factory_id=1,
                date=TODAY,
                worker_id=worker.id,
                status="Present",
                is_present=True,
            )
        )
        db.commit()
        result = compute_daily_cost(db, 1, TODAY)
        assert result["total_material_cost_paise"] == 4000
        assert result["total_labour_cost_paise"] == 30000
        assert "material_cost" not in result["missing_fields"]
        assert "labour_cost" not in result["missing_fields"]
    finally:
        db.close()
        engine.dispose()


def test_multi_day_cost_is_weighted_not_simple_daily_average():
    engine, db = make_db()
    try:
        seed_production(db, 1, TODAY - timedelta(days=1), boxes=1, material="75", labour="0", electricity="0")
        seed_production(db, 1, TODAY, boxes=3, material="525", labour="0", electricity="0")
        result = compute_cost_window(db, 1, 7)
        assert result["cups_produced_total"] == 4000
        assert result["weighted_cost_per_cup"] == "0.1500"
        assert result["weighted_cost_per_cup"] != "0.1250"
    finally:
        db.close()
        engine.dispose()


def test_empty_window_never_returns_fake_zero_cpc():
    engine, db = make_db()
    try:
        db.add(Factory(id=1, name="Empty Cost Factory", subscription_status="active"))
        db.commit()
        result = compute_cost_window(db, 1, 7)
        assert result["weighted_cost_per_cup"] == MISSING
        assert result["weighted_loaded_cost_per_cup"] == MISSING
    finally:
        db.close()
        engine.dispose()


def test_raw_material_purchase_expense_is_not_double_counted():
    engine, db = make_db()
    try:
        seed_production(db, 1, TODAY, boxes=1)
        db.add_all(
            [
                ExpenseLog(
                    factory_id=1,
                    date=TODAY,
                    category="Raw Material",
                    description="Blank purchase",
                    amount=Decimal("1000"),
                ),
                ExpenseLog(
                    factory_id=1,
                    date=TODAY,
                    category="Rent",
                    description="Daily overhead",
                    amount=Decimal("100"),
                ),
            ]
        )
        db.commit()
        result = compute_daily_cost(db, 1, TODAY)
        assert result["total_overhead_cost_paise"] == 10000
        assert result["total_loaded_cost_paise"] == 27500
    finally:
        db.close()
        engine.dispose()


def test_briefing_renders_cost_section():
    snapshot = {
        "production": {"produced": 10, "target": 20, "gap": 10},
        "workers": {"present": 2, "absent": 1},
        "sales": {"invoice_count": 1, "amount": 100, "collections_received": 50, "outstanding_amount": 50},
        "risk_items": [],
        "cost": {
            "has_cost_data": True,
            "cost_per_cup": "0.7500",
            "loaded_cost_per_cup": "0.9000",
            "source_quality": "partial",
        },
    }
    message = render_morning_briefing_message(snapshot, "Owner", "en")
    assert "💰 Cost Intelligence" in message
    assert "Cost Per Cup: ₹0.7500" in message
    assert "Loaded Cost Per Cup: ₹0.9000" in message
    assert "Data Quality: Partial" in message

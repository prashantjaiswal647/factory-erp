from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from models import CostPerCupDaily, Customer, DailyProduction, FinalProductStock, Machine, PerSizeDaily, SalesInvoice
from routers.profit import per_size_profit, per_size_profit_history
from services.briefing_service import render_morning_briefing_message
from services.profit_intelligence import MISSING, compute_per_size_profit, persist_per_size_profit
from tests.test_cost_per_cup import make_db, seed_production


TODAY = date.today()


def _invoice(db, factory_id: int, size: int, revenue: str):
    customer = Customer(factory_id=factory_id, name=f"Customer {factory_id}-{size}")
    db.add(customer)
    db.flush()
    db.add(
        SalesInvoice(
            factory_id=factory_id,
            customer_id=customer.id,
            date=TODAY,
            cup_size_ml=size,
            packaging_profile_id=1000 + factory_id + size,
            boxes_sold=1,
            total_amount=Decimal(revenue),
            amount_paid=Decimal(revenue),
        )
    )


def _production(db, factory_id: int, size: int, material: str, labour: str = "0"):
    existing = db.query(DailyProduction).filter_by(factory_id=factory_id, date=TODAY).first()
    if existing is None:
        seed_production(db, factory_id, TODAY, boxes=1, material=material, labour=labour, electricity="0")
        row = db.query(DailyProduction).filter_by(factory_id=factory_id, date=TODAY).order_by(DailyProduction.id.desc()).first()
        row.product_size_ml = size
    else:
        machine = db.query(Machine).filter_by(factory_id=factory_id).first()
        db.add(
            DailyProduction(
                factory_id=factory_id,
                date=TODAY,
                machine_id=machine.id,
                product_size_ml=size,
                variety="White",
                packaging_size_name="Standard",
                packets_per_box_limit=10,
                total_boxes_made=1,
                raw_material_cost=Decimal(material),
                labor_cost=Decimal(labour),
                electricity_cost=Decimal("0"),
            )
        )
    if db.query(FinalProductStock).filter_by(factory_id=factory_id, product_size_ml=size).first() is None:
        db.add(
            FinalProductStock(
                factory_id=factory_id,
                product_size_ml=size,
                variety="White",
                packaging_size_name="Standard",
                pieces_per_packet=100,
                packets_per_box_limit=10,
            )
        )
    db.commit()


def test_per_size_grouping_weighted_margin_rankings_and_order():
    engine, db = make_db()
    try:
        _production(db, 1, 250, "400", "100")
        _production(db, 1, 100, "250", "50")
        _invoice(db, 1, 250, "1000")
        _invoice(db, 1, 100, "500")
        db.commit()

        result = compute_per_size_profit(db, 1, TODAY)
        assert [item["size_ml"] for item in result["sizes"]] == [100, 250]
        assert result["sizes"][0]["revenue_paise"] == 50000
        assert result["sizes"][0]["cost_paise"] == 30000
        assert result["sizes"][1]["cost_paise"] == 50000
        assert result["weighted_margin"] == 46.6667
        assert result["best_size"]["size_ml"] == 250
        assert result["worst_size"]["size_ml"] == 100
    finally:
        db.close()
        engine.dispose()


def test_sized_cost_snapshot_has_priority_over_production_cost():
    engine, db = make_db()
    try:
        _production(db, 1, 250, "400", "100")
        _invoice(db, 1, 250, "1000")
        db.add(
            CostPerCupDaily(
                factory_id=1,
                production_date=TODAY,
                size_ml=250,
                cups_produced_total=1000,
                total_material_cost_paise=10000,
                total_labour_cost_paise=5000,
                total_electricity_cost_paise=0,
                total_overhead_cost_paise=5000,
                total_production_cost_paise=15000,
                source_quality="complete",
                missing_fields_json=[],
            )
        )
        db.commit()
        item = compute_per_size_profit(db, 1, TODAY)["sizes"][0]
        assert item["cost_paise"] == 20000
        assert item["cost_source"] == "CostPerCupDaily"
        assert item["units_produced"] == 1000
    finally:
        db.close()
        engine.dispose()


def test_missing_size_cost_never_uses_blended_factory_cost():
    engine, db = make_db()
    try:
        _invoice(db, 1, 100, "500")
        db.add(
            CostPerCupDaily(
                factory_id=1,
                production_date=TODAY,
                size_ml=None,
                cups_produced_total=1000,
                total_material_cost_paise=10000,
                total_labour_cost_paise=5000,
                total_electricity_cost_paise=0,
                total_overhead_cost_paise=0,
                total_production_cost_paise=15000,
                source_quality="complete",
                missing_fields_json=[],
            )
        )
        db.commit()
        result = compute_per_size_profit(db, 1, TODAY)
        assert result["sizes"][0]["cost_paise"] == MISSING
        assert result["sizes"][0]["status"] == "DATA_NOT_AVAILABLE"
        assert result["weighted_margin"] == MISSING
    finally:
        db.close()
        engine.dispose()


def test_factory_isolation_and_owner_route_scope():
    engine, db = make_db()
    try:
        _production(db, 1, 100, "100")
        _production(db, 2, 250, "900")
        _invoice(db, 1, 100, "500")
        _invoice(db, 2, 250, "9000")
        db.commit()
        direct = compute_per_size_profit(db, 1, TODAY)
        routed = per_size_profit(TODAY, SimpleNamespace(factory_id=1), db)
        assert [item["size_ml"] for item in direct["sizes"]] == [100]
        assert routed == direct
        assert "900000" not in str(direct)
    finally:
        db.close()
        engine.dispose()


def test_briefing_renders_compact_per_size_section_and_missing_state():
    base = {
        "production": {"produced": None, "target": None, "gap": None},
        "workers": {"present": None, "absent": None},
        "sales": {"invoice_count": None, "amount": None, "collections_received": None, "outstanding_amount": None},
        "risk_items": [],
        "per_size_profit": {
            "data_available": True,
            "best_size": {"size_ml": 250, "margin_percent": 32.0},
            "worst_size": {"size_ml": 100, "margin_percent": 4.0},
        },
    }
    rendered = render_morning_briefing_message(base, "Owner", "en")
    assert "Per-Size Profit\nBest Size: 250 ml\nMargin: 32.0%\nWorst Size: 100 ml\nMargin: 4.0%" in rendered
    base["per_size_profit"] = {"data_available": False, "best_size": None, "worst_size": None}
    assert "Per-Size Profit" not in render_morning_briefing_message(base, "Owner", "en")


def test_per_size_translations_for_hindi_and_hinglish():
    snapshot = {
        "production": {"produced": None, "target": None, "gap": None},
        "workers": {"present": None, "absent": None},
        "sales": {"invoice_count": None, "amount": None, "collections_received": None, "outstanding_amount": None},
        "risk_items": [],
        "per_size_profit": {
            "data_available": True,
            "best_size": {"size_ml": 250, "margin_percent": 32.0},
            "worst_size": {"size_ml": 100, "margin_percent": 4.0},
        },
    }
    hindi = render_morning_briefing_message(snapshot, "Owner", "hi")
    hinglish = render_morning_briefing_message(snapshot, "Owner", "hinglish")
    assert "प्रति आकार लाभ" in hindi
    assert "सबसे लाभदायक आकार: 250 ml" in hindi
    assert "सबसे कम लाभ वाला आकार: 100 ml" in hindi
    assert "Size-wise Profit" in hinglish
    assert "Sabse Achha Size: 250 ml" in hinglish
    assert "Sabse Kam Margin Size: 100 ml" in hinglish


def test_summary_mode_is_byte_stable_and_short():
    snapshot = {
        "production": {"produced": 100, "target": 120, "gap": 20},
        "workers": {"present": 10, "absent": 2},
        "sales": {"invoice_count": 2, "amount": 1000, "collections_received": 500, "outstanding_amount": 500},
        "risk_items": [],
        "factory_health": {"overall_score": 82, "largest_risk": "Collections"},
        "profit": {"data_available": True, "gross_profit": 10500},
        "per_size_profit": {
            "data_available": True,
            "best_size": {"size_ml": 250},
            "worst_size": {"size_ml": 100},
        },
    }
    first = render_morning_briefing_message(snapshot, "Owner", "en", summary_mode=True)
    second = render_morning_briefing_message(snapshot, "Owner", "en", summary_mode=True)
    assert first.encode("utf-8") == second.encode("utf-8")
    assert first == (
        "Good Morning Owner\n\n"
        "🏭 Factory Health\n"
        "Score: 82/100\n"
        "Biggest Risk: Collections\n\n"
        "💰 Profit Intelligence\n"
        "Profit: ₹10,500.00\n\n"
        "Per-Size Profit\n"
        "Best Size: 250 ml\n"
        "Worst Size: 100 ml\n\n"
        "* Munshi AI"
    )
    assert "Production Yesterday" not in first


def test_history_reads_persisted_rows_and_is_factory_scoped():
    engine, db = make_db()
    try:
        _production(db, 1, 100, "100")
        _production(db, 2, 250, "900")
        _invoice(db, 1, 100, "500")
        _invoice(db, 2, 250, "9000")
        db.commit()
        persist_per_size_profit(db, 1, TODAY)
        persist_per_size_profit(db, 2, TODAY)
        db.commit()

        db.query(SalesInvoice).delete()
        db.query(DailyProduction).delete()
        db.commit()
        response = per_size_profit_history(days=30, current_user=SimpleNamespace(factory_id=1), db=db)

        assert len(response["items"]) == 1
        assert [item["size_ml"] for item in response["items"][0]["sizes"]] == [100]
        assert response["items"][0]["total_revenue"] == 50000
        assert db.query(PerSizeDaily).filter_by(factory_id=2).count() == 1
    finally:
        db.close()
        engine.dispose()

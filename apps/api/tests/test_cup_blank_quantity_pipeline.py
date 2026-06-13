from decimal import Decimal
from types import SimpleNamespace

from fastapi import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import BlankStock, Factory, Inventory
from routers.inventory import list_live_stock
from routers.onboarding import apply_bulk_rows, validate_bulk_frame


def make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    return engine, SessionLocal()


def test_cup_blank_quantity_source_telemetry_and_factory_isolation():
    engine, db = make_session()
    try:
        factory_a = Factory(name="Blank Quantity Factory A")
        factory_b = Factory(name="Blank Quantity Factory B")
        db.add_all([factory_a, factory_b])
        db.flush()

        db.add_all(
            [
                BlankStock(
                    factory_id=factory_a.id,
                    blank_size_ml=100,
                    linked_bottom_size_mm=100,
                    variety="White",
                    weight_per_bora_kg=Decimal("50"),
                    total_boras=Decimal("0"),
                    total_qty_kg=Decimal("0"),
                ),
                BlankStock(
                    factory_id=factory_a.id,
                    blank_size_ml=200,
                    linked_bottom_size_mm=200,
                    variety="White",
                    weight_per_bora_kg=Decimal("50"),
                    total_boras=Decimal("20"),
                    total_qty_kg=Decimal("1000"),
                ),
                BlankStock(
                    factory_id=factory_b.id,
                    blank_size_ml=300,
                    linked_bottom_size_mm=300,
                    variety="White",
                    weight_per_bora_kg=Decimal("50"),
                    total_boras=Decimal("10"),
                    total_qty_kg=Decimal("500"),
                ),
                Inventory(
                    factory_id=factory_a.id,
                    item_name="Legacy Unknown Inventory",
                    category=None,
                    unit="pieces",
                    quantity=Decimal("3"),
                ),
            ]
        )
        db.commit()

        response = Response()
        rows = list_live_stock(
            current_user=SimpleNamespace(factory_id=factory_a.id),
            db=db,
            response=response,
        )
        blank_rows = [row for row in rows if row["bucket"] == "cup_blanks"]
        by_size = {row["size_ml"]: row for row in blank_rows}

        assert len(blank_rows) == 2
        assert by_size[100]["quantity"] == 0
        assert by_size[100]["quantity_source"] == "not_recorded"
        assert by_size[200]["quantity"] == 1000
        assert by_size[200]["quantity_source"] == "excel_upload"
        assert all(row["factory_id"] == factory_a.id for row in rows)

        unknown = next(row for row in rows if row["stock_type"] == "Inventory")
        assert unknown["item_name"] == "Legacy Unknown Inventory"
        assert unknown["bucket"] == "needs_mapping_review"
        assert unknown["quantity_source"] is None

        warning_header = response.headers["X-Inventory-Warnings"]
        assert warning_header
        assert all(part.endswith("=0") for part in warning_header.split(","))
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_blank_stock_bulk_row_without_total_boras_is_accepted():
    import pandas as pd

    frame = pd.DataFrame(
        [
            {
                "row_type": "ACTUAL",
                "material_name": "Plain White",
                "size_ml": 250,
                "kg_per_sack": 20,
            }
        ]
    )

    valid_rows, failed_rows = validate_bulk_frame(frame, "blank_stock")

    assert failed_rows == []
    assert len(valid_rows) == 1
    assert "total_boras" not in valid_rows[0]

    engine, db = make_session()
    try:
        factory = Factory(name="Blank Parser Factory")
        db.add(factory)
        db.flush()

        saved = apply_bulk_rows(
            db,
            SimpleNamespace(factory_id=factory.id),
            "blank_stock",
            valid_rows,
        )
        db.commit()

        stock = db.query(BlankStock).filter(BlankStock.factory_id == factory.id).one()
        assert saved == 1
        assert stock.weight_per_bora_kg == Decimal("20")
        assert stock.total_boras == Decimal("0")
        assert stock.total_qty_kg == Decimal("0")
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_blank_stock_bulk_quantity_is_calculated_and_visible_in_inventory():
    import pandas as pd

    frame = pd.DataFrame(
        [
            {
                "row_type": "ACTUAL",
                "material_name": "Plain White",
                "size_ml": 250,
                "kg_per_sack": 20,
                "total_boras_sacks": 12,
            }
        ]
    )
    valid_rows, failed_rows = validate_bulk_frame(frame, "blank_stock")

    assert failed_rows == []
    assert valid_rows[0]["total_boras_sacks"] == Decimal("12")

    engine, db = make_session()
    try:
        factory_a = Factory(name="New Blank Format Factory A")
        factory_b = Factory(name="New Blank Format Factory B")
        db.add_all([factory_a, factory_b])
        db.flush()

        apply_bulk_rows(db, SimpleNamespace(factory_id=factory_a.id), "blank_stock", valid_rows)
        apply_bulk_rows(db, SimpleNamespace(factory_id=factory_b.id), "blank_stock", valid_rows)
        db.commit()

        stock_a = db.query(BlankStock).filter(BlankStock.factory_id == factory_a.id).one()
        stock_b = db.query(BlankStock).filter(BlankStock.factory_id == factory_b.id).one()
        assert stock_a.total_boras == Decimal("12")
        assert stock_a.total_qty_kg == Decimal("240")
        assert stock_b.id != stock_a.id

        rows = list_live_stock(current_user=SimpleNamespace(factory_id=factory_a.id), db=db)
        blank_rows = [row for row in rows if row["bucket"] == "cup_blanks"]
        assert len(blank_rows) == 1
        assert blank_rows[0]["factory_id"] == factory_a.id
        assert blank_rows[0]["quantity"] == 240
        assert blank_rows[0]["quantity_source"] == "excel_upload"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_owner_friendly_cup_blank_import_pipeline():
    import pandas as pd
    # 1. owner-friendly Cup_Blank import with 10 bora, 40 kg/bora shows 400 kg in inventory
    frame = pd.DataFrame(
        [
            {
                "row_type": "ACTUAL",
                "Blank Description": "Paper Blanks",
                "Cup Size ML": 150,
                "Design / Variety Name": "White Cup",
                "Weight per Bora KG": 40,
                "Opening Boras": 10,
            }
        ]
    )
    # We must mock OWNER_HEADER_ALIASES mapping
    from routers.onboarding import OWNER_HEADER_ALIASES, canonical_bulk_header
    mapped_cols = []
    for col in frame.columns:
        canonical = canonical_bulk_header(col)
        mapped = OWNER_HEADER_ALIASES["blank_stock"].get(canonical, canonical)
        mapped_cols.append(mapped)
    frame.columns = mapped_cols

    valid_rows, failed_rows = validate_bulk_frame(frame, "blank_stock")
    assert failed_rows == []
    assert len(valid_rows) == 1
    assert valid_rows[0]["total_boras_sacks"] == Decimal("10")
    assert valid_rows[0]["weight_per_bora_kg"] == Decimal("40")

    engine, db = make_session()
    try:
        factory = Factory(name="Owner Friendly Test Factory")
        db.add(factory)
        db.flush()

        # Apply
        apply_bulk_rows(db, SimpleNamespace(factory_id=factory.id), "blank_stock", valid_rows)
        db.commit()

        stock = db.query(BlankStock).filter(BlankStock.factory_id == factory.id).one()
        assert stock.total_boras == Decimal("10")
        assert stock.total_qty_kg == Decimal("400")

        # Check inventory API
        rows = list_live_stock(current_user=SimpleNamespace(factory_id=factory.id), db=db)
        blank_rows = [row for row in rows if row["bucket"] == "cup_blanks"]
        assert len(blank_rows) == 1
        assert blank_rows[0]["quantity"] == 400
        assert blank_rows[0]["total_boras"] == 10
        assert blank_rows[0]["weight_per_bora_kg"] == 40

        # 2. re-upload same sheet does not reset stock to 0
        apply_bulk_rows(db, SimpleNamespace(factory_id=factory.id), "blank_stock", valid_rows)
        db.commit()
        stock = db.query(BlankStock).filter(BlankStock.factory_id == factory.id).one()
        assert stock.total_boras == Decimal("10")
        assert stock.total_qty_kg == Decimal("400")

        # 3. old template kg_per_sack alias still works
        old_frame = pd.DataFrame(
            [
                {
                    "row_type": "ACTUAL",
                    "material_name": "Plain White",
                    "size_ml": 150,
                    "kg_per_sack": 35,
                    "quantity_of_total_bora": 5,
                }
            ]
        )
        mapped_old = []
        for col in old_frame.columns:
            canonical = canonical_bulk_header(col)
            mapped = OWNER_HEADER_ALIASES["blank_stock"].get(canonical, canonical)
            mapped_old.append(mapped)
        old_frame.columns = mapped_old

        v_rows, f_rows = validate_bulk_frame(old_frame, "blank_stock")
        assert f_rows == []
        assert v_rows[0]["weight_per_bora_kg"] == Decimal("35")
        assert v_rows[0]["total_boras_sacks"] == Decimal("5")

        # 4. missing bora quantity gives validation error
        bad_frame = pd.DataFrame(
            [
                {
                    "row_type": "ACTUAL",
                    "material_name": "Plain White",
                    "size_ml": 150,
                    "weight_per_bora_kg": 40,
                    "Opening Bora Quantity (typo)": 10,
                }
            ]
        )
        mapped_bad = []
        for col in bad_frame.columns:
            canonical = canonical_bulk_header(col)
            mapped = OWNER_HEADER_ALIASES["blank_stock"].get(canonical, canonical)
            mapped_bad.append(mapped)
        bad_frame.columns = mapped_bad

        v_bad, f_bad = validate_bulk_frame(bad_frame, "blank_stock")
        assert len(f_bad) == 1
        assert "Opening Bora Quantity could not be mapped" in f_bad[0]["error"]

    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

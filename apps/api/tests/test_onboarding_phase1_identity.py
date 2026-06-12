from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import (
    BlankStock,
    BottomStock,
    BoxStock,
    Customer,
    Factory,
    FinalProductStock,
)
from routers.inventory import production_mapping_issue
from routers.onboarding import apply_bulk_rows, validate_bulk_cross_sheet


def make_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    session.add(Factory(id=1, name="Identity Factory"))
    session.commit()
    return engine, session


def test_customer_restore_keys_keep_same_name_customers_separate_and_reupload_is_idempotent():
    engine, db = make_db()
    user = SimpleNamespace(id=1, factory_id=1)
    rows = [
        {
            "row_type": "ACTUAL", "customer_restore_key": "CUS-1", "name": "Raj Traders",
            "firm_name": "North Firm", "phone_number": "9876500001", "contact_number": "",
            "email": "", "place": "Delhi", "address": "", "gst_number": "",
            "previous_due": Decimal("0"), "opening_outstanding_date": None,
            "opening_outstanding_note": "", "advance_balance": Decimal("0"),
            "advance_balance_date": None, "advance_balance_note": "",
        },
        {
            "row_type": "ACTUAL", "customer_restore_key": "CUS-2", "name": "Raj Traders",
            "firm_name": "South Firm", "phone_number": "9876500002", "contact_number": "",
            "email": "", "place": "Delhi", "address": "", "gst_number": "",
            "previous_due": Decimal("0"), "opening_outstanding_date": None,
            "opening_outstanding_note": "", "advance_balance": Decimal("0"),
            "advance_balance_date": None, "advance_balance_note": "",
        },
    ]
    try:
        apply_bulk_rows(db, user, "customer", rows, {})
        db.commit()
        apply_bulk_rows(db, user, "customer", rows, {})
        db.commit()
        customers = db.query(Customer).order_by(Customer.customer_restore_key).all()
        assert len(customers) == 2
        assert [row.customer_restore_key for row in customers] == ["CUS-1", "CUS-2"]
    finally:
        db.close()
        engine.dispose()


def test_material_identity_fields_and_finished_goods_loose_packets_are_preserved():
    engine, db = make_db()
    user = SimpleNamespace(id=1, factory_id=1)
    try:
        apply_bulk_rows(db, user, "blank_stock", [{
            "row_type": "ACTUAL", "material_restore_key": "BL-210",
            "material_name": "Premium Paper Blank", "variety_design": "Blue Print",
            "size_ml": 210, "linked_bottom_size_mm": 68,
            "weight_per_bora_kg": Decimal("40"), "total_boras_sacks": Decimal("2"),
        }], {})
        apply_bulk_rows(db, user, "bottom_reel", [{
            "row_type": "ACTUAL", "material_restore_key": "BT-68",
            "bottom_size_mm": 68, "variety_design": "Blue Print",
            "total_individual_rolls": 10, "total_weight_kg": Decimal("20"),
            "bottom_price_per_kg": Decimal("110"),
        }], {})
        apply_bulk_rows(db, user, "finished_goods", [{
            "row_type": "ACTUAL", "product_restore_key": "SKU-210-BLUE",
            "product_size_ml": 210, "variety_design": "Blue Print",
            "packaging_size_name": "210 Blue Box", "pcs_per_packet": 100,
            "packets_per_box": 10, "initial_stock_boxes": 5, "initial_loose_packets": 3,
        }], {})
        db.commit()

        blank = db.query(BlankStock).one()
        bottom = db.query(BottomStock).one()
        product = db.query(FinalProductStock).one()
        assert blank.material_name == "Premium Paper Blank"
        assert blank.variety == "Blue Print"
        assert blank.linked_bottom_size_mm == 68
        assert blank.linked_bottom_size_mm != blank.blank_size_ml
        assert bottom.variety == "Blue Print"
        assert bottom.price_per_kg == Decimal("110")
        assert product.product_restore_key == "SKU-210-BLUE"
        assert product.loose_packets == 3
    finally:
        db.close()
        engine.dispose()


def test_production_mapping_guard_rejects_incomplete_and_accepts_complete_sku():
    engine, db = make_db()
    try:
        product = FinalProductStock(
            factory_id=1, product_size_ml=210, variety="Blue Print",
            packaging_size_name="210 Blue Box", pieces_per_packet=100,
            packets_per_box_limit=10, total_boxes=0, loose_packets=0, current_quantity=0,
        )
        db.add(product)
        db.commit()
        assert production_mapping_issue(db, "1", product) == "Inventory mapping incomplete for this SKU."

        db.add_all([
            BlankStock(
                factory_id=1, blank_size_ml=210, variety="Blue Print",
                material_name="Paper", linked_bottom_size_mm=68,
                weight_per_bora_kg=40, total_boras=2, total_qty_kg=80,
            ),
            BottomStock(
                factory_id=1, bottom_size_mm=68, variety="Blue Print",
                total_rolls=10, total_weight_kg=20, total_qty_kg=20,
            ),
            BoxStock(
                factory_id=1, packaging_size_name="210 Blue Box",
                box_type="210 Blue Box", total_boxes=10, quantity=10,
            ),
        ])
        db.commit()
        assert production_mapping_issue(db, "1", product) is None
    finally:
        db.close()
        engine.dispose()


def test_cross_sheet_validation_requires_matching_blank_bottom_box_and_machine_bottom():
    issues = validate_bulk_cross_sheet({
        "finished_goods": [{
            "_row_number": 3, "product_size_ml": 210,
            "variety_design": "Blue", "packaging_size_name": "Missing Box",
        }],
        "blank_stock": [{
            "_row_number": 3, "size_ml": 210,
            "variety_design": "Blue", "linked_bottom_size_mm": 68,
        }],
        "bottom_reel": [{
            "_row_number": 19, "bottom_size_mm": 65, "variety_design": "Blue",
        }],
        "box_stock": [],
        "machine": [{"_row_number": 3, "bottom_size_mm": 70}],
    })

    assert {issue.field for issue in issues} == {
        "packaging_size_name",
        "linked_bottom_size_mm",
        "bottom_size_mm",
    }
    assert all(issue.action_type == "error" for issue in issues)

import os
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import urlparse
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import (
    Factory,
    User,
    Worker,
    WorkerOpeningAttendance,
    Machine,
    BlankStock,
    BottomStock,
    BoxStock,
    PlasticStock,
    FinishedGoodsStock,
    PackagingProfile,
    Inventory
)
from routers.onboarding import apply_bulk_rows


def reset_test_schema(engine):
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        return

    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    database_url = os.getenv("P0_ISOLATION_DATABASE_URL")
    if database_url:
        parsed = urlparse(database_url)
        database_name = parsed.path.lstrip("/").lower()
        if parsed.scheme not in {"postgresql", "postgresql+psycopg2"}:
            raise RuntimeError("P0_ISOLATION_DATABASE_URL must use PostgreSQL")
        if "test" not in database_name and "validate" not in database_name:
            raise RuntimeError("Postgres isolation tests require a database named with 'test' or 'validate'")
        engine = create_engine(database_url)
    else:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    reset_test_schema(engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    
    # Create factories
    factory_a = Factory(id=1, name="Factory A")
    factory_b = Factory(id=2, name="Factory B")
    session.add_all([factory_a, factory_b])
    session.commit()
    session.add_all(
        [
            User(
                id=10,
                factory_id=1,
                username="owner-a@test.local",
                email="owner-a@test.local",
                password_hash="test",
                role="Owner",
                is_verified=True,
            ),
            User(
                id=20,
                factory_id=2,
                username="owner-b@test.local",
                email="owner-b@test.local",
                password_hash="test",
                role="Owner",
                is_verified=True,
            ),
        ]
    )
    session.commit()
    
    try:
        yield session
    finally:
        session.close()
        reset_test_schema(engine)
        engine.dispose()

def test_cross_factory_worker_insert(db):
    user_a = SimpleNamespace(id=10, factory_id=1)
    user_b = SimpleNamespace(id=20, factory_id=2)
    
    worker_row_a = [
        {
            "row_type": "ACTUAL",
            "name": "Amit Kumar",
            "mobile_number": "9999999999",
            "daily_wages": Decimal("500"),
            "duty_hours": Decimal("8"),
            "previous_attendance_details": Decimal("3"),
        }
    ]
    
    worker_row_b = [
        {
            "row_type": "ACTUAL",
            "name": "Amit Kumar",
            "mobile_number": "8888888888",
            "daily_wages": Decimal("600"),
            "duty_hours": Decimal("9"),
            "previous_attendance_details": Decimal("5"),
        }
    ]
    
    # Apply bulk rows for factory A
    stats_a = {"inserted": 0, "updated": 0, "skipped": 0}
    count_a = apply_bulk_rows(db, user_a, "worker", worker_row_a, stats_a)
    db.commit()
    
    # Apply bulk rows for factory B
    stats_b = {"inserted": 0, "updated": 0, "skipped": 0}
    count_b = apply_bulk_rows(db, user_b, "worker", worker_row_b, stats_b)
    db.commit()
    
    # Assert counts
    assert count_a == 1
    assert stats_a["inserted"] == 1
    assert count_b == 1
    assert stats_b["inserted"] == 1
    
    # Assert database state
    all_workers = db.query(Worker).all()
    assert len(all_workers) == 2
    
    worker_a = db.query(Worker).filter(Worker.factory_id == 1).one()
    worker_b = db.query(Worker).filter(Worker.factory_id == 2).one()
    
    assert worker_a.name == "Amit Kumar"
    assert worker_a.phone == "+919999999999"
    assert worker_a.daily_wages == Decimal("500")
    
    assert worker_b.name == "Amit Kumar"
    assert worker_b.phone == "+918888888888"
    assert worker_b.daily_wages == Decimal("600")
    
    # Assert attendance is also isolated
    attendance_a = db.query(WorkerOpeningAttendance).filter(WorkerOpeningAttendance.factory_id == 1).one()
    attendance_b = db.query(WorkerOpeningAttendance).filter(WorkerOpeningAttendance.factory_id == 2).one()
    
    assert attendance_a.worker_id == worker_a.id
    assert attendance_a.present_days == Decimal("3")
    
    assert attendance_b.worker_id == worker_b.id
    assert attendance_b.present_days == Decimal("5")


def test_cross_factory_worker_update(db):
    user_a = SimpleNamespace(id=10, factory_id=1)
    user_b = SimpleNamespace(id=20, factory_id=2)
    initial_row = [
        {
            "row_type": "ACTUAL",
            "name": "Shared Worker",
            "mobile_number": "9999999999",
            "daily_wages": Decimal("500"),
            "duty_hours": Decimal("8"),
            "previous_attendance_details": Decimal("2"),
        }
    ]
    other_tenant_row = [
        {
            **initial_row[0],
            "mobile_number": "8888888888",
            "daily_wages": Decimal("700"),
            "previous_attendance_details": Decimal("4"),
        }
    ]

    apply_bulk_rows(db, user_a, "worker", initial_row)
    apply_bulk_rows(db, user_b, "worker", other_tenant_row)
    db.commit()

    updated_row = [
        {
            **initial_row[0],
            "daily_wages": Decimal("550"),
            "previous_attendance_details": Decimal("3"),
        }
    ]
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user_a, "worker", updated_row, stats)
    db.commit()

    worker_a = db.query(Worker).filter(Worker.factory_id == 1).one()
    worker_b = db.query(Worker).filter(Worker.factory_id == 2).one()
    attendance_a = db.query(WorkerOpeningAttendance).filter(
        WorkerOpeningAttendance.factory_id == 1
    ).one()
    attendance_b = db.query(WorkerOpeningAttendance).filter(
        WorkerOpeningAttendance.factory_id == 2
    ).one()

    assert stats["updated"] == 1
    assert worker_a.daily_wages == Decimal("550")
    assert attendance_a.present_days == Decimal("3")
    assert worker_b.daily_wages == Decimal("700")
    assert attendance_b.present_days == Decimal("4")


def test_cross_factory_isolation_company_profile(db):
    user_a = SimpleNamespace(id=10, factory_id=1)
    user_b = SimpleNamespace(id=20, factory_id=2)
    
    profile_row_a = [
        {
            "row_type": "ACTUAL",
            "factory_name": "Factory A Corp",
            "gstin": "07AAAAA1111A1Z1",
            "factory_address": "Address A",
            "invoice_prefix": "A-",
            "advance_upi_discount": Decimal("1.50"),
            "bill_of_supply_start_seq": 100,
            "tax_invoice_start_seq": 200,
            "bill_of_supply_simple_start_seq": 300,
        }
    ]
    
    profile_row_b = [
        {
            "row_type": "ACTUAL",
            "factory_name": "Factory B Corp",
            "gstin": "08BBBBB2222B2Z2",
            "factory_address": "Address B",
            "invoice_prefix": "B-",
            "advance_upi_discount": Decimal("2.50"),
            "bill_of_supply_start_seq": 400,
            "tax_invoice_start_seq": 500,
            "bill_of_supply_simple_start_seq": 600,
        }
    ]
    
    apply_bulk_rows(db, user_a, "company_profile", profile_row_a)
    apply_bulk_rows(db, user_b, "company_profile", profile_row_b)
    db.commit()
    
    fa = db.query(Factory).filter(Factory.id == 1).one()
    fb = db.query(Factory).filter(Factory.id == 2).one()
    
    assert fa.factory_name == "Factory A Corp"
    assert fa.gst_number == "07AAAAA1111A1Z1"
    assert fa.invoice_prefix == "A-"
    
    assert fb.factory_name == "Factory B Corp"
    assert fb.gst_number == "08BBBBB2222B2Z2"
    assert fb.invoice_prefix == "B-"


def test_cross_factory_machine(db):
    user_a = SimpleNamespace(id=10, factory_id=1)
    user_b = SimpleNamespace(id=20, factory_id=2)
    
    machine_row_a = [
        {
            "row_type": "ACTUAL",
            "machine_name": "Speedy Cup",
            "default_operating_speed": 80,
            "target_output_per_shift": 40000,
            "mould_size_ml": 150,
            "bottom_size_mm": 57,
        }
    ]
    
    machine_row_b = [
        {
            "row_type": "ACTUAL",
            "machine_name": "Speedy Cup",
            "default_operating_speed": 90,
            "target_output_per_shift": 50000,
            "mould_size_ml": 250,
            "bottom_size_mm": 70,
        }
    ]
    
    apply_bulk_rows(db, user_a, "machine", machine_row_a)
    apply_bulk_rows(db, user_b, "machine", machine_row_b)
    db.commit()
    
    m_a = db.query(Machine).filter(Machine.factory_id == 1).one()
    m_b = db.query(Machine).filter(Machine.factory_id == 2).one()
    
    assert m_a.name == "Speedy Cup"
    assert m_a.default_speed == 80
    assert m_a.mould_size_ml == 150
    
    assert m_b.name == "Speedy Cup"
    assert m_b.default_speed == 90
    assert m_b.mould_size_ml == 250


def test_cross_factory_isolation_blank_stock(db):
    user_a = SimpleNamespace(id=10, factory_id=1)
    user_b = SimpleNamespace(id=20, factory_id=2)
    
    blank_row_a = [
        {
            "row_type": "ACTUAL",
            "material_name": "Plain White",
            "size_ml": 150,
            "kg_per_sack": Decimal("25"),
        }
    ]
    
    blank_row_b = [
        {
            "row_type": "ACTUAL",
            "material_name": "Plain White",
            "size_ml": 150,
            "kg_per_sack": Decimal("30"),
        }
    ]
    
    apply_bulk_rows(db, user_a, "blank_stock", blank_row_a)
    apply_bulk_rows(db, user_b, "blank_stock", blank_row_b)
    db.commit()
    
    b_a = db.query(BlankStock).filter(BlankStock.factory_id == 1).one()
    b_b = db.query(BlankStock).filter(BlankStock.factory_id == 2).one()
    
    assert b_a.blank_size_ml == 150
    assert b_a.weight_per_bora_kg == Decimal("25")
    
    assert b_b.blank_size_ml == 150
    assert b_b.weight_per_bora_kg == Decimal("30")


def test_cross_factory_isolation_bottom_reel(db):
    user_a = SimpleNamespace(id=10, factory_id=1)
    user_b = SimpleNamespace(id=20, factory_id=2)
    
    bottom_row_a = [
        {
            "row_type": "ACTUAL",
            "bottom_size_mm": 57,
            "total_individual_rolls": 10,
            "total_weight_kg": Decimal("100"),
        }
    ]
    
    bottom_row_b = [
        {
            "row_type": "ACTUAL",
            "bottom_size_mm": 57,
            "total_individual_rolls": 12,
            "total_weight_kg": Decimal("120"),
        }
    ]
    
    apply_bulk_rows(db, user_a, "bottom_reel", bottom_row_a)
    apply_bulk_rows(db, user_b, "bottom_reel", bottom_row_b)
    db.commit()
    
    r_a = db.query(BottomStock).filter(BottomStock.factory_id == 1).one()
    r_b = db.query(BottomStock).filter(BottomStock.factory_id == 2).one()
    
    assert r_a.bottom_size_mm == 57
    assert r_a.total_rolls == 10
    assert r_a.total_weight_kg == Decimal("100")
    
    assert r_b.bottom_size_mm == 57
    assert r_b.total_rolls == 12
    assert r_b.total_weight_kg == Decimal("120")


def test_cross_factory_isolation_box_stock(db):
    user_a = SimpleNamespace(id=10, factory_id=1)
    user_b = SimpleNamespace(id=20, factory_id=2)
    
    box_row_a = [
        {
            "row_type": "ACTUAL",
            "box_type": "Standard Box",
            "box_quantity_pieces": 100,
            "price_per_box_rs": Decimal("15"),
        }
    ]
    
    box_row_b = [
        {
            "row_type": "ACTUAL",
            "box_type": "Standard Box",
            "box_quantity_pieces": 200,
            "price_per_box_rs": Decimal("18"),
        }
    ]
    
    apply_bulk_rows(db, user_a, "box_stock", box_row_a)
    apply_bulk_rows(db, user_b, "box_stock", box_row_b)
    db.commit()
    
    bx_a = db.query(BoxStock).filter(BoxStock.factory_id == 1).one()
    bx_b = db.query(BoxStock).filter(BoxStock.factory_id == 2).one()
    
    assert bx_a.packaging_size_name == "Standard Box"
    assert bx_a.quantity == 100
    assert bx_a.price_per_box == Decimal("15")
    
    assert bx_b.packaging_size_name == "Standard Box"
    assert bx_b.quantity == 200
    assert bx_b.price_per_box == Decimal("18")


def test_cross_factory_isolation_plastic_stock(db):
    user_a = SimpleNamespace(id=10, factory_id=1)
    user_b = SimpleNamespace(id=20, factory_id=2)
    
    plastic_row_a = [
        {
            "row_type": "ACTUAL",
            "plastic_size_type": "PP-100",
            "used_for_cup_size_ml": 100,
            "total_boras_sacks": 5,
            "weight_per_bora_kg": Decimal("20"),
            "price_per_kg_rs": Decimal("120"),
        }
    ]
    
    plastic_row_b = [
        {
            "row_type": "ACTUAL",
            "plastic_size_type": "PP-100",
            "used_for_cup_size_ml": 100,
            "total_boras_sacks": 8,
            "weight_per_bora_kg": Decimal("22"),
            "price_per_kg_rs": Decimal("130"),
        }
    ]
    
    apply_bulk_rows(db, user_a, "plastic_stock", plastic_row_a)
    apply_bulk_rows(db, user_b, "plastic_stock", plastic_row_b)
    db.commit()
    
    p_a = db.query(PlasticStock).filter(PlasticStock.factory_id == 1).one()
    p_b = db.query(PlasticStock).filter(PlasticStock.factory_id == 2).one()
    
    assert p_a.plastic_size_name == "PP-100"
    assert p_a.total_boras == 5
    assert p_a.price_per_kg == Decimal("120")
    
    assert p_b.plastic_size_name == "PP-100"
    assert p_b.total_boras == 8
    assert p_b.price_per_kg == Decimal("130")


def test_cross_factory_finished_goods(db):
    user_a = SimpleNamespace(id=10, factory_id=1)
    user_b = SimpleNamespace(id=20, factory_id=2)
    
    fg_row_a = [
        {
            "row_type": "ACTUAL",
            "product_size_ml": 150,
            "variety_design": "Theme A",
            "packaging_size_name": "Pack A",
            "pcs_per_packet": 50,
            "packets_per_box": 20,
            "initial_stock_boxes": 10,
        }
    ]
    
    fg_row_b = [
        {
            "row_type": "ACTUAL",
            "product_size_ml": 150,
            "variety_design": "Theme A",
            "packaging_size_name": "Pack A",
            "pcs_per_packet": 60,
            "packets_per_box": 25,
            "initial_stock_boxes": 15,
        }
    ]
    
    apply_bulk_rows(db, user_a, "finished_goods", fg_row_a)
    apply_bulk_rows(db, user_b, "finished_goods", fg_row_b)
    db.commit()
    
    fgs_a = db.query(FinishedGoodsStock).filter(FinishedGoodsStock.factory_id == 1).one()
    fgs_b = db.query(FinishedGoodsStock).filter(FinishedGoodsStock.factory_id == 2).one()
    
    assert fgs_a.cup_size_ml == 150
    assert fgs_a.boxes_available == 10
    
    assert fgs_b.cup_size_ml == 150
    assert fgs_b.boxes_available == 15


def test_same_file_reupload_idempotency_all_types(db):
    user = SimpleNamespace(id=10, factory_id=1)
    
    # 1. company_profile
    profile_rows = [{
        "row_type": "ACTUAL",
        "factory_name": "Idempotent Factory",
        "gstin": "07GSTIN1234",
        "factory_address": "Test Road",
        "invoice_prefix": "IDF-",
        "advance_upi_discount": Decimal("2.00"),
        "bill_of_supply_start_seq": 1,
        "tax_invoice_start_seq": 1,
        "bill_of_supply_simple_start_seq": 1,
    }]
    # Run 1
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "company_profile", profile_rows, stats)
    db.commit()
    assert stats["updated"] == 1
    # Run 2
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "company_profile", profile_rows, stats)
    db.commit()
    assert stats["updated"] == 1
    
    # 2. worker
    worker_rows = [{
        "row_type": "ACTUAL",
        "name": "Idempotent Worker",
        "mobile_number": "9000000000",
        "daily_wages": Decimal("350"),
        "duty_hours": Decimal("8"),
        "previous_attendance_details": Decimal("2"),
    }]
    # Run 1
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "worker", worker_rows, stats)
    db.commit()
    assert stats["inserted"] == 1
    assert db.query(Worker).filter(Worker.factory_id == 1).count() == 1
    # Run 2
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "worker", worker_rows, stats)
    db.commit()
    assert stats["updated"] == 1
    assert db.query(Worker).filter(Worker.factory_id == 1).count() == 1
    # Run 3 (Update value)
    worker_rows[0]["daily_wages"] = Decimal("380")
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "worker", worker_rows, stats)
    db.commit()
    assert stats["updated"] == 1
    assert db.query(Worker).filter(Worker.factory_id == 1).one().daily_wages == Decimal("380")
    
    # 3. machine
    machine_rows = [{
        "row_type": "ACTUAL",
        "machine_name": "Idempotent Machine",
        "default_operating_speed": 70,
        "target_output_per_shift": 30000,
        "mould_size_ml": 100,
        "bottom_size_mm": 50,
    }]
    # Run 1
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "machine", machine_rows, stats)
    db.commit()
    assert stats["inserted"] == 1
    assert db.query(Machine).filter(Machine.factory_id == 1).count() == 1
    # Run 2
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "machine", machine_rows, stats)
    db.commit()
    assert stats["updated"] == 1
    assert db.query(Machine).filter(Machine.factory_id == 1).count() == 1
    # Run 3
    machine_rows[0]["default_operating_speed"] = 75
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "machine", machine_rows, stats)
    db.commit()
    assert stats["updated"] == 1
    assert db.query(Machine).filter(Machine.factory_id == 1).one().default_speed == 75

    # 4. blank_stock
    blank_rows = [{
        "row_type": "ACTUAL",
        "material_name": "Idempotent Blank",
        "size_ml": 80,
        "kg_per_sack": Decimal("15"),
    }]
    # Run 1
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "blank_stock", blank_rows, stats)
    db.commit()
    assert stats["inserted"] == 1
    assert db.query(BlankStock).filter(BlankStock.factory_id == 1).count() == 1
    # Run 2
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "blank_stock", blank_rows, stats)
    db.commit()
    assert stats["updated"] == 1
    assert db.query(BlankStock).filter(BlankStock.factory_id == 1).count() == 1
    # Run 3
    blank_rows[0]["kg_per_sack"] = Decimal("18")
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "blank_stock", blank_rows, stats)
    db.commit()
    assert stats["updated"] == 1
    assert db.query(BlankStock).filter(BlankStock.factory_id == 1).one().weight_per_bora_kg == Decimal("18")

    # 5. bottom_reel
    bottom_rows = [{
        "row_type": "ACTUAL",
        "bottom_size_mm": 45,
        "total_individual_rolls": 5,
        "total_weight_kg": Decimal("50"),
    }]
    # Run 1
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "bottom_reel", bottom_rows, stats)
    db.commit()
    assert stats["inserted"] == 1
    assert db.query(BottomStock).filter(BottomStock.factory_id == 1).count() == 1
    # Run 2
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "bottom_reel", bottom_rows, stats)
    db.commit()
    assert stats["updated"] == 1
    assert db.query(BottomStock).filter(BottomStock.factory_id == 1).count() == 1
    # Run 3
    bottom_rows[0]["total_individual_rolls"] = 6
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "bottom_reel", bottom_rows, stats)
    db.commit()
    assert stats["updated"] == 1
    assert db.query(BottomStock).filter(BottomStock.factory_id == 1).one().total_rolls == 6

    # 6. box_stock
    box_rows = [{
        "row_type": "ACTUAL",
        "box_type": "Idempotent Box",
        "box_quantity_pieces": 50,
        "price_per_box_rs": Decimal("8"),
    }]
    # Run 1
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "box_stock", box_rows, stats)
    db.commit()
    assert stats["inserted"] == 1
    assert db.query(BoxStock).filter(BoxStock.factory_id == 1).count() == 1
    # Run 2
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "box_stock", box_rows, stats)
    db.commit()
    assert stats["updated"] == 1
    assert db.query(BoxStock).filter(BoxStock.factory_id == 1).count() == 1
    # Run 3
    box_rows[0]["box_quantity_pieces"] = 60
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "box_stock", box_rows, stats)
    db.commit()
    assert stats["updated"] == 1
    assert db.query(BoxStock).filter(BoxStock.factory_id == 1).one().quantity == 60

    # 7. plastic_stock
    plastic_rows = [{
        "row_type": "ACTUAL",
        "plastic_size_type": "PP-80",
        "used_for_cup_size_ml": 80,
        "total_boras_sacks": 3,
        "weight_per_bora_kg": Decimal("10"),
        "price_per_kg_rs": Decimal("90"),
    }]
    # Run 1
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "plastic_stock", plastic_rows, stats)
    db.commit()
    assert stats["inserted"] == 1
    assert db.query(PlasticStock).filter(PlasticStock.factory_id == 1).count() == 1
    # Run 2
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "plastic_stock", plastic_rows, stats)
    db.commit()
    assert stats["updated"] == 1
    assert db.query(PlasticStock).filter(PlasticStock.factory_id == 1).count() == 1
    # Run 3
    plastic_rows[0]["total_boras_sacks"] = 4
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "plastic_stock", plastic_rows, stats)
    db.commit()
    assert stats["updated"] == 1
    assert db.query(PlasticStock).filter(PlasticStock.factory_id == 1).one().total_boras == 4

    # 8. finished_goods
    fg_rows = [{
        "row_type": "ACTUAL",
        "product_size_ml": 80,
        "variety_design": "Design FG",
        "packaging_size_name": "Box FG",
        "pcs_per_packet": 50,
        "packets_per_box": 10,
        "initial_stock_boxes": 5,
    }]
    # Run 1
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "finished_goods", fg_rows, stats)
    db.commit()
    assert stats["inserted"] == 1
    assert db.query(FinishedGoodsStock).filter(FinishedGoodsStock.factory_id == 1).count() == 1
    assert db.query(PackagingProfile).filter(PackagingProfile.factory_id == 1).count() == 1
    # Run 2
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "finished_goods", fg_rows, stats)
    db.commit()
    assert stats["updated"] == 1
    assert db.query(FinishedGoodsStock).filter(FinishedGoodsStock.factory_id == 1).count() == 1
    assert db.query(PackagingProfile).filter(PackagingProfile.factory_id == 1).count() == 1
    # Run 3
    fg_rows[0]["initial_stock_boxes"] = 7
    stats = {"inserted": 0, "updated": 0, "skipped": 0}
    apply_bulk_rows(db, user, "finished_goods", fg_rows, stats)
    db.commit()
    assert stats["updated"] == 1
    assert db.query(FinishedGoodsStock).filter(FinishedGoodsStock.factory_id == 1).one().boxes_available == 7

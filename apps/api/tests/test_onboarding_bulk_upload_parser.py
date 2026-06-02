from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import BottomStock, Machine, Worker, WorkerOpeningAttendance
from routers.onboarding import apply_bulk_rows, validate_bulk_frame


def test_bottom_reel_bulk_rows_default_blank_weight_to_zero():
    frame = pd.DataFrame(
        [
            {
                "row_type": "ACTUAL",
                "bottom_size_mm": 65,
                "total_individual_rolls": 49,
                "total_weight_kg": None,
            }
        ]
    )

    rows, errors = validate_bulk_frame(frame, "bottom_reel", "Raw Materials", row_offset=20)

    assert errors == []
    assert rows == [
        {
            "row_type": "ACTUAL",
            "bottom_size_mm": 65,
            "total_individual_rolls": 49,
            "total_weight_kg": Decimal("0"),
        }
    ]


def test_plastic_stock_bulk_rows_expand_comma_separated_cup_sizes():
    frame = pd.DataFrame(
        [
            {
                "row_type": "ACTUAL",
                "plastic_size_type": "3.5*18",
                "used_for_cup_size_ml": "55,65",
                "total_boras_sacks": 4,
                "weight_per_bora_kg": 30,
                "price_per_kg_rs": 180,
            }
        ]
    )

    rows, errors = validate_bulk_frame(frame, "plastic_stock", "Raw Materials", row_offset=64)

    assert errors == []
    assert [row["used_for_cup_size_ml"] for row in rows] == [55, 65]
    assert {row["plastic_size_type"] for row in rows} == {"3.5*18"}


def test_worker_bulk_upload_updates_existing_worker_in_same_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        db.add(Worker(factory_id=2, name="Anjal Kumar", phone="9000000000", daily_wages=300, daily_wage_rate=300))
        db.commit()

        current_user = SimpleNamespace(id=1, factory_id=2)
        row_count = apply_bulk_rows(
            db,
            current_user,
            "worker",
            [
                {
                    "row_type": "ACTUAL",
                    "name": "Anjal Kumar",
                    "mobile_number": "8285817277",
                    "daily_wages": Decimal("400"),
                    "duty_hours": Decimal("8"),
                    "previous_attendance_details": Decimal("0"),
                }
            ],
        )
        db.commit()

        workers = db.query(Worker).filter(Worker.factory_id == 2, Worker.name == "Anjal Kumar").all()
        assert row_count == 1
        assert len(workers) == 1
        assert workers[0].phone == "+918285817277"
        assert workers[0].daily_wages == Decimal("400")
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_bottom_reel_bulk_upload_updates_existing_stock_in_same_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        db.add(
            BottomStock(
                factory_id=2,
                bottom_size_mm=65,
                variety="Plain White",
                total_rolls=10,
                total_weight_kg=Decimal("25"),
                total_qty_kg=Decimal("25"),
            )
        )
        db.commit()

        current_user = SimpleNamespace(id=1, factory_id=2)
        row_count = apply_bulk_rows(
            db,
            current_user,
            "bottom_reel",
            [
                {
                    "row_type": "ACTUAL",
                    "bottom_size_mm": 65,
                    "total_individual_rolls": 49,
                    "total_weight_kg": Decimal("0"),
                }
            ],
        )
        db.commit()

        stocks = (
            db.query(BottomStock)
            .filter(BottomStock.factory_id == 2, BottomStock.bottom_size_mm == 65, BottomStock.variety == "Plain White")
            .all()
        )
        assert row_count == 1
        assert len(stocks) == 1
        assert stocks[0].total_rolls == 49
        assert stocks[0].total_weight_kg == Decimal("0")
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_machine_bulk_upload_updates_existing_machine_in_same_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        db.add(
            Machine(
                factory_id=2,
                name="Hi-Speed Cup Machine X",
                machine_name="Hi-Speed Cup Machine X",
                machine_type="Hi-Speed Cup Machine X",
                speed_per_minute=60,
                speed_bpm=60,
                speed_cups_per_minute=60,
                default_speed=60,
                target_output_per_shift=20000,
                raw_materials_mapped=[],
                is_active=True,
            )
        )
        db.commit()

        current_user = SimpleNamespace(id=1, factory_id=2)
        row_count = apply_bulk_rows(
            db,
            current_user,
            "machine",
            [
                {
                    "row_type": "ACTUAL",
                    "machine_name": "Hi-Speed Cup Machine X",
                    "default_operating_speed": 120,
                    "target_output_per_shift": 55000,
                    "mould_size_ml": 210,
                    "bottom_size_mm": 68,
                }
            ],
        )
        db.commit()

        machines = db.query(Machine).filter(Machine.factory_id == 2, Machine.name == "Hi-Speed Cup Machine X").all()
        assert row_count == 1
        assert len(machines) == 1
        assert machines[0].default_speed == 120
        assert machines[0].target_output_per_shift == 55000
        assert machines[0].mould_size_ml == 210
        assert machines[0].bottom_size_mm == 68
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_worker_bulk_upload_updates_existing_opening_attendance():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        worker = Worker(factory_id=2, name="Anjal Kumar", phone="9000000000", daily_wages=300, daily_wage_rate=300)
        db.add(worker)
        db.flush()
        db.add(
            WorkerOpeningAttendance(
                factory_id=2,
                worker_id=worker.id,
                period_start=date.today(),
                period_end=date.today(),
                present_days=Decimal("3"),
                created_by_user_id=1,
            )
        )
        db.commit()

        current_user = SimpleNamespace(id=1, factory_id=2)
        row_count = apply_bulk_rows(
            db,
            current_user,
            "worker",
            [
                {
                    "row_type": "ACTUAL",
                    "name": "Anjal Kumar",
                    "mobile_number": "8285817277",
                    "daily_wages": Decimal("400"),
                    "duty_hours": Decimal("8"),
                    "previous_attendance_details": Decimal("7"),
                }
            ],
        )
        db.commit()

        attendance_rows = db.query(WorkerOpeningAttendance).filter(WorkerOpeningAttendance.factory_id == 2).all()
        assert row_count == 1
        assert len(attendance_rows) == 1
        assert attendance_rows[0].present_days == Decimal("7")
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

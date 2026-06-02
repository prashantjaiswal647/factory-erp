from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import Worker
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

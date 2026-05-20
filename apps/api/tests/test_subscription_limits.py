import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import Factory, Machine, User
from subscription_limits import check_machine_limit


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def seed_factory_with_machines(machine_count: int):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    factory = Factory(id=1, name="Limit Test Factory", subscription_status="trial")
    user = User(
        id=1,
        factory_id=1,
        username="owner",
        password_hash="hash",
        role="Owner",
        is_verified=True,
    )
    db.add(factory)
    db.add(user)
    db.flush()
    for index in range(machine_count):
        machine_number = f"M-{index + 1}"
        db.add(
            Machine(
                factory_id=1,
                name=machine_number,
                machine_number=machine_number,
                machine_sequence_number=machine_number,
                machine_type="Paper Cup",
                speed_per_minute=50,
                speed_bpm=50,
                speed_cups_per_minute=50,
            )
        )
    db.commit()
    return db


def test_trial_user_with_seven_machines_is_blocked_from_adding_eighth():
    db = seed_factory_with_machines(7)
    try:
        with pytest.raises(HTTPException) as exc:
            check_machine_limit(factory_id=1, db=db)

        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "UPGRADE_REQUIRED"
        assert exc.value.detail["used"] == 7
        assert exc.value.detail["limit"] == 7
    finally:
        db.close()


def test_trial_user_with_six_machines_can_add_seventh():
    db = seed_factory_with_machines(6)
    try:
        usage = check_machine_limit(factory_id=1, db=db)

        assert usage.used == 6
        assert usage.limit == 7
    finally:
        db.close()

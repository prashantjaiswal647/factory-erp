from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import AppUsageLog, Factory, FactoryInventory, Payment, SubscriptionPayment, TokenUsageLog, User
from routers.super_admin import delete_factory_cascade, validate_bulk_factory_ids


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def test_bulk_factory_ids_reject_empty_list():
    db = init_db()
    try:
        with pytest.raises(Exception):
            validate_bulk_factory_ids(db, [])
    finally:
        db.close()


def test_bulk_factory_ids_enforces_max(monkeypatch):
    db = init_db()
    try:
        monkeypatch.setenv("SUPER_ADMIN_BULK_DELETE_MAX", "1")
        db.add_all([Factory(id=1, name="One"), Factory(id=2, name="Two")])
        db.commit()
        with pytest.raises(Exception):
            validate_bulk_factory_ids(db, [1, 2])
    finally:
        db.close()


def test_delete_factory_cascade_removes_related_records():
    db = init_db()
    try:
        factory = Factory(id=11, name="Delete Me", factory_name="Delete Me")
        db.add(factory)
        db.flush()
        owner = User(
            id=21,
            user_id="delete-owner",
            factory_id=factory.id,
            username="delete@example.com",
            email="delete@example.com",
            phone_number="+919876543210",
            full_name="Delete Owner",
            password_hash="hashed",
            role="Owner",
            is_verified=True,
        )
        db.add(owner)
        db.flush()
        factory.owner_id = owner.id
        factory.owner_phone_number = owner.phone_number
        db.add_all(
            [
                FactoryInventory(factory_id=factory.id, raw_material_name="Paper", quantity=1),
                Payment(factory_id=factory.id, customer_phone="+919876543210", amount_paid=100, payment_mode="Cash", date=date.today()),
                SubscriptionPayment(factory_id=factory.id, plan_code="trial", billing_cycle="monthly", amount_paise=0, subscription_start_date=datetime.now(timezone.utc), subscription_end_date=datetime.now(timezone.utc)),
                AppUsageLog(factory_id=factory.id, user_id=owner.id, event_type="login", route_or_module="auth"),
                TokenUsageLog(factory_id=factory.id, user_id=owner.id, feature_name="ai-supervisor", total_tokens=5),
            ]
        )
        db.commit()

        delete_factory_cascade(db, factory)
        db.commit()

        assert db.query(Factory).filter(Factory.id == factory.id).count() == 0
        assert db.query(User).filter(User.factory_id == factory.id).count() == 0
        assert db.query(FactoryInventory).filter(FactoryInventory.factory_id == factory.id).count() == 0
        assert db.query(Payment).filter(Payment.factory_id == factory.id).count() == 0
        assert db.query(SubscriptionPayment).filter(SubscriptionPayment.factory_id == factory.id).count() == 0
        assert db.query(AppUsageLog).filter(AppUsageLog.factory_id == factory.id).count() == 0
        assert db.query(TokenUsageLog).filter(TokenUsageLog.factory_id == factory.id).count() == 0
    finally:
        db.close()

import pytest
from datetime import datetime, timedelta, timezone
from fastapi import BackgroundTasks
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import Factory
from auth import resolve_factory_subscription, ensure_factory_trial
from routers.billing import activate_factory_subscription
from routers.super_admin import apply_factory_subscription_update
from routers.staff import StaffCreateRequest, create_staff

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


def test_priority_1_manual_override_active():
    db = init_db()
    try:
        now = datetime.now(timezone.utc)
        future_override = now + timedelta(days=15)
        # Seed factory with active manual override
        factory = Factory(
            id=1,
            name="Override Factory",
            subscription_override=True,
            override_expires_at=future_override,
            override_plan="premium_enterprise",
            subscription_status="active",
            active_plan="basic",
            subscription_end_date=now + timedelta(days=2),  # Stale shorter standard sub
            trial_end_date=now + timedelta(days=5),          # Stale trial end
        )
        db.add(factory)
        db.commit()
        db.refresh(factory)

        res = resolve_factory_subscription(factory)
        assert res["is_manual_override"] is True
        assert res["plan_name"] == "premium_enterprise"
        assert res["subscription_status"] == "active"
        assert res["payment_status"] == "manual_override"
        assert res["access_allowed"] is True
        assert res["days_left"] == 15
        assert res["effective_plan"] == "premium_enterprise"
        assert res["effective_status"] == "active"
        assert res["effective_expires_at"] == future_override
    finally:
        db.close()


def test_priority_2_standard_active_subscription():
    db = init_db()
    try:
        now = datetime.now(timezone.utc)
        future_sub_end = now + timedelta(days=25)
        # Seed factory with active paid subscription (no manual override)
        factory = Factory(
            id=2,
            name="Paid Factory",
            subscription_override=False,
            active_plan="growth",
            plan_name="growth",
            subscription_status="active",
            payment_status="paid",
            subscription_end_date=future_sub_end,
            trial_end_date=now + timedelta(days=5),  # Do not prefer trial_end_date
        )
        db.add(factory)
        db.commit()
        db.refresh(factory)

        res = resolve_factory_subscription(factory)
        assert res["is_manual_override"] is False
        assert res["plan_name"] == "growth"
        assert res["subscription_status"] == "active"
        assert res["payment_status"] == "paid"
        assert res["access_allowed"] is True
        assert res["days_left"] == 25
        assert res["effective_plan"] == "growth"
        assert res["effective_status"] == "active"
        assert res["effective_expires_at"] == future_sub_end
        # Ensure raw debug fields are populated
        assert res["raw_active_plan"] == "growth"
        assert res["raw_subscription_end_date"] == future_sub_end
    finally:
        db.close()


def test_priority_3_basic_trial_active():
    db = init_db()
    try:
        now = datetime.now(timezone.utc)
        future_trial_end = now + timedelta(days=6)
        # Seed factory in basic trial state
        factory = Factory(
            id=3,
            name="Trial Factory",
            subscription_override=False,
            active_plan="basic",
            subscription_status="trial_active",
            payment_status="payment_pending",
            trial_end_date=future_trial_end,
        )
        db.add(factory)
        db.commit()
        db.refresh(factory)

        res = resolve_factory_subscription(factory)
        assert res["is_manual_override"] is False
        assert res["plan_name"] == "basic"
        assert res["subscription_status"] == "trial_active"
        assert res["payment_status"] == "payment_pending"
        assert res["access_allowed"] is True
        assert res["days_left"] == 6
        assert res["effective_plan"] == "basic"
        assert res["effective_status"] == "trial_active"
        assert res["effective_expires_at"] == future_trial_end
    finally:
        db.close()


def test_days_left_ceiling_rounding():
    db = init_db()
    try:
        now = datetime.now(timezone.utc)
        # Exactly 1.1 days (95040 seconds) -> should round up to 2 days left
        future_sub_end = now + timedelta(seconds=95040)
        factory = Factory(
            id=4,
            name="Ceiling Rounding Factory",
            subscription_status="active",
            active_plan="premium",
            payment_status="paid",
            subscription_end_date=future_sub_end,
        )
        db.add(factory)
        db.commit()
        db.refresh(factory)

        res = resolve_factory_subscription(factory)
        assert res["days_left"] == 2
    finally:
        db.close()


def test_adminer_manual_premium_active_plan_wins_over_trial():
    db = init_db()
    try:
        now = datetime.now(timezone.utc)
        future_sub_end = now + timedelta(days=365)
        factory = Factory(
            id=5,
            name="Adminer Premium Factory",
            active_plan="premium",
            plan_name="premium",
            subscription_status="active",
            payment_status="paid",
            subscription_end_date=future_sub_end,
            plan_expires_at=future_sub_end,
            trial_end_date=now + timedelta(days=1),
        )
        db.add(factory)
        db.commit()
        db.refresh(factory)

        res = resolve_factory_subscription(factory)
        assert res["access_allowed"] is True
        assert res["effective_plan"] == "premium"
        assert res["effective_status"] == "active"
        assert res["effective_expires_at"] == future_sub_end
        assert res["days_left"] == 365
    finally:
        db.close()


def test_super_admin_partial_update_synchronizes_canonical_subscription_fields():
    db = init_db()
    try:
        now = datetime.now(timezone.utc)
        old_expiry = now + timedelta(hours=1)
        new_expiry = now + timedelta(days=30)
        factory = Factory(
            id=51,
            name="Admin Sync Factory",
            active_plan="basic",
            plan_name="basic",
            subscription_status="active",
            payment_status="paid",
            subscription_end_date=old_expiry,
            subscription_end=old_expiry,
            plan_expires_at=old_expiry,
        )
        db.add(factory)
        db.commit()

        apply_factory_subscription_update(
            factory,
            {
                "plan_name": "premium",
                "billing_cycle": "monthly",
                "subscription_end_date": new_expiry,
            },
        )
        db.commit()
        db.refresh(factory)

        assert factory.active_plan == "premium"
        assert factory.plan_name == "premium"
        assert factory.subscription_end_date.replace(tzinfo=timezone.utc) == new_expiry
        assert factory.subscription_end.replace(tzinfo=timezone.utc) == new_expiry
        assert factory.plan_expires_at.replace(tzinfo=timezone.utc) == new_expiry

        resolved = resolve_factory_subscription(factory)
        assert resolved["effective_plan"] == "premium"
        assert resolved["effective_status"] == "active"
        assert resolved["effective_expires_at"] == new_expiry
        assert resolved["days_left"] == 30
    finally:
        db.close()


def test_trial_active_future_trial_end_allows_access():
    db = init_db()
    try:
        now = datetime.now(timezone.utc)
        future_trial_end = now + timedelta(days=1)
        factory = Factory(
            id=6,
            name="Future Trial Factory",
            active_plan="basic",
            subscription_status="trial_active",
            payment_status="payment_pending",
            trial_end_date=future_trial_end,
        )
        db.add(factory)
        db.commit()
        db.refresh(factory)

        res = resolve_factory_subscription(factory)
        assert res["access_allowed"] is True
        assert res["effective_status"] == "trial_active"
        assert res["days_left"] == 1
    finally:
        db.close()


def test_expired_trial_without_paid_plan_blocks_access():
    db = init_db()
    try:
        now = datetime.now(timezone.utc)
        factory = Factory(
            id=7,
            name="Expired Trial Factory",
            active_plan="basic",
            subscription_status="trial_active",
            payment_status="payment_pending",
            trial_end_date=now - timedelta(days=1),
        )
        db.add(factory)
        db.commit()
        db.refresh(factory)

        res = resolve_factory_subscription(factory)
        assert res["access_allowed"] is False
        assert res["effective_status"] == "payment_pending"
        assert res["days_left"] == 0
    finally:
        db.close()


def test_adminer_active_future_plan_expires_allows_without_restart():
    db = init_db()
    try:
        now = datetime.now(timezone.utc)
        future_expiry = now + timedelta(days=365)
        factory = Factory(
            id=8,
            name="Adminer Future Plan Factory",
            active_plan="premium",
            plan_name="premium",
            subscription_status="active",
            payment_status="paid",
            plan_expires_at=future_expiry,
            trial_end_date=now - timedelta(days=1),
        )
        db.add(factory)
        db.commit()
        db.refresh(factory)

        res = resolve_factory_subscription(factory)
        assert res["access_allowed"] is True
        assert res["effective_plan"] == "premium"
        assert res["plan_expires_at"] == future_expiry
        assert res["days_left"] == 365
    finally:
        db.close()


def test_adminer_expired_status_blocks_even_with_stale_future_expiry():
    db = init_db()
    try:
        now = datetime.now(timezone.utc)
        future_expiry = now + timedelta(days=365)
        factory = Factory(
            id=9,
            name="Adminer Expired Factory",
            active_plan="premium",
            plan_name="premium",
            subscription_status="expired",
            payment_status="paid",
            subscription_end_date=future_expiry,
            plan_expires_at=future_expiry,
        )
        db.add(factory)
        db.commit()
        db.refresh(factory)

        res = resolve_factory_subscription(factory)
        assert res["access_allowed"] is False
        assert res["effective_status"] == "expired"
    finally:
        db.close()


def test_subscription_purchase_stacks_after_current_active_expiry():
    db = init_db()
    try:
        now = datetime.now(timezone.utc)
        current_end = now + timedelta(days=12)
        factory = Factory(
            id=10,
            name="Stacked Subscription Factory",
            active_plan="basic",
            plan_name="basic",
            subscription_status="active",
            payment_status="paid",
            subscription_start_date=now - timedelta(days=18),
            subscription_end_date=current_end,
            subscription_start=now - timedelta(days=18),
            subscription_end=current_end,
            plan_expires_at=current_end,
        )
        db.add(factory)
        db.commit()
        db.refresh(factory)

        activate_factory_subscription(db, factory, "premium", "monthly", "pay_stacked")

        payment = factory.subscription_end_date
        assert factory.subscription_start == current_end
        assert payment == current_end + timedelta(days=30)
        assert factory.subscription_end == payment
        assert factory.plan_expires_at == payment
    finally:
        db.close()


def test_staff_create_forces_creator_factory_id():
    db = init_db()
    try:
        factory = Factory(id=21, name="Tenant Boundary Factory")
        db.add(factory)
        db.commit()
        owner = type(
            "Owner",
            (),
            {"id": 1, "username": "owner21", "full_name": "Owner Twenty One", "role": "Owner", "factory_id": 21},
        )()
        payload = StaffCreateRequest(
            full_name="Tenant Worker",
            phone_number="9999990021",
            password="secret123",
            role="worker",
        )
        bg_tasks = BackgroundTasks()

        staff = create_staff(payload=payload, background_tasks=bg_tasks, current_user=owner, db=db)

        assert staff.factory_id == owner.factory_id
        assert staff.role == "Operator"
    finally:
        db.close()

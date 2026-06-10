import pytest
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base, get_db
from main import app as main_app
from models import (
    Factory,
    User,
    Customer,
    OutstandingBill,
)
from auth import get_current_user


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


mock_user = SimpleNamespace(
    id=1,
    factory_id=1,
    username="owner@test.com",
    email="owner@test.com",
    role="Owner",
    full_name="Owner Admin"
)


def override_get_current_user():
    return mock_user


def ensure_testclient_compatibility():
    import inspect
    import httpx
    if "app" in inspect.signature(httpx.Client.__init__).parameters:
        return
    original_init = httpx.Client.__init__
    if getattr(original_init, "_munshi_accepts_app_kwarg", False):
        return
    def patched_init(self, *args, app=None, **kwargs):
        return original_init(self, *args, **kwargs)
    patched_init._munshi_accepts_app_kwarg = True
    httpx.Client.__init__ = patched_init


@pytest.fixture(autouse=True)
def setup_db_and_overrides():
    ensure_testclient_compatibility()
    main_app.dependency_overrides[get_db] = override_get_db
    main_app.dependency_overrides[get_current_user] = override_get_current_user

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        # Seed Factory
        db.add(Factory(id=1, name="Factory One", subscription_status="active"))
        # Seed User
        db.add(User(id=1, factory_id=1, username="owner@test.com", role="Owner", is_verified=True, password_hash="some-hash"))
        
        # Seed Customers
        c1 = Customer(id=1, factory_id=1, name="ABC Traders")
        c2 = Customer(id=2, factory_id=1, name="XYZ Packaging")
        db.add_all([c1, c2])
        db.flush()

        # Seed Outstanding Bills
        today = date.today()
        # Bill 1: 5 Days old, ₹50,000 (0-7 Days bucket, not overdue)
        db.add(OutstandingBill(
            factory_id=1,
            customer_id=1,
            tracking_number="INV-001",
            bill_date=today - timedelta(days=5),
            bill_amount=Decimal("50000.00"),
            balance_amount=Decimal("50000.00"),
            status="active"
        ))
        # Bill 2: 35 Days old, ₹3,20,000 (31-60 Days bucket, overdue)
        db.add(OutstandingBill(
            factory_id=1,
            customer_id=1,
            tracking_number="INV-002",
            bill_date=today - timedelta(days=35),
            bill_amount=Decimal("320000.00"),
            balance_amount=Decimal("320000.00"),
            status="active"
        ))
        # Bill 3: 11 Days old, ₹2,40,000 (8-15 Days bucket, not overdue as <= 15 days credit term)
        db.add(OutstandingBill(
            factory_id=1,
            customer_id=2,
            tracking_number="INV-003",
            bill_date=today - timedelta(days=11),
            bill_amount=Decimal("240000.00"),
            balance_amount=Decimal("240000.00"),
            status="active"
        ))
        db.commit()
    finally:
        db.close()

    yield

    main_app.dependency_overrides.pop(get_db, None)
    main_app.dependency_overrides.pop(get_current_user, None)


def test_collection_war_room_calculations():
    client = TestClient(main_app)
    response = client.get("/api/dashboard/collection-war-room")
    assert response.status_code == 200
    data = response.json()
    
    assert data["total_outstanding"] == 610000.0
    assert data["overdue_amount"] == 320000.0
    assert len(data["top_customers"]) == 2
    
    # Check Buckets
    buckets = data["aging_buckets"]
    assert buckets["0_7_days"] == 50000.0
    assert buckets["8_15_days"] == 240000.0
    assert buckets["31_60_days"] == 320000.0
    
    # Check High Risk Customers count (oldest bill > 30 days)
    assert data["high_risk_customers"] == 1


def test_collection_war_room_telegram_alert():
    client = TestClient(main_app)
    with patch("services.telegram_delivery.send_role_briefing", return_value=1) as mock_sender:
        response = client.post("/api/dashboard/collection-war-room/telegram-alert")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        mock_sender.assert_called_once()
        assert "Collection War Room" in mock_sender.call_args[0][3]


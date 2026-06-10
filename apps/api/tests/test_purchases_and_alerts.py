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
    Supplier,
    PurchaseEntry,
    PurchaseRateHistory,
    BlankStock,
    BottomStock,
    BoxStock,
    PlasticStock,
    PolybagStock,
    DailyProduction,
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
        # Seed Factories
        db.add(Factory(id=1, name="Factory One", subscription_status="active"))
        db.add(Factory(id=2, name="Factory Two", subscription_status="active"))
        db.flush()

        # Seed Users
        db.add(User(id=1, factory_id=1, username="owner@test.com", role="Owner", is_verified=True, password_hash="some-hash"))
        db.add(User(id=2, factory_id=2, username="owner2@test.com", role="Owner", is_verified=True, password_hash="some-hash"))
        db.commit()
    finally:
        db.close()

    yield

    main_app.dependency_overrides.pop(get_db, None)
    main_app.dependency_overrides.pop(get_current_user, None)


def test_supplier_creation():
    client = TestClient(main_app)
    # Create supplier
    payload = {
        "name": "Supplier A",
        "phone": "9876543210",
        "address": "123 Industrial Area",
        "gst_number": "07ABCDE1234F1Z5"
    }
    response = client.post("/api/purchases/suppliers", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Supplier A"
    assert float(data["outstanding_amount"]) == 0.0

    # Test duplicate name rejection
    response = client.post("/api/purchases/suppliers", json=payload)
    assert response.status_code == 400


def test_purchase_creation_increases_stock_and_creates_outstanding():
    client = TestClient(main_app)
    db = TestingSessionLocal()
    try:
        supplier = Supplier(factory_id=1, name="Supplier B", outstanding_amount=Decimal("0.00"))
        db.add(supplier)
        db.commit()
        supplier_id = supplier.id
    finally:
        db.close()

    # Create Purchase Entry for Blank (Received status)
    payload = {
        "supplier_id": supplier_id,
        "item_category": "Blank",
        "product_size_ml": 250,
        "variety_design": "Plain White",
        "quantity": 500.0,
        "rate": 1.5,
        "bill_number": "BILL-001",
        "received_status": "Received"
    }
    response = client.post("/api/purchases/entries", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert float(data["total_amount"]) == 750.0

    # Assert stock increased
    db = TestingSessionLocal()
    try:
        blank_stock = db.query(BlankStock).filter(
            BlankStock.factory_id == 1,
            BlankStock.blank_size_ml == 250,
            BlankStock.variety == "Plain White"
        ).first()
        assert blank_stock is not None
        assert float(blank_stock.total_qty_kg) == 500.0

        # Assert supplier outstanding created
        supp = db.query(Supplier).filter(Supplier.id == supplier_id).first()
        assert float(supp.outstanding_amount) == 750.0
    finally:
        db.close()


def test_low_stock_alerts():
    client = TestClient(main_app)
    db = TestingSessionLocal()
    try:
        # Seed a small amount of BlankStock
        db.add(BlankStock(factory_id=1, blank_size_ml=250, variety="Plain White", linked_bottom_size_mm=52, total_qty_kg=Decimal("10.00")))
        # Seed daily production usage to compute high average consumption (e.g. 50kg/day in past 30 days)
        db.add(DailyProduction(
            factory_id=1,
            date=date.today() - timedelta(days=1),
            machine_id=1,
            product_size_ml=250,
            variety="Plain White",
            packaging_size_name="Standard",
            packets_per_box_limit=100,
            blank_used_kg=Decimal("300.00"),
            bottom_used_kg=Decimal("300.00")
        ))
        db.commit()
    finally:
        db.close()

    with patch("services.telegram_delivery.send_role_briefing", return_value=1):
        response = client.get("/api/purchases/alerts")
        assert response.status_code == 200
        data = response.json()
        alert_types = [a["type"] for a in data["alerts"]]
        assert "blank_low_stock" in alert_types or "bottom_low_stock" in alert_types


def test_purchase_factory_isolation():
    client = TestClient(main_app)
    db = TestingSessionLocal()
    try:
        # Create supplier for Factory 1
        s1 = Supplier(factory_id=1, name="Supplier F1")
        # Create supplier for Factory 2
        s2 = Supplier(factory_id=2, name="Supplier F2")
        db.add_all([s1, s2])
        db.commit()
        s1_id = s1.id
        s2_id = s2.id
    finally:
        db.close()

    # Try to list suppliers under Factory 1 context
    global mock_user
    mock_user.factory_id = 1
    response = client.get("/api/purchases/suppliers")
    assert response.status_code == 200
    names = [s["name"] for s in response.json()]
    assert "Supplier F1" in names
    assert "Supplier F2" not in names

    # Try to create purchase for Factory 2 supplier from Factory 1 context -> Should reject (404)
    payload = {
        "supplier_id": s2_id,
        "item_category": "Blank",
        "product_size_ml": 250,
        "variety_design": "Plain White",
        "quantity": 100.0,
        "rate": 2.0,
        "received_status": "Pending"
    }
    response = client.post("/api/purchases/entries", json=payload)
    assert response.status_code == 404

import pytest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base, get_db
from models import (
    Factory, User, Worker, Machine, CostingMaster, Customer, 
    BlankStock, BottomStock, BoxStock, FinalProductStock, 
    DailyProduction, DailySale, SalesInvoice, InvoiceDocument, OutstandingBill, Payment, PaymentCollection
)
from auth import get_current_user, get_current_active_user, require_owner
from main import app as main_app


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


# Create test engine
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


mock_user = SimpleNamespace(id=1, factory_id=1, username="owner@test.com", email="owner@test.com", role="Owner", full_name="Owner Admin")


def override_get_current_user():
    global mock_user
    return mock_user


@pytest.fixture(autouse=True)
def setup_db_and_overrides():
    # Setup dependency overrides on main_app
    main_app.dependency_overrides[get_db] = override_get_db
    main_app.dependency_overrides[get_current_user] = override_get_current_user
    main_app.dependency_overrides[get_current_active_user] = override_get_current_user
    main_app.dependency_overrides[require_owner] = override_get_current_user

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    try:
        # Seed Factory
        factory = Factory(id=1, name="E2E Test Factory", subscription_status="active", active_plan="growth")
        db.add(factory)
        db.flush()

        # Seed User
        owner_user = User(
            id=1,
            factory_id=1,
            username="owner@test.com",
            email="owner@test.com",
            role="Owner",
            full_name="Owner Admin",
            password_hash="mock_secure_hash",
            is_verified=True,
        )
        db.add(owner_user)

        # Seed Costing Master
        costing = CostingMaster(
            factory_id=1,
            paper_price_per_kg=Decimal("80.00"),
            bottom_roll_price_per_kg=Decimal("90.00"),
            labour_cost_per_box=Decimal("10.00"),
            electricity_cost_per_box=Decimal("5.00"),
        )
        db.add(costing)

        # Seed Machine
        machine = Machine(
            id=1,
            factory_id=1,
            name="Machine 1",
            machine_type="Cup Machine",
            mould_size_ml=250,
            cup_size_ml=250,
            bottom_size_mm=52,
            is_active=True,
        )
        db.add(machine)

        # Seed Worker
        worker = Worker(
            id=1,
            factory_id=1,
            name="Worker 1",
            daily_wages=Decimal("1000.00"),
            daily_wage_rate=Decimal("1000.00"),
            is_active=True,
        )
        db.add(worker)

        # Seed Customer
        customer = Customer(
            id=1,
            factory_id=1,
            name="Customer 1",
            phone_number="9876543210",
            previous_due=Decimal("0.00"),
            total_due=Decimal("0.00"),
            balance_amount=Decimal("0.00"),
            pending_dues=0.0,
            pending_balance=Decimal("0.00"),
        )
        db.add(customer)

        # Seed Inventory
        blank_stock = BlankStock(
            factory_id=1,
            blank_size_ml=250,
            variety="Standard/White",
            linked_bottom_size_mm=52,
            weight_per_bora_kg=Decimal("20.000"),
            total_boras=Decimal("5.000"),
            total_qty_kg=Decimal("100.000"),
        )
        bottom_stock = BottomStock(
            factory_id=1,
            bottom_size_mm=52,
            variety="Standard/White",
            bag_weight_kg=Decimal("25.000"),
            rolls_per_bag=5,
            total_bags=2,
            total_rolls=10,
            total_weight_kg=Decimal("50.000"),
            total_qty_kg=Decimal("50.000"),
        )
        box_stock = BoxStock(
            factory_id=1,
            packaging_size_name="Box-1",
            total_boxes=100,
            quantity=100,
            price_per_box=2.5,
        )
        final_stock = FinalProductStock(
            id=1,
            factory_id=1,
            product_size_ml=250,
            variety="Standard/White",
            packaging_size_name="Box-1",
            pieces_per_packet=100,
            current_quantity=5,
            total_boxes=5,
            loose_packets=0,
            packets_per_box_limit=10,
        )
        db.add_all([blank_stock, bottom_stock, box_stock, final_stock])
        db.commit()
    finally:
        db.close()

    yield

    for dep in [get_db, get_current_user, get_current_active_user, require_owner]:
        main_app.dependency_overrides.pop(dep, None)


@pytest.fixture(autouse=True)
def mock_n8n_sync():
    with patch("routers.operations.sync_data_to_n8n_bg") as mock_ops, \
         patch("routers.sales.sync_data_to_n8n_bg") as mock_sales:
        yield (mock_ops, mock_sales)


def test_e2e_erp_workflow(mock_n8n_sync):
    ensure_testclient_compatibility()
    client = TestClient(main_app)

    # ----------------------------------------------------
    # 1. Validate Initial Stocks
    # ----------------------------------------------------
    db = TestingSessionLocal()
    try:
        b_stock = db.query(BlankStock).filter_by(factory_id=1, blank_size_ml=250).first()
        assert b_stock.total_qty_kg == Decimal("100.0")
        assert b_stock.total_boras == Decimal("5.0")

        bot_stock = db.query(BottomStock).filter_by(factory_id=1, bottom_size_mm=52).first()
        assert bot_stock.total_qty_kg == Decimal("50.0")
        assert bot_stock.total_rolls == 10

        box_stock = db.query(BoxStock).filter_by(factory_id=1, packaging_size_name="Box-1").first()
        assert box_stock.total_boxes == 100

        fp_stock = db.query(FinalProductStock).filter_by(factory_id=1, id=1).first()
        assert fp_stock.current_quantity == 5
    finally:
        db.close()

    # ----------------------------------------------------
    # 2. Production Entry (Stock Calculation Validation)
    # ----------------------------------------------------
    production_payload = {
        "date": "2026-06-03",
        "worker_id": 1,
        "machine_id": 1,
        "product_id": 1,
        "product_size_ml": 250,
        "variety": "Standard/White",
        "packaging_size_name": "Box-1",
        "pieces_per_packet": 100,
        "packets_per_box_limit": 10,
        "shift": "Day",
        "total_boxes_made": 10,
        "loose_packets_made": 0,
        "blank_used_bori": 1.0,
        "bottom_used_rolls": 2,
        "blank_used_kg": 20.0,
        "bottom_used_kg": 10.0,
        "wastage_kg": 0.5,
        "remarks": "E2E Production Run"
    }

    prod_res = client.post("/api/production/daily", json=production_payload)
    if prod_res.status_code != 201:
        print("ERROR RESPONSE:", prod_res.status_code, prod_res.text)
    assert prod_res.status_code == 201
    prod_data = prod_res.json()
    assert prod_data["total_boxes_after"] == 15

    # Validate stock deductions & additions after production
    db = TestingSessionLocal()
    try:
        b_stock = db.query(BlankStock).filter_by(factory_id=1, blank_size_ml=250).first()
        # Initial 100.0 - 20.0 used = 80.0
        assert b_stock.total_qty_kg == Decimal("80.0")
        assert b_stock.total_boras == Decimal("4.0")

        bot_stock = db.query(BottomStock).filter_by(factory_id=1, bottom_size_mm=52).first()
        # Initial 50.0 - 10.0 used = 40.0
        assert bot_stock.total_qty_kg == Decimal("40.0")
        assert bot_stock.total_rolls == 8

        box_stock = db.query(BoxStock).filter_by(factory_id=1, packaging_size_name="Box-1").first()
        # Initial 100 - 10 used = 90
        assert box_stock.total_boxes == 90

        fp_stock = db.query(FinalProductStock).filter_by(factory_id=1, id=1).first()
        # Initial 5 + 10 produced = 15
        assert fp_stock.current_quantity == 15
    finally:
        db.close()

    # ----------------------------------------------------
    # 3. Sale & Invoice & Outstanding Creation
    # ----------------------------------------------------
    sale_payload = {
        "date": "2026-06-03",
        "customer_id": 1,
        "amount_paid": 200.0,
        "legal_invoice_type": "bill_of_supply",
        "items": [
            {
                "product_id": 1,
                "product_size_ml": 250,
                "variety": "Standard/White",
                "packaging_size_name": "Box-1",
                "boxes_sold": 8,
                "loose_packets_sold": 0,
                "rate_per_box": 100.0,
                "rate_per_packet": 10.0,
                "packets_per_box": 10
            }
        ]
    }

    sale_res = client.post("/api/sales/invoice", json=sale_payload)
    assert sale_res.status_code == 201
    sale_data = sale_res.json()
    # 8 boxes * 100.0 = 800.0 total bill
    assert Decimal(str(sale_data["bill_total"])) == Decimal("800.00")
    assert Decimal(str(sale_data["amount_paid"])) == Decimal("200.00")
    assert Decimal(str(sale_data["customer_total_due"])) == Decimal("600.00")

    # Validate stocks and customer/bill entities
    db = TestingSessionLocal()
    try:
        # Final stock should decrease: 15 - 8 = 7
        fp_stock = db.query(FinalProductStock).filter_by(factory_id=1, id=1).first()
        assert fp_stock.current_quantity == 7

        # Customer balance should be 600
        customer = db.query(Customer).filter_by(id=1).first()
        assert customer.total_due == Decimal("600.0")
        assert customer.balance_amount == Decimal("600.0")

        # Outstanding bill should be created
        bill = db.query(OutstandingBill).filter_by(customer_id=1, factory_id=1).first()
        assert bill is not None
        assert bill.bill_amount == Decimal("800.0")
        assert bill.amount_paid == Decimal("200.0")
        assert bill.balance_amount == Decimal("600.0")
        assert bill.status == "partial"
    finally:
        db.close()

    # ----------------------------------------------------
    # 4. Payment Adjustment
    # ----------------------------------------------------
    payment_payload = {
        "customer_id": 1,
        "amount_paid": 400.0,
        "payment_mode": "Cash",
        "date": "2026-06-03"
    }

    pay_res = client.post("/api/payments/add", json=payment_payload)
    assert pay_res.status_code == 201
    pay_data = pay_res.json()
    # Remaining customer due should now be 200
    assert Decimal(str(pay_data["total_remaining_balance"])) == Decimal("200.00")

    db = TestingSessionLocal()
    try:
        customer = db.query(Customer).filter_by(id=1).first()
        assert customer.total_due == Decimal("200.0")
        assert customer.balance_amount == Decimal("200.0")

        bill = db.query(OutstandingBill).filter_by(customer_id=1, factory_id=1).first()
        assert bill.amount_paid == Decimal("600.0")  # 200 original + 400 new
        assert bill.balance_amount == Decimal("200.0")
        assert bill.status == "partial"
    finally:
        db.close()

    # ----------------------------------------------------
    # 5. Overpaying Edge Case
    # ----------------------------------------------------
    overpay_payload = {
        "customer_id": 1,
        "amount_paid": 300.0,  # exceeds outstanding 200
        "payment_mode": "UPI",
        "date": "2026-06-03",
        "save_extra_as_advance": False
    }
    overpay_res = client.post("/api/payments/add", json=overpay_payload)
    assert overpay_res.status_code == 400
    assert "exceeds outstanding balance" in overpay_res.json()["detail"]

    # ----------------------------------------------------
    # 6. Deletion/Reversal Edge Cases
    # ----------------------------------------------------
    
    # Case A: Clear Outstanding Bill with reason="mistake" (Reversal)
    db = TestingSessionLocal()
    try:
        bill = db.query(OutstandingBill).filter_by(customer_id=1, factory_id=1).first()
        bill_id = bill.id
    finally:
        db.close()

    # Delete outstanding bill (mistake)
    del_res = client.delete(f"/api/sales/outstanding/{bill_id}", params={"reason": "mistake", "confirm": True})
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    db = TestingSessionLocal()
    try:
        # Check outstanding bill is deleted
        assert db.query(OutstandingBill).filter_by(id=bill_id).count() == 0
        # Check associated daily sales are deleted
        assert db.query(DailySale).filter_by(customer_id=1).count() == 0
        # Check invoice document is deleted
        assert db.query(InvoiceDocument).filter_by(customer_id=1).count() == 0
        
        # Check that stock is restored: 7 + 8 sold = 15 boxes
        fp_stock = db.query(FinalProductStock).filter_by(factory_id=1, id=1).first()
        assert fp_stock.current_quantity == 15

        # Check customer balance reset to 0
        customer = db.query(Customer).filter_by(id=1).first()
        assert customer.total_due == Decimal("0.00")
        assert customer.balance_amount == Decimal("0.00")
    finally:
        db.close()

    # Case B: Delete Production Log
    db = TestingSessionLocal()
    try:
        prod = db.query(DailyProduction).filter_by(factory_id=1).first()
        prod_id = prod.id
    finally:
        db.close()

    del_prod_res = client.delete(f"/api/production/daily/{prod_id}")
    assert del_prod_res.status_code == 204

    db = TestingSessionLocal()
    try:
        # Check production log is deleted
        assert db.query(DailyProduction).filter_by(id=prod_id).count() == 0
        # Check that final product stock drops to onboarding level (5)
        fp_stock = db.query(FinalProductStock).filter_by(factory_id=1, id=1).first()
        assert fp_stock.current_quantity == 5
    finally:
        db.close()

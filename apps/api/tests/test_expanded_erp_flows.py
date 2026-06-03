import pytest
import os
os.environ["JWT_SECRET_KEY"] = "test_secret_key_12345678901234567890"

from datetime import date, datetime, timedelta, timezone
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
    DailyProduction, DailySale, SalesInvoice, InvoiceDocument, OutstandingBill, Payment, 
    PaymentCollection, WorkerOpeningAttendance, AttendanceLog, AdvancePayment, HisabSettlement,
    ActivityLog,
)
from auth import (
    get_current_user, get_current_active_user, require_owner,
    create_access_token, get_jwt_secret_key
)
from routers.onboarding import apply_bulk_rows
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


# SQLite engine for tests
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


@pytest.fixture(autouse=True)
def clean_db():
    main_app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    main_app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def mock_n8n_sync():
    with patch("routers.operations.sync_data_to_n8n_bg") as mock_ops, \
         patch("routers.sales.sync_data_to_n8n_bg") as mock_sales:
        yield (mock_ops, mock_sales)


# Helper to get mock active user
def get_mock_owner_user(factory_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=factory_id * 10,
        factory_id=factory_id,
        username=f"owner_{factory_id}@test.com",
        email=f"owner_{factory_id}@test.com",
        role="Owner",
        full_name=f"Owner of Factory {factory_id}",
    )


# ---------------------------------------------------------------------------
# Priority 1: Factory Isolation Tests
# ---------------------------------------------------------------------------
def test_factory_isolation_flow(monkeypatch):
    # Setup two mock users
    user_f1 = get_mock_owner_user(1)
    user_f2 = get_mock_owner_user(2)

    # Local overrides to swap active user
    current_active_user = user_f1

    def local_get_active_user():
        return current_active_user

    # Temporarily override authentication dependencies to simulate active session
    main_app.dependency_overrides[get_current_user] = local_get_active_user
    main_app.dependency_overrides[get_current_active_user] = local_get_active_user
    main_app.dependency_overrides[require_owner] = local_get_active_user

    ensure_testclient_compatibility()
    client = TestClient(main_app)

    db = TestingSessionLocal()
    try:
        # Seed both factories
        db.add(Factory(id=1, name="Factory 1", subscription_status="active", active_plan="growth"))
        db.add(Factory(id=2, name="Factory 2", subscription_status="active", active_plan="growth"))

        # Seed users in DB (to prevent foreign key issues and allow real checks)
        db.add(User(id=user_f1.id, factory_id=1, username=user_f1.username, email=user_f1.email, role="Owner", full_name=user_f1.full_name, password_hash="hash", is_verified=True))
        db.add(User(id=user_f2.id, factory_id=2, username=user_f2.username, email=user_f2.email, role="Owner", full_name=user_f2.full_name, password_hash="hash", is_verified=True))

        # Seed stocks for Factory 1 only
        db.add(FinalProductStock(id=10, factory_id=1, product_size_ml=250, variety="Standard/White", packaging_size_name="Box-1", total_boxes=10, current_quantity=10, packets_per_box_limit=10))
        # Seed stocks for Factory 2 only
        db.add(FinalProductStock(id=20, factory_id=2, product_size_ml=250, variety="Standard/White", packaging_size_name="Box-1", total_boxes=5, current_quantity=5, packets_per_box_limit=10))
        
        # Seed Machine for Factory 1 and 2
        db.add(Machine(id=1, factory_id=1, name="M1", mould_size_ml=250, cup_size_ml=250, bottom_size_mm=52))
        db.add(Machine(id=2, factory_id=2, name="M2", mould_size_ml=250, cup_size_ml=250, bottom_size_mm=52))

        # Seed Worker for Factory 1 and 2
        db.add(Worker(id=1, factory_id=1, name="W1", daily_wages=Decimal("1000")))
        db.add(Worker(id=2, factory_id=2, name="W2", daily_wages=Decimal("1000")))

        # Seed Customer for Factory 1 and 2
        db.add(Customer(id=1, factory_id=1, name="Cust 1", phone_number="9876543210"))
        db.add(Customer(id=2, factory_id=2, name="Cust 2", phone_number="9876543211"))

        db.commit()
    finally:
        db.close()

    # 1. Check final stock query isolation
    # F1 query
    current_active_user = user_f1
    res_f1 = client.get("/api/inventory/final-stock")
    assert res_f1.status_code == 200
    f1_stocks = res_f1.json()
    assert len(f1_stocks) == 1
    assert f1_stocks[0]["current_quantity"] == 10

    # F2 query
    current_active_user = user_f2
    res_f2 = client.get("/api/inventory/final-stock")
    assert res_f2.status_code == 200
    f2_stocks = res_f2.json()
    assert len(f2_stocks) == 1
    assert f2_stocks[0]["current_quantity"] == 5

    # 2. Daily production entry isolation
    # F1 posts a production run
    current_active_user = user_f1
    prod_payload_f1 = {
        "date": "2026-06-03",
        "worker_id": 1,
        "machine_id": 1,
        "product_id": 10,
        "product_size_ml": 250,
        "variety": "Standard/White",
        "packaging_size_name": "Box-1",
        "pieces_per_packet": 100,
        "packets_per_box_limit": 10,
        "total_boxes_made": 10,
        "loose_packets_made": 0,
        "blank_used_kg": 0,
        "bottom_used_kg": 0,
    }
    prod_res_f1 = client.post("/api/production/daily", json=prod_payload_f1)
    assert prod_res_f1.status_code == 201

    # F2 queries production logs (should not see F1's log)
    current_active_user = user_f2
    logs_res_f2 = client.get("/api/production/daily")  # Wait, check if GET exists or operations daily sequence
    # Let's hit the daily sequence endpoint instead
    seq_res_f2 = client.get("/api/v1/operations/daily-sequence")
    assert seq_res_f2.status_code == 200
    assert len(seq_res_f2.json()) == 0  # No sequence logs seeded in F2

    # 3. Sales & Invoice isolation
    # F1 posts invoice
    current_active_user = user_f1
    sale_payload_f1 = {
        "date": "2026-06-03",
        "customer_id": 1,
        "amount_paid": 0,
        "legal_invoice_type": "bill_of_supply",
        "items": [
            {
                "product_id": 10,
                "product_size_ml": 250,
                "variety": "Standard/White",
                "packaging_size_name": "Box-1",
                "boxes_sold": 5,
                "loose_packets_sold": 0,
                "rate_per_box": 100.0,
                "rate_per_packet": 10.0,
                "packets_per_box": 10
            }
        ]
    }
    sale_res_f1 = client.post("/api/sales/invoice", json=sale_payload_f1)
    assert sale_res_f1.status_code == 201

    # F2 queries outstanding dues (should not see F1's customer dues)
    current_active_user = user_f2
    dues_res_f2 = client.get("/api/sales/dues/pending")
    assert dues_res_f2.status_code == 200
    assert len(dues_res_f2.json()) == 0  # F2 customer Cust 2 has no dues

    # F2 tries to fetch outstanding dues list for payments
    payments_res_f2 = client.get("/api/payments/dues")
    assert payments_res_f2.status_code == 200
    assert float(payments_res_f2.json()["grand_total_outstanding"]) == 0.0

    # 4. Dashboard Summary Isolation
    # F1 summary shows values
    current_active_user = user_f1
    dash_res_f1 = client.get("/api/dashboard/summary")
    assert dash_res_f1.status_code == 200
    f1_stats = dash_res_f1.json()
    assert float(f1_stats["total_sales_last_7_days"]) > 0 or float(f1_stats["current_total_market_outstanding"]) > 0

    # F2 summary shows zeros
    current_active_user = user_f2
    dash_res_f2 = client.get("/api/dashboard/summary")
    assert dash_res_f2.status_code == 200
    f2_stats = dash_res_f2.json()
    assert float(f2_stats["total_sales_last_7_days"]) == 0.0
    assert float(f2_stats["current_total_market_outstanding"]) == 0.0

    # Clear dependency overrides when done
    for dep in [get_current_user, get_current_active_user, require_owner]:
        main_app.dependency_overrides.pop(dep, None)


def test_cross_factory_id_access_is_blocked_for_sensitive_routes():
    user_f1 = get_mock_owner_user(1)
    user_f2 = get_mock_owner_user(2)
    current_active_user = user_f1

    def local_get_active_user():
        return current_active_user

    main_app.dependency_overrides[get_current_user] = local_get_active_user
    main_app.dependency_overrides[get_current_active_user] = local_get_active_user
    main_app.dependency_overrides[require_owner] = local_get_active_user

    ensure_testclient_compatibility()
    client = TestClient(main_app)

    db = TestingSessionLocal()
    try:
        db.add_all([
            Factory(id=1, name="Factory A", subscription_status="active", active_plan="growth"),
            Factory(id=2, name="Factory B", subscription_status="active", active_plan="growth"),
            User(id=user_f1.id, factory_id=1, username=user_f1.username, email=user_f1.email, role="Owner", full_name=user_f1.full_name, password_hash="hash", is_verified=True),
            User(id=user_f2.id, factory_id=2, username=user_f2.username, email=user_f2.email, role="Owner", full_name=user_f2.full_name, password_hash="hash", is_verified=True),
            User(id=22, factory_id=2, username="staff-b@test.com", email="staff-b@test.com", role="Supervisor", full_name="Factory B Staff", password_hash="hash", is_verified=True),
            Worker(id=11, factory_id=1, name="Shared Worker", daily_wages=Decimal("800")),
            Worker(id=22, factory_id=2, name="Shared Worker", daily_wages=Decimal("900")),
            Machine(id=11, factory_id=1, name="Shared Machine", machine_type="Cup Machine", mould_size_ml=250, cup_size_ml=250, bottom_size_mm=52),
            Machine(id=22, factory_id=2, name="Shared Machine", machine_type="Cup Machine", mould_size_ml=250, cup_size_ml=250, bottom_size_mm=52),
            Customer(id=11, factory_id=1, name="Shared Customer", phone_number="9000000001", balance_amount=Decimal("0"), total_due=Decimal("0"), pending_balance=Decimal("0"), pending_dues=0),
            Customer(id=22, factory_id=2, name="Shared Customer", phone_number="9000000002", balance_amount=Decimal("500"), total_due=Decimal("500"), pending_balance=Decimal("500"), pending_dues=500),
            DailyProduction(id=22, factory_id=2, date=date(2026, 6, 3), worker_id=22, machine_id=22, product_size_ml=250, variety="Standard/White", packaging_size_name="Box-B", packets_per_box_limit=10, total_boxes_made=7),
            ActivityLog(id=22, factory_id=2, event_type="production", description="Factory B only", log_date=date(2026, 6, 3)),
            InvoiceDocument(id=22, factory_id=2, customer_id=22, invoice_number="B-001", invoice_date=date(2026, 6, 3), customer_name="Shared Customer", customer_phone="9000000002", bill_total=Decimal("500"), amount_paid=Decimal("0"), customer_total_due=Decimal("500"), payload_json={"items": []}),
            OutstandingBill(id=22, factory_id=2, customer_id=22, invoice_document_id=22, source_type="invoice", tracking_number="B-001", bill_date=date(2026, 6, 3), bill_amount=Decimal("500"), amount_paid=Decimal("0"), balance_amount=Decimal("500"), status="active"),
        ])
        db.commit()
    finally:
        db.close()

    current_active_user = user_f1

    assert client.patch("/api/sales/customers/22", json={"name": "Cross Tenant Edit"}).status_code == 404
    assert client.get("/api/sales/customers/22/balance").status_code == 200
    assert client.get("/api/sales/customers/22/balance").json()["customer_name"] == ""
    assert client.get("/api/sales/invoices/22/pdf").status_code == 404
    assert client.delete("/api/production/daily/22").status_code == 404
    assert client.put("/api/operations/sequence/22", json={"event_type": "production", "description": "cross edit"}).status_code == 404
    assert client.delete("/api/operations/sequence/22").status_code == 404
    assert client.delete("/api/v1/staff/22/delete").status_code == 404
    assert client.post("/api/automation/customers/22/portal-link").status_code == 404
    assert client.get("/api/reports/customer-weekly/22").status_code == 404
    assert client.post("/api/payments/add", json={"customer_id": 22, "amount_paid": 100, "payment_mode": "Cash", "date": "2026-06-03"}).status_code == 404

    delete_bill_res = client.delete("/api/sales/outstanding/22?confirm=true&reason=paid")
    assert delete_bill_res.status_code == 200
    assert delete_bill_res.json()["status"] == "error"

    db = TestingSessionLocal()
    try:
        assert db.query(Customer).filter(Customer.id == 22).one().name == "Shared Customer"
        assert db.query(InvoiceDocument).filter(InvoiceDocument.id == 22).one().pdf_generated_count == 0
        assert db.query(DailyProduction).filter(DailyProduction.id == 22).one().factory_id == 2
        assert db.query(ActivityLog).filter(ActivityLog.id == 22).one().description == "Factory B only"
        assert db.query(User).filter(User.id == 22).one().factory_id == 2
        assert db.query(OutstandingBill).filter(OutstandingBill.id == 22).one().balance_amount == Decimal("500.00")
        assert db.query(Payment).filter(Payment.factory_id == 1).count() == 0
    finally:
        db.close()

    for dep in [get_current_user, get_current_active_user, require_owner]:
        main_app.dependency_overrides.pop(dep, None)


def test_bulk_upload_rows_are_bound_to_authenticated_factory_only():
    user_f1 = get_mock_owner_user(1)
    user_f2 = get_mock_owner_user(2)
    db = TestingSessionLocal()
    try:
        db.add_all([
            Factory(id=1, name="Factory A", subscription_status="active", active_plan="growth"),
            Factory(id=2, name="Factory B", subscription_status="active", active_plan="growth"),
            User(id=user_f1.id, factory_id=1, username=user_f1.username, email=user_f1.email, role="Owner", full_name=user_f1.full_name, password_hash="hash", is_verified=True),
            User(id=user_f2.id, factory_id=2, username=user_f2.username, email=user_f2.email, role="Owner", full_name=user_f2.full_name, password_hash="hash", is_verified=True),
        ])
        apply_bulk_rows(
            db,
            user_f1,
            "worker",
            [{"name": "Same Name", "mobile_number": "9999999999", "daily_wages": Decimal("500"), "duty_hours": 8, "previous_attendance_details": 0}],
        )
        apply_bulk_rows(
            db,
            user_f2,
            "worker",
            [{"name": "Same Name", "mobile_number": "8888888888", "daily_wages": Decimal("700"), "duty_hours": 9, "previous_attendance_details": 0}],
        )
        db.commit()

        worker_f1 = db.query(Worker).filter(Worker.factory_id == 1, Worker.name == "Same Name").one()
        worker_f2 = db.query(Worker).filter(Worker.factory_id == 2, Worker.name == "Same Name").one()
        assert worker_f1.phone == "+919999999999"
        assert worker_f1.daily_wages == Decimal("500.00")
        assert worker_f2.phone == "+918888888888"
        assert worker_f2.daily_wages == Decimal("700.00")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Priority 2: Bulk Upload Idempotency Tests
# ---------------------------------------------------------------------------
def test_bulk_upload_idempotency():
    user = get_mock_owner_user(1)
    db = TestingSessionLocal()

    try:
        # Seed Factory
        db.add(Factory(id=1, name="Onboarding Factory"))
        db.commit()

        valid_rows = [
            {
                "row_type": "ACTUAL",
                "name": "Anjal Kumar",
                "mobile_number": "8285817277",
                "daily_wages": Decimal("300"),
                "duty_hours": Decimal("8"),
                "previous_attendance_details": Decimal("5"),
            }
        ]

        # Case 1: New Row Insert
        count1 = apply_bulk_rows(db, user, "worker", valid_rows)
        db.commit()
        assert count1 == 1

        workers = db.query(Worker).filter_by(factory_id=1, name="Anjal Kumar").all()
        assert len(workers) == 1
        assert workers[0].daily_wages == Decimal("300")
        assert workers[0].phone == "+918285817277"

        opening = db.query(WorkerOpeningAttendance).filter_by(factory_id=1, worker_id=workers[0].id).all()
        assert len(opening) == 1
        assert opening[0].present_days == Decimal("5")

        # Case 2: Upload same excel/rows again (Idempotent - no duplicates created)
        count2 = apply_bulk_rows(db, user, "worker", valid_rows)
        db.commit()
        assert count2 == 1

        workers_again = db.query(Worker).filter_by(factory_id=1, name="Anjal Kumar").all()
        assert len(workers_again) == 1  # Still only 1 worker!

        # Case 3: Duplicate rows in same upload
        valid_duplicate_rows = [
            {
                "row_type": "ACTUAL",
                "name": "Duplicate Worker",
                "mobile_number": "9999999999",
                "daily_wages": Decimal("350"),
                "duty_hours": Decimal("8"),
                "previous_attendance_details": Decimal("0"),
            },
            {
                "row_type": "ACTUAL",
                "name": "Duplicate Worker",
                "mobile_number": "9999999999",
                "daily_wages": Decimal("350"),
                "duty_hours": Decimal("8"),
                "previous_attendance_details": Decimal("0"),
            }
        ]
        count3 = apply_bulk_rows(db, user, "worker", valid_duplicate_rows)
        db.commit()
        assert count3 == 2  # Processed both rows

        workers_dup = db.query(Worker).filter_by(factory_id=1, name="Duplicate Worker").all()
        assert len(workers_dup) == 1  # But only 1 worker is saved in database!

        # Case 4: Changed row update
        changed_rows = [
            {
                "row_type": "ACTUAL",
                "name": "Anjal Kumar",
                "mobile_number": "8285817277",
                "daily_wages": Decimal("450"),  # Changed daily wage
                "duty_hours": Decimal("10"),   # Changed duty hours
                "previous_attendance_details": Decimal("10"), # Changed opening present days
            }
        ]
        count4 = apply_bulk_rows(db, user, "worker", changed_rows)
        db.commit()
        assert count4 == 1

        workers_changed = db.query(Worker).filter_by(factory_id=1, name="Anjal Kumar").all()
        assert len(workers_changed) == 1
        assert workers_changed[0].daily_wages == Decimal("450")  # Wage updated!
        assert workers_changed[0].duty_hours == Decimal("10")    # Hours updated!

        opening_changed = db.query(WorkerOpeningAttendance).filter_by(factory_id=1, worker_id=workers_changed[0].id).all()
        assert len(opening_changed) == 1
        assert opening_changed[0].present_days == Decimal("10")  # Opening attendance updated!

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Priority 3: Salary / Attendance Tests
# ---------------------------------------------------------------------------
def test_salary_attendance_flow():
    user = get_mock_owner_user(1)

    def local_get_active_user():
        return user

    main_app.dependency_overrides[get_current_user] = local_get_active_user
    main_app.dependency_overrides[get_current_active_user] = local_get_active_user
    main_app.dependency_overrides[require_owner] = local_get_active_user

    ensure_testclient_compatibility()
    client = TestClient(main_app)

    db = TestingSessionLocal()
    try:
        # Seed Factory, Worker
        db.add(Factory(id=1, name="Salary Factory"))
        worker = Worker(
            id=10,
            factory_id=1,
            name="John Wage",
            daily_wage_rate=Decimal("1000"),
            daily_wages=Decimal("1000"),
            shift_hours=8.0,
            duty_hours=8.0,
            is_active=True,
        )
        db.add(worker)
        db.flush()

        # Step 1: Onboarding opening attendance = 5 days present, 100 Rs advance paid
        opening = WorkerOpeningAttendance(
            factory_id=1,
            worker_id=worker.id,
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 5),
            present_days=Decimal("5"),
            advance_paid=Decimal("100"),
            notes="Opening details",
            created_by_user_id=user.id,
        )
        db.add(opening)
        db.commit()
    finally:
        db.close()

    # Step 2: Record 2 days of daily attendance logs via API (Present)
    # Day 1
    att_res1 = client.post("/api/workers/10/attendance", json={"date": "2026-05-06", "status": "Present", "duty_hours": 8.0})
    assert att_res1.status_code == 200
    # Day 2
    att_res2 = client.post("/api/workers/10/attendance", json={"date": "2026-05-07", "status": "Present", "duty_hours": 8.0})
    assert att_res2.status_code == 200

    # Step 3: Record an advance payment of 150 Rs via API
    adv_res = client.post("/api/workers/10/advance", json={"date": "2026-05-07", "amount": 150.0})
    assert adv_res.status_code == 200

    # Step 4: Run preview settlement (/settle without confirm)
    # Duty period covers both opening attendance and daily attendance
    settle_payload = {
        "worker_id": 10,
        "duty_from_date": "2026-05-01",
        "duty_to_date": "2026-05-10",
        "advance_cutoff_date": "2026-05-10",
        "confirm": False
    }
    preview_res = client.post("/api/workers/settle", json=settle_payload)
    assert preview_res.status_code == 200
    preview_data = preview_res.json()

    # Calculations verification:
    # opening_payable_days = 5
    # daily_duty_days = 2
    # total_duty_days = 7
    # rate = 1000
    # total_duty_amount = 7000
    # opening_advance = 100
    # daily_advance = 150
    # total_advance_deducted = 250
    # net_payable = 7000 - 250 = 6750
    assert Decimal(str(preview_data["total_duty_amount"])) == Decimal("7000.00")
    assert Decimal(str(preview_data["total_advance_deducted"])) == Decimal("250.00")
    assert Decimal(str(preview_data["net_payable"])) == Decimal("6750.00")
    assert preview_data["attendance_count"] == 2
    assert preview_data["advance_count"] == 1
    assert preview_data["settlement_id"] is None  # preview, not saved

    # Step 5: Confirm hisab settlement
    settle_payload["confirm"] = True
    confirm_res = client.post("/api/workers/settle", json=settle_payload)
    assert confirm_res.status_code == 200
    confirm_data = confirm_res.json()
    assert confirm_data["settlement_id"] is not None

    # Step 6: Verify database state is updated (logs marked is_settled=True)
    db = TestingSessionLocal()
    try:
        settlement = db.query(HisabSettlement).filter_by(id=confirm_data["settlement_id"]).first()
        assert settlement is not None
        assert settlement.net_paid == Decimal("6750.00")

        # Verify logs are closed
        att_logs = db.query(AttendanceLog).filter_by(worker_id=10).all()
        assert len(att_logs) == 2
        assert all(log.is_settled for log in att_logs)

        advances = db.query(AdvancePayment).filter_by(worker_id=10).all()
        assert len(advances) == 1
        assert advances[0].is_settled is True
    finally:
        db.close()

    for dep in [get_current_user, get_current_active_user, require_owner]:
        main_app.dependency_overrides.pop(dep, None)


# ---------------------------------------------------------------------------
# Priority 4: Trial/Subscription Limit Tests
# ---------------------------------------------------------------------------
def test_subscription_limits_and_trial_expiry(monkeypatch):
    monkeypatch.setattr("auth.is_trial_bypass_enabled", lambda: False)
    ensure_testclient_compatibility()
    client = TestClient(main_app)

    db = TestingSessionLocal()
    try:
        # Seed Factory with expired trial
        f_expired = Factory(
            id=100,
            name="Expired Factory",
            subscription_status="trial",
            trial_end_date=datetime.now(timezone.utc) - timedelta(days=5),
            subscription_end_date=None,
        )
        db.add(f_expired)
        
        # Seed Factory with inactive subscription
        f_inactive = Factory(
            id=200,
            name="Inactive Factory",
            subscription_status="inactive",
            subscription_end_date=datetime.now(timezone.utc) - timedelta(days=1),
            trial_end_date=datetime.now(timezone.utc) - timedelta(days=30),
        )
        db.add(f_inactive)

        # Seed Factory with active trial and machines seeded (limit check)
        f_limit = Factory(
            id=300,
            name="Active Limit Factory",
            subscription_status="trial",
            trial_end_date=datetime.now(timezone.utc) + timedelta(days=10),
        )
        db.add(f_limit)
        db.flush()

        # Seed users for these factories
        db.add(User(id=100, factory_id=100, username="user_exp", email="exp@test.com", password_hash="hash", role="Owner", is_verified=True))
        db.add(User(id=200, factory_id=200, username="user_inact", email="inact@test.com", password_hash="hash", role="Owner", is_verified=True))
        db.add(User(id=300, factory_id=300, username="user_limit", email="limit@test.com", password_hash="hash", role="Owner", is_verified=True))

        # Seed 7 machines for Factory 300 (which is the trial machine limit)
        for i in range(7):
            db.add(Machine(
                factory_id=300,
                name=f"Mac_{i+1}",
                machine_number=f"Mac_{i+1}",
                machine_sequence_number=f"SEQ_{i+1}",
                machine_type="Paper Cup",
                speed_per_minute=50,
                speed_bpm=50,
                speed_cups_per_minute=50,
            ))

        db.commit()
    finally:
        db.close()

    # Generate JWT Bearer tokens
    token_expired = create_access_token(subject="user_exp", role="Owner", factory_id=100)
    token_inactive = create_access_token(subject="user_inact", role="Owner", factory_id=200)
    token_limit = create_access_token(subject="user_limit", role="Owner", factory_id=300)

    # 1. Expired trial blocks requests (HTTP 402)
    headers_expired = {"Authorization": f"Bearer {token_expired}"}
    res_exp = client.get("/api/dashboard/summary", headers=headers_expired)
    assert res_exp.status_code == 402
    assert "subscription expired" in res_exp.json()["detail"].lower()

    # 2. Inactive subscription blocks requests (HTTP 402)
    headers_inactive = {"Authorization": f"Bearer {token_inactive}"}
    res_inact = client.get("/api/dashboard/summary", headers=headers_inactive)
    assert res_inact.status_code == 402
    assert "subscription expired" in res_inact.json()["detail"].lower()

    # 3. Active trial works, but machine limit is enforced (HTTP 403 on adding 8th)
    headers_limit = {"Authorization": f"Bearer {token_limit}"}
    
    # Check limit usage fetch endpoint (should report 7/7 used)
    limit_res = client.get("/api/onboarding/machines/limits", headers=headers_limit)
    assert limit_res.status_code == 200
    assert limit_res.json()["limit"] == 7
    assert limit_res.json()["limit_reached"] is True

    # Check that posting 8th machine is rejected (HTTP 403)
    machine_payload = {
        "machines": [
            {
                "machine_sequence_number": "SEQ_8",
                "name": "Eighth Machine",
                "cup_size_ml": 250,
                "bottom_size_mm": 52,
                "speed_cups_per_minute": 50,
            }
        ]
    }
    post_res = client.post("/api/onboarding/step2/machines", json=machine_payload, headers=headers_limit)
    assert post_res.status_code == 403
    assert post_res.json()["detail"]["code"] == "UPGRADE_REQUIRED"
    assert post_res.json()["detail"]["used"] == 7
    assert post_res.json()["detail"]["limit"] == 7


# ---------------------------------------------------------------------------
# Priority 5: Invoice PDF Smoke Test
# ---------------------------------------------------------------------------
def test_invoice_pdf_smoke_and_isolation():
    user_f1 = get_mock_owner_user(1)
    user_f2 = get_mock_owner_user(2)

    current_active_user = user_f1

    def local_get_active_user():
        return current_active_user

    main_app.dependency_overrides[get_current_user] = local_get_active_user
    main_app.dependency_overrides[get_current_active_user] = local_get_active_user
    main_app.dependency_overrides[require_owner] = local_get_active_user

    ensure_testclient_compatibility()
    client = TestClient(main_app)

    db = TestingSessionLocal()
    try:
        # Seed Factory 1 and 2
        db.add(Factory(id=1, name="Factory 1", subscription_status="active", active_plan="growth"))
        db.add(Factory(id=2, name="Factory 2", subscription_status="active", active_plan="growth"))
        
        # Seed User
        db.add(User(id=user_f1.id, factory_id=1, username=user_f1.username, email=user_f1.email, role="Owner", full_name=user_f1.full_name, password_hash="hash", is_verified=True))
        db.add(User(id=user_f2.id, factory_id=2, username=user_f2.username, email=user_f2.email, role="Owner", full_name=user_f2.full_name, password_hash="hash", is_verified=True))

        # Seed InvoiceDocument under Factory 1
        invoice_doc = InvoiceDocument(
            id=500,
            factory_id=1,
            invoice_number="12345",
            invoice_date=date.today(),
            customer_name="Cust 1",
            customer_phone="9876543210",
            payment_method="Cash",
            bill_total=Decimal("800.00"),
            amount_paid=Decimal("200.00"),
            customer_total_due=Decimal("600.00"),
            status="created",
            payload_json={
                "invoice": {
                    "invoice_id": "12345",
                    "invoice_date": date.today().isoformat(),
                    "customer_name": "Cust 1",
                    "customer_phone": "9876543210",
                    "payment_method": "Cash",
                    "bill_total": 800.00,
                    "amount_paid": 200.00,
                    "customer_total_due": 600.00,
                },
                "items": [
                    {
                        "product_size_ml": 250,
                        "variety": "Standard/White",
                        "packaging_size_name": "Box-1",
                        "boxes_sold": 8,
                        "line_total": 800.00,
                    }
                ]
            }
        )
        db.add(invoice_doc)
        db.commit()
    finally:
        db.close()

    # 1. Factory 1 Owner fetches the PDF (Valid 200 Response + PDF Content-Type)
    current_active_user = user_f1
    pdf_res = client.get("/api/sales/invoices/500/pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert len(pdf_res.content) > 0

    # 2. Factory 2 Owner tries to fetch the F1 PDF (404 Isolation check)
    current_active_user = user_f2
    pdf_res_f2 = client.get("/api/sales/invoices/500/pdf")
    assert pdf_res_f2.status_code == 404
    assert "invoice not found" in pdf_res_f2.json()["detail"].lower()

    for dep in [get_current_user, get_current_active_user, require_owner]:
        main_app.dependency_overrides.pop(dep, None)

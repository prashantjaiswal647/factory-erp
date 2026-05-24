import pytest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import User, Worker, WorkerOpeningAttendance, Factory, AttendanceLog, AdvancePayment, HisabSettlement
from routers.staff import staff_v1_router, get_db, require_owner, get_current_active_user
from routers.attendance import calculate_settlement, SettlementRequest

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

mock_user = None

def override_get_current_active_user():
    global mock_user
    return mock_user

def override_require_owner():
    global mock_user
    if mock_user and mock_user.role != "Owner":
        raise HTTPException(status_code=403, detail="Owner privileges required")
    return mock_user

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # Seed Factories
    f1 = Factory(id=1, name="Factory One", subscription_status="trial_active", active_plan="basic")
    f2 = Factory(id=2, name="Factory Two", subscription_status="trial_active", active_plan="basic")
    db.add(f1)
    db.add(f2)
    db.commit()
    db.close()

def build_client():
    app = FastAPI()
    app.include_router(staff_v1_router)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user
    app.dependency_overrides[require_owner] = override_require_owner
    return TestClient(app)

def test_create_staff_with_opening_attendance():
    global mock_user
    client = build_client()
    
    mock_user = SimpleNamespace(id=1, factory_id=1, role="Owner")
    
    # Create Worker with opening attendance
    payload = {
        "name": "Operator Worker",
        "phone": "9999999999",
        "password": "securepassword123",
        "confirm_password": "securepassword123",
        "role": "worker",
        "status": "active",
        "opening_attendance": {
            "period_start": "2026-05-01",
            "period_end": "2026-05-15",
            "present_days": 12.0,
            "half_days": 1.0,
            "absent_days": 2.0,
            "paid_leave_days": 0.0,
            "overtime_hours": 5.0,
            "advance_paid": 500.0,
            "deductions": 50.0,
            "notes": "First half May"
        }
    }
    
    response = client.post("/api/v1/staff/create", json=payload)
    assert response.status_code == 201
    res_data = response.json()
    
    assert res_data["opening_attendance"] is not None
    assert res_data["opening_attendance"]["present_days"] == 12.0
    assert res_data["opening_attendance"]["period_start"] == "2026-05-01"
    
    db = TestingSessionLocal()
    worker = db.query(Worker).filter(Worker.factory_id == 1).first()
    assert worker is not None
    assert worker.name == "Operator Worker"
    
    oa = db.query(WorkerOpeningAttendance).filter(WorkerOpeningAttendance.worker_id == worker.id).first()
    assert oa is not None
    assert oa.present_days == 12.0
    assert oa.overtime_hours == 5.0
    assert oa.advance_paid == 500.0
    db.close()


def test_opening_attendance_crud_endpoints():
    global mock_user
    client = build_client()
    
    # First seed a Worker and User
    db = TestingSessionLocal()
    user = User(id=10, factory_id=1, username="+919999999999", phone_number="+919999999999", full_name="Worker Staff", role="Operator", password_hash="hash")
    worker = Worker(id=100, factory_id=1, name="Worker Staff", phone="+919999999999", is_active=True)
    db.add(user)
    db.add(worker)
    db.commit()
    db.close()
    
    mock_user = SimpleNamespace(id=1, factory_id=1, role="Owner")
    
    # Create opening attendance
    payload = {
        "period_start": "2026-05-01",
        "period_end": "2026-05-15",
        "present_days": 10.0,
        "half_days": 0.0,
        "absent_days": 5.0,
        "paid_leave_days": 0.0,
        "overtime_hours": 0.0,
        "advance_paid": 200.0,
        "deductions": 0.0,
        "notes": "Testing notes"
    }
    
    # POST
    resp = client.post("/api/v1/staff/10/opening-attendance", json=payload)
    assert resp.status_code == 201
    assert resp.json()["present_days"] == 10.0
    
    # GET
    resp = client.get("/api/v1/staff/10/opening-attendance")
    assert resp.status_code == 200
    assert resp.json()["advance_paid"] == 200.0
    
    # PATCH
    resp = client.patch("/api/v1/staff/10/opening-attendance", json={"period_start": "2026-05-01", "period_end": "2026-05-15", "advance_paid": 300.0})
    assert resp.status_code == 200
    assert resp.json()["advance_paid"] == 300.0
    
    # DELETE
    resp = client.delete("/api/v1/staff/10/opening-attendance")
    assert resp.status_code == 204
    
    # Verify deleted
    resp = client.get("/api/v1/staff/10/opening-attendance")
    assert resp.status_code == 404


def test_settlement_merges_opening_attendance_and_excludes_overlap():
    db = TestingSessionLocal()
    
    worker = Worker(id=50, factory_id=1, name="Legend Worker", phone="12345", daily_wage_rate=500, shift_hours=8.0, is_active=True)
    db.add(worker)
    
    # Add opening attendance: May 1st to May 15th
    oa = WorkerOpeningAttendance(
        factory_id=1,
        worker_id=50,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 15),
        present_days=12.0,
        half_days=1.0, # 0.5 days
        absent_days=2.0,
        paid_leave_days=0.0,
        overtime_hours=4.0,
        advance_paid=1000.0,
        deductions=100.0,
        created_by_user_id=1
    )
    db.add(oa)
    
    # Add daily attendance logs:
    # Overlapping date (should be ignored): May 10th
    log_ignored = AttendanceLog(factory_id=1, worker_id=50, date=date(2026, 5, 10), status="Present")
    # Non-overlapping date (should be counted): May 20th
    log_counted = AttendanceLog(factory_id=1, worker_id=50, date=date(2026, 5, 20), status="Present")
    
    db.add(log_ignored)
    db.add(log_counted)
    
    # Add daily advance logs:
    # Overlapping advance (should be ignored): May 5th
    adv_ignored = AdvancePayment(factory_id=1, worker_id=50, date=date(2026, 5, 5), amount=500.0)
    # Non-overlapping advance (should be counted): May 25th
    adv_counted = AdvancePayment(factory_id=1, worker_id=50, date=date(2026, 5, 25), amount=300.0)
    
    db.add(adv_ignored)
    db.add(adv_counted)
    
    db.commit()
    
    # Calculate Settlement from May 1st to May 31st
    req = SettlementRequest(
        worker_id=50,
        duty_from_date=date(2026, 5, 1),
        duty_to_date=date(2026, 5, 31),
        advance_cutoff_date=date(2026, 5, 31)
    )
    
    res = calculate_settlement(db, 1, worker, req)
    
    # Total duty days: 12.0 (opening present) + 0.5 (opening half) + 1.0 (daily counted) = 13.5 days
    # Overtime hours: 4.0 hours (opening) -> 4 * (500 / 8) = 250 Rs
    # Gross duty: 13.5 * 500 + 250 = 6750 + 250 = 7000 Rs
    assert res.total_duty_amount == Decimal("7000.00")
    
    # Total advances/deductions deducted: 1000 (opening advance) + 100 (opening deductions) + 300 (daily counted) = 1400 Rs
    assert res.total_advance_deducted == Decimal("1400.00")
    
    # Net payable: 7000 - 1400 = 5600 Rs
    assert res.net_payable == Decimal("5600.00")
    
    # Ensure count is correct (only includes daily non-overlapping records)
    assert res.attendance_count == 1 # only May 20th
    assert res.advance_count == 1 # only May 25th
    
    db.close()

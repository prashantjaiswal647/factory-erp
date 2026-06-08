import pytest
from types import SimpleNamespace
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import User, SuperAdminAuditLog, Factory
from routers.staff import (
    staff_v1_router,
    security_v1_router,
    get_db,
    get_current_active_user,
    require_owner,
)


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


# SQLite in-memory engine for isolation
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

# Mock global active user session
mock_user = None

def override_get_current_active_user():
    global mock_user
    return mock_user

def override_require_owner():
    global mock_user
    if mock_user and mock_user.role not in {"Owner", "Sub-Owner"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Owner privileges required")
    return mock_user

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # Seed Factory
    factory1 = Factory(id=1, name="Factory One", subscription_status="trial_active", active_plan="basic")
    factory2 = Factory(id=2, name="Factory Two", subscription_status="trial_active", active_plan="basic")
    db.add(factory1)
    db.add(factory2)
    db.commit()
    db.close()

def build_client():
    ensure_testclient_compatibility()
    app = FastAPI()
    app.include_router(staff_v1_router)
    app.include_router(security_v1_router)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_get_current_active_user
    app.dependency_overrides[require_owner] = override_require_owner
    return TestClient(app)

def test_staff_list_zero_leakage_and_hidden_scoping():
    global mock_user
    db = TestingSessionLocal()
    
    # Seed a Supervisor under Factory 1 and Operator under Factory 2
    staff1 = User(id=10, factory_id=1, username="+918888888888", phone_number="+918888888888", full_name="F1 Staff", role="Supervisor", password_hash="hash")
    staff2 = User(id=20, factory_id=2, username="+917777777777", phone_number="+917777777777", full_name="F2 Staff", role="Operator", password_hash="hash")
    db.add(staff1)
    db.add(staff2)
    db.commit()
    db.close()
    
    client = build_client()
    
    # Log in as Owner of Factory 1
    mock_user = SimpleNamespace(id=1, factory_id=1, username="owner1", full_name="Owner One", role="Owner")
    
    response = client.get("/api/v1/staff/list")
    assert response.status_code == 200
    records = response.json()
    
    # Assert hidden WHERE filter applied successfully
    assert len(records) == 1
    assert records[0]["full_name"] == "F1 Staff"
    
    # Assert Zero Factory ID UI Leakage: factory_id field must not be in response
    assert "factory_id" not in records[0]

def test_staff_creation_hashes_instantly_and_inherits_factory():
    global mock_user
    client = build_client()
    
    # Log in as Owner of Factory 1
    mock_user = SimpleNamespace(id=1, factory_id=1, username="owner1", full_name="Owner One", role="Owner")
    
    payload = {
        "name": "New Supervisor",
        "phone": "8888888888",
        "password": "staffSecurePassword1",
        "role": "supervisor"
    }
    
    response = client.post("/api/v1/staff/create", json=payload)
    assert response.status_code == 201
    record = response.json()
    
    assert record["full_name"] == "New Supervisor"
    assert record["role"] == "Supervisor"
    assert "factory_id" not in record  # No leakage
    
    # Verify in DB
    db = TestingSessionLocal()
    db_user = db.query(User).filter(User.full_name == "New Supervisor").first()
    assert db_user is not None
    assert db_user.factory_id == 1  # Inherited Owner factory_id
    assert db_user.password_hash != "staffSecurePassword1"  # Instantly hashed
    db.close()

def test_worker_creation_syncs_with_workers_table():
    global mock_user
    client = build_client()
    
    # Log in as Owner of Factory 1
    mock_user = SimpleNamespace(id=1, factory_id=1, username="owner1", full_name="Owner One", role="Owner")
    
    payload = {
        "name": "New Worker Operator",
        "phone": "9998887776",
        "password": "workerSecurePassword123",
        "role": "worker"
    }
    
    response = client.post("/api/v1/staff/create", json=payload)
    assert response.status_code == 201
    record = response.json()
    
    assert record["full_name"] == "New Worker Operator"
    assert record["role"] == "Operator"
    assert "factory_id" not in record
    
    # Verify in DB (both users and workers table)
    db = TestingSessionLocal()
    db_user = db.query(User).filter(User.full_name == "New Worker Operator").first()
    assert db_user is not None
    assert db_user.factory_id == 1
    
    # Check corresponding Worker table row
    from models import Worker
    db_worker = db.query(Worker).filter(Worker.factory_id == 1).filter(Worker.name == "New Worker Operator").first()
    assert db_worker is not None
    assert db_worker.phone == "+919998887776"
    assert db_worker.is_active is True
    db.close()

def test_staff_edit_and_delete_with_multi_tenant_boundaries():
    global mock_user
    db = TestingSessionLocal()
    staff1 = User(id=10, factory_id=1, username="+918888888888", phone_number="+918888888888", full_name="F1 Staff", role="Supervisor", password_hash="hash")
    db.add(staff1)
    db.commit()
    db.close()
    
    client = build_client()
    
    # Attempt to edit as Owner of Factory 2 (Cross-factory attempt)
    mock_user = SimpleNamespace(id=2, factory_id=2, username="owner2", full_name="Owner Two", role="Owner")
    edit_response = client.put("/api/v1/staff/10/update", json={"name": "Attacker Hack"})
    assert edit_response.status_code == 404  # Not found due to scope restriction
    
    # Edit as correct Owner of Factory 1
    mock_user = SimpleNamespace(id=1, factory_id=1, username="owner1", full_name="Owner One", role="Owner")
    edit_response = client.put("/api/v1/staff/10/update", json={"name": "Updated Staff Name"})
    assert edit_response.status_code == 200
    assert edit_response.json()["full_name"] == "Updated Staff Name"
    
    # Delete as incorrect Owner
    mock_user = SimpleNamespace(id=2, factory_id=2, username="owner2", full_name="Owner Two", role="Owner")
    del_response = client.delete("/api/v1/staff/10/delete")
    assert del_response.status_code == 404
    
    # Delete as correct Owner
    mock_user = SimpleNamespace(id=1, factory_id=1, username="owner1", full_name="Owner One", role="Owner")
    del_response = client.delete("/api/v1/staff/10/delete")
    assert del_response.status_code == 204


def test_owner_can_create_and_delete_sub_owner():
    global mock_user
    client = build_client()
    mock_user = SimpleNamespace(id=99, factory_id=1, username="owner1", full_name="Owner One", role="Owner")

    create_response = client.post(
        "/api/v1/staff/create",
        json={
            "name": "Second Owner",
            "phone": "8888888801",
            "password": "securePassword1",
            "role": "sub_owner",
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["role"] == "Sub-Owner"

    deactivate_response = client.put(
        f"/api/v1/staff/{create_response.json()['id']}/update",
        json={"status": "inactive"},
    )
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False

    delete_response = client.delete(f"/api/v1/staff/{create_response.json()['id']}/delete")
    assert delete_response.status_code == 204


@pytest.mark.parametrize("role_value", ["sub_owner", "Sub-Owner", "Sub Owner"])
def test_owner_can_create_sub_owner_from_supported_role_aliases(role_value):
    global mock_user
    client = build_client()
    mock_user = SimpleNamespace(id=99, factory_id=1, username="owner1", full_name="Owner One", role="Owner")

    response = client.post(
        "/api/v1/staff/create",
        json={
            "name": f"Alias {role_value}",
            "phone": f"8888888{len(role_value):03d}",
            "password": "securePassword1",
            "role": role_value,
        },
    )

    assert response.status_code == 201
    assert response.json()["role"] == "Sub-Owner"


def test_owner_can_promote_supervisor_to_sub_owner():
    global mock_user
    db = TestingSessionLocal()
    db.add(
        User(
            id=31,
            factory_id=1,
            username="supervisor31",
            full_name="Supervisor Thirty One",
            role="Supervisor",
            password_hash="hash",
        )
    )
    db.commit()
    db.close()

    client = build_client()
    mock_user = SimpleNamespace(id=99, factory_id=1, username="owner1", full_name="Owner One", role="Owner")
    response = client.put("/api/v1/staff/31/update", json={"role": "Sub Owner"})

    assert response.status_code == 200
    assert response.json()["role"] == "Sub-Owner"


def test_sub_owner_can_manage_normal_staff_but_not_owner_or_sub_owner():
    global mock_user
    db = TestingSessionLocal()
    owner = User(
        id=1,
        factory_id=1,
        username="owner1",
        full_name="Owner One",
        role="Owner",
        password_hash="hash",
    )
    sub_owner = User(
        id=2,
        factory_id=1,
        username="subowner1",
        full_name="Sub Owner One",
        role="Sub-Owner",
        password_hash="hash",
    )
    supervisor = User(
        id=3,
        factory_id=1,
        username="supervisor1",
        full_name="Supervisor One",
        role="Supervisor",
        password_hash="hash",
    )
    other_factory_staff = User(
        id=4,
        factory_id=2,
        username="supervisor2",
        full_name="Supervisor Two",
        role="Supervisor",
        password_hash="hash",
    )
    db.add_all([owner, sub_owner, supervisor, other_factory_staff])
    db.commit()
    db.close()

    client = build_client()
    mock_user = SimpleNamespace(
        id=2,
        factory_id=1,
        username="subowner1",
        full_name="Sub Owner One",
        role="Sub-Owner",
    )

    list_response = client.get("/api/v1/staff/list")
    assert list_response.status_code == 200
    assert {item["id"] for item in list_response.json()} == {1, 2, 3}

    owner_edit = client.put("/api/v1/staff/1/update", json={"name": "Changed Owner"})
    assert owner_edit.status_code == 403

    owner_delete = client.delete("/api/v1/staff/1/delete")
    assert owner_delete.status_code == 403

    create_owner = client.post(
        "/api/v1/staff/create",
        json={
            "name": "Forbidden Owner",
            "phone": "8888888802",
            "password": "securePassword1",
            "role": "sub_owner",
        },
    )
    assert create_owner.status_code == 403

    normal_staff_update = client.put("/api/v1/staff/3/update", json={"name": "Updated Supervisor"})
    assert normal_staff_update.status_code == 200

    cross_factory_update = client.put("/api/v1/staff/4/update", json={"name": "Cross Factory"})
    assert cross_factory_update.status_code == 404

    normal_staff_delete = client.delete("/api/v1/staff/3/delete")
    assert normal_staff_delete.status_code == 204

def test_otp_factory_id_extraction_gateway():
    global mock_user
    db = TestingSessionLocal()
    owner = User(id=1, factory_id=101, username="+919999999999", phone_number="+919999999999", full_name="Owner Phone", role="Owner", password_hash="hash")
    db.add(owner)
    db.commit()
    db.close()
    
    client = build_client()
    
    # 1. Request OTP for unregistered number
    req_res = client.post("/api/v1/security/request-factory-id", json={"phone_number": "1111111111"})
    assert req_res.status_code == 404
    
    # 2. Request OTP for registered Owner
    req_res = client.post("/api/v1/security/request-factory-id", json={"phone_number": "9999999999"})
    assert req_res.status_code == 202
    
    # Fetch seed OTP from db
    db = TestingSessionLocal()
    from models import OTPStore
    otp_record = db.query(OTPStore).filter(OTPStore.phone_number == "+919999999999").first()
    assert otp_record is not None
    otp_code = otp_record.otp_code
    db.close()
    
    # 3. Verify OTP and check raw string return value of factory_id
    verify_res = client.post(
        "/api/v1/security/verify-factory-id",
        json={"phone_number": "9999999999", "otp_code": otp_code}
    )
    assert verify_res.status_code == 200
    assert verify_res.text == "101"  # Returns raw factory_id explicitly to the client

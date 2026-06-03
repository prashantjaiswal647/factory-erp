import time
import pytest
from decimal import Decimal
from fastapi import FastAPI, Request, Response, Depends, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base, get_db
from models import Factory, Customer, FinishedGoodsStock, User
from main import app as main_app, _rate_limit_store
from auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    generate_storefront_session_token,
    decode_storefront_session_token,
    create_access_token
)

# Test db config
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
def setup_db_and_overrides(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-1234567890-test")
    ensure_testclient_compatibility()
    main_app.dependency_overrides[get_db] = override_get_db
    
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    try:
        # Seed Factory
        factory = Factory(id=1, name="Test Factory", subscription_status="active", active_plan="growth")
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
        
        # Seed Customer
        customer = Customer(
            id=10,
            factory_id="1",
            name="Test Customer",
            phone_number="+919876543210",
            contact_number="9876543210",
            store_token="test_store_token_123",
            portal_access_token="test_store_token_123",
            is_portal_approved=True
        )
        db.add(customer)
        db.commit()
    finally:
        db.close()
        
    _rate_limit_store.clear()
    yield
    _rate_limit_store.clear()

def test_access_token_expiration_reduced():
    """Verify that ACCESS_TOKEN_EXPIRE_MINUTES is set to a safe production default (8 hours = 480 minutes)."""
    assert ACCESS_TOKEN_EXPIRE_MINUTES == 480

def test_storefront_session_token_cryptography():
    """Verify that storefront session tokens sign and decode correctly, and reject expired or malformed signatures."""
    token = generate_storefront_session_token(customer_id=10, store_token="test_store_token_123")
    assert len(token.split(".")) == 4
    
    # Successful decode
    decoded = decode_storefront_session_token(token)
    assert decoded is not None
    assert decoded[0] == 10
    assert decoded[1] == "test_store_token_123"
    
    # Invalid token mismatch
    assert decode_storefront_session_token("invalid.token") is None
    assert decode_storefront_session_token(token + "manipulated") is None
    
    # Expired token
    expired_token = generate_storefront_session_token(customer_id=10, store_token="test_store_token_123", validity_seconds=-1)
    assert decode_storefront_session_token(expired_token) is None

def test_verify_customer_rate_limiting():
    """Verify that the verify-customer endpoint rate limits requests from the same IP client (5 requests/minute)."""
    client = TestClient(main_app)
    
    payload = {
        "store_token": "test_store_token_123",
        "phone_number": "9876543210"
    }
    
    # Send 5 valid/invalid requests
    for i in range(5):
        response = client.post("/api/store/verify-customer", json=payload)
        # Should succeed or fail with 4xx depending on correctness, but not 429
        assert response.status_code != 429
        
    # The 6th request must trigger rate limiting (429)
    response = client.post("/api/store/verify-customer", json=payload)
    assert response.status_code == 429
    assert response.json()["detail"] == "Too many verification attempts. Please try again after a minute."

def test_storefront_session_guards():
    """Verify that storefront endpoints enforce session verification via X-Storefront-Session or Cookie."""
    client = TestClient(main_app)
    store_token = "test_store_token_123"
    
    # 1. Access storefront details without token -> 401
    response = client.get(f"/api/storefront/{store_token}")
    assert response.status_code == 401
    assert "session verification required" in response.json()["detail"].lower()
    
    # 2. Access with invalid token -> 403
    response = client.get(f"/api/storefront/{store_token}", headers={"X-Storefront-Session": "invalid_session_token"})
    assert response.status_code == 403
    assert "invalid or expired storefront session" in response.json()["detail"].lower()
    
    # 3. Request OTP / Verify customer storefront first to fetch token
    verify_payload = {
        "store_token": store_token,
        "phone_number": "9876543210"
    }
    verify_res = client.post("/api/store/verify-customer", json=verify_payload)
    assert verify_res.status_code == 200
    res_data = verify_res.json()
    session_token = res_data.get("storefront_session_token")
    assert session_token is not None
    
    # 4. Access storefront details with header token -> 200
    response = client.get(f"/api/storefront/{store_token}", headers={"X-Storefront-Session": session_token})
    assert response.status_code == 200
    
    # 5. Access storefront details with cookie token -> 200
    # Clear client headers and let the cookie handle it
    client.cookies.set("storefront_session", session_token)
    response = client.get(f"/api/storefront/{store_token}")
    assert response.status_code == 200
    
    # 6. Access storefront checkout order without token -> 401
    client.cookies.clear()
    order_payload = {
        "payment_method": "Normal_Credit",
        "items": [{"product_id": 1, "quantity": 10}],
        "terms_accepted": True
    }
    response = client.post(f"/api/storefront/{store_token}/order", json=order_payload)
    assert response.status_code == 401
    
    # 7. Access storefront checkout order with token -> Should bypass auth guard
    # It might fail with 400/404 due to database constraints, but should NOT be 401/403
    response = client.post(
        f"/api/storefront/{store_token}/order", 
        json=order_payload, 
        headers={"X-Storefront-Session": session_token}
    )
    assert response.status_code not in (401, 403)


def test_priority1_n8n_webhook_security(monkeypatch):
    """Verify webhook endpoint /api/ai/n8n-webhook is secured by X-N8N-API-KEY and fails safely."""
    client = TestClient(main_app)
    
    # 1. Missing N8N_API_KEY environment variable -> Should fail with 503
    monkeypatch.delenv("N8N_API_KEY", raising=False)
    response = client.post(
        "/api/ai/n8n-webhook",
        json={"factory_id": 1, "user_message": "hello"},
        headers={"X-N8N-API-KEY": "some-key"}
    )
    assert response.status_code == 503
    assert "N8N_API_KEY is not configured" in response.json()["detail"]
    
    # 2. Configured N8N_API_KEY but wrong X-N8N-API-KEY header -> Should fail with 401
    monkeypatch.setenv("N8N_API_KEY", "secure_n8n_api_key_123")
    response = client.post(
        "/api/ai/n8n-webhook",
        json={"factory_id": 1, "user_message": "hello"},
        headers={"X-N8N-API-KEY": "wrong_key"}
    )
    assert response.status_code == 401
    assert "Unauthorized" in response.json()["detail"]
    
    # 3. Configured N8N_API_KEY and correct X-N8N-API-KEY header
    # It should pass auth check. It will try to query the Factory 1.
    # Since in setup_db_and_overrides we seed Factory ID 1, this should proceed to Groq LLM initialization.
    # Groq LLM requires GROQ_API_KEY. If not set, it returns 503 "GROQ_API_KEY or Groq dependencies are not configured".
    # This is a successful auth bypass!
    response = client.post(
        "/api/ai/n8n-webhook",
        json={"factory_id": 1, "user_message": "hello"},
        headers={"X-N8N-API-KEY": "secure_n8n_api_key_123"}
    )
    assert response.status_code in (503, 404, 200, 502)
    # The detail should not be about authentication
    if response.status_code == 503:
        assert "GROQ_API_KEY or Groq" in response.json()["detail"]


def test_priority1_telegram_crypto_fails_safely_when_secret_missing(monkeypatch):
    """Verify telegram_crypto get_encryption_key fails safely if JWT_SECRET_KEY is missing."""
    from telegram_crypto import get_encryption_key
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        get_encryption_key()
    assert "JWT_SECRET_KEY environment variable is required" in str(excinfo.value)


def test_priority2_global_template_approval_access_control():
    """Verify that global machine template approval is restricted to Super Admin only."""
    from routers.super_admin import require_super_admin
    client = TestClient(main_app)
    
    # 1. Access without super admin credentials -> Should be blocked (401)
    response = client.patch("/api/admin/templates/999/approve")
    assert response.status_code == 401
    
    # 2. Overriding require_super_admin -> Bypasses check, goes to route logic
    # It should return 404 Not Found since template 999 does not exist in SQLite DB.
    main_app.dependency_overrides[require_super_admin] = lambda: "super_admin@test.com"
    response = client.patch("/api/admin/templates/999/approve")
    assert response.status_code == 404
    assert "Machine template not found" in response.json()["detail"]
    
    # Clean up overrides
    main_app.dependency_overrides.pop(require_super_admin, None)


def test_priority3_expense_access_control():
    """Verify expense access control allows Owner, Sub-Owner, Supervisor, and forbids Operator, Worker."""
    from types import SimpleNamespace
    from auth import get_current_user
    client = TestClient(main_app)
    
    # 1. Test allowed roles (Owner, Sub-Owner, Supervisor)
    allowed_roles = ["Owner", "Sub-Owner", "Supervisor"]
    for role in allowed_roles:
        mock_user = SimpleNamespace(id=1, factory_id=1, role=role, is_active=True, full_name="Test User", username="test")
        main_app.dependency_overrides[get_current_user] = lambda: mock_user
        
        # Test GET /api/expenses
        response = client.get("/api/expenses")
        assert response.status_code == 200
        
        # Test POST /api/expenses
        payload = {"expense_name": "Test Expense", "amount": 100.0, "category": "Office"}
        response = client.post("/api/expenses", json=payload)
        assert response.status_code == 201
        
    # 2. Test restricted roles (Operator, Worker)
    restricted_roles = ["Operator", "Worker"]
    for role in restricted_roles:
        mock_user = SimpleNamespace(id=1, factory_id=1, role=role, is_active=True, full_name="Test User", username="test")
        main_app.dependency_overrides[get_current_user] = lambda: mock_user
        
        # Test GET /api/expenses
        response = client.get("/api/expenses")
        assert response.status_code == 403
        
        # Test POST /api/expenses
        payload = {"expense_name": "Test Expense", "amount": 100.0, "category": "Office"}
        response = client.post("/api/expenses", json=payload)
        assert response.status_code == 403
        
    # Clean up overrides
    main_app.dependency_overrides.pop(get_current_user, None)


def test_priority3_machine_onboarding_access_control():
    """Verify machine onboarding settings are restricted to Owner, Sub-Owner, Supervisor only."""
    from types import SimpleNamespace
    from auth import get_current_user
    client = TestClient(main_app)
    
    # Allowed roles: Owner, Sub-Owner, Supervisor
    allowed_roles = ["Owner", "Sub-Owner", "Supervisor"]
    for role in allowed_roles:
        mock_user = SimpleNamespace(id=1, factory_id=1, role=role, is_active=True, full_name="Test User", username="test")
        main_app.dependency_overrides[get_current_user] = lambda: mock_user
        
        # Test GET /api/machine-onboardings
        response = client.get("/api/machine-onboardings")
        assert response.status_code == 200
        
        # Test POST /api/machine-onboardings
        payload = {
            "machine_type": "Paper Cup",
            "base_config": {},
            "custom_fields": {}
        }
        response = client.post("/api/machine-onboardings", json=payload)
        assert response.status_code == 201
        
        # Test POST /api/machines/setup
        setup_payload = {
            "machine_name": "Test Cup Machine",
            "default_speed": 40.0,
            "target_output_per_shift": 1000,
            "raw_materials_mapped": ["Blank", "Bottom"]
        }
        response = client.post("/api/machines/setup", json=setup_payload)
        assert response.status_code == 201
        
    # Restricted roles: Operator, Worker
    restricted_roles = ["Operator", "Worker"]
    for role in restricted_roles:
        mock_user = SimpleNamespace(id=1, factory_id=1, role=role, is_active=True, full_name="Test User", username="test")
        main_app.dependency_overrides[get_current_user] = lambda: mock_user
        
        # Test GET /api/machine-onboardings
        response = client.get("/api/machine-onboardings")
        assert response.status_code == 403
        
        # Test POST /api/machine-onboardings
        payload = {
            "machine_type": "Paper Cup",
            "base_config": {},
            "custom_fields": {}
        }
        response = client.post("/api/machine-onboardings", json=payload)
        assert response.status_code == 403
        
        # Test POST /api/machines/setup
        setup_payload = {
            "machine_name": "Test Cup Machine",
            "default_speed": 40.0,
            "target_output_per_shift": 1000,
            "raw_materials_mapped": ["Blank", "Bottom"]
        }
        response = client.post("/api/machines/setup", json=setup_payload)
        assert response.status_code == 403
        
    # Active machines GET /api/machines/active should be allowed for Operator/Worker
    for role in restricted_roles:
        mock_user = SimpleNamespace(id=1, factory_id=1, role=role, is_active=True, full_name="Test User", username="test")
        main_app.dependency_overrides[get_current_user] = lambda: mock_user
        
        response = client.get("/api/machines/active")
        assert response.status_code == 200
        
    # Clean up overrides
    main_app.dependency_overrides.pop(get_current_user, None)


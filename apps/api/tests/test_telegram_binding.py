import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timezone, timedelta

from db import Base, get_db
from models import Factory, User
from auth import get_current_user
from routers.integrations import router

# 1. Setup sqlite database for isolated tests
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

# Mock user and factory details
MOCK_FACTORY_ID = 100
MOCK_USER_ID = 500

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # Seed mock factory and user
    db = TestingSessionLocal()
    
    # Factory 1
    factory1 = Factory(
        id=MOCK_FACTORY_ID,
        name="Telegram Binding Test Factory",
        subscription_status="active"
    )
    db.add(factory1)
    db.flush()

    # User 1
    user1 = User(
        id=MOCK_USER_ID,
        factory_id=MOCK_FACTORY_ID,
        username="telegram-owner",
        full_name="Telegram Owner",
        password_hash="mock_hash",
        role="Owner",
        is_active=True
    )
    db.add(user1)
    
    # Factory 2 (for duplicate bind checks)
    factory2 = Factory(
        id=200,
        name="Telegram Another Factory",
        subscription_status="active"
    )
    db.add(factory2)
    db.flush()

    # User 2
    user2 = User(
        id=600,
        factory_id=200,
        username="another-owner",
        full_name="Another Owner",
        password_hash="mock_hash",
        role="Owner",
        is_active=True
    )
    db.add(user2)
    
    db.commit()
    db.close()

def build_client(current_user_id=MOCK_USER_ID):
    db = TestingSessionLocal()
    mock_user = db.query(User).filter(User.id == current_user_id).first()
    db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: mock_user
    
    # Patch check_permissions if needed since fastapi dependency check works on it
    from auth import check_permissions
    app.dependency_overrides[check_permissions(["Owner", "Sub-Owner"])] = lambda: mock_user

    # Ensure Client accepts app kwarg if needed
    import inspect
    import httpx
    if "app" not in inspect.signature(httpx.Client.__init__).parameters:
        original_init = httpx.Client.__init__
        def patched_init(self, *args, app=None, **kwargs):
            return original_init(self, *args, **kwargs)
        httpx.Client.__init__ = patched_init

    return TestClient(app)

def test_telegram_connect_success():
    client = build_client()
    response = client.post("/api/telegram/connect")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "code" in data
    assert "expires_at" in data
    assert len(data["code"]) == 6

    # Verify saved in db
    db = TestingSessionLocal()
    user = db.query(User).filter(User.id == MOCK_USER_ID).first()
    assert user.telegram_binding_code == data["code"]
    assert user.telegram_binding_expiry is not None
    db.close()

def test_telegram_verify_code_success(monkeypatch):
    # Setup mock n8n API key env variable
    monkeypatch.setenv("N8N_API_KEY", "dev-n8n-local-secret")

    client = build_client()
    
    # 1. Connect
    response = client.post("/api/telegram/connect")
    assert response.status_code == status.HTTP_200_OK
    code = response.json()["code"]

    # 2. Verify with correct code and n8n header
    headers = {"X-N8N-API-KEY": "dev-n8n-local-secret"}
    verify_payload = {"code": code, "chat_id": "123456789"}
    verify_response = client.post("/api/telegram/verify-code", json=verify_payload, headers=headers)
    assert verify_response.status_code == status.HTTP_200_OK
    assert verify_response.json()["status"] == "success"

    # 3. Check db updates
    db = TestingSessionLocal()
    user = db.query(User).filter(User.id == MOCK_USER_ID).first()
    assert user.telegram_chat_id == "123456789"
    assert user.telegram_id == "123456789"
    assert user.telegram_binding_code is None
    assert user.telegram_binding_expiry is None

    factory = db.query(Factory).filter(Factory.id == MOCK_FACTORY_ID).first()
    assert factory.telegram_chat_id == "123456789"
    db.close()

def test_telegram_verify_code_expired(monkeypatch):
    monkeypatch.setenv("N8N_API_KEY", "dev-n8n-local-secret")
    client = build_client()
    
    # 1. Connect
    response = client.post("/api/telegram/connect")
    assert response.status_code == status.HTTP_200_OK
    code = response.json()["code"]

    # 2. Manually expire the code in DB
    db = TestingSessionLocal()
    user = db.query(User).filter(User.id == MOCK_USER_ID).first()
    user.telegram_binding_expiry = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    db.close()

    # 3. Verify
    headers = {"X-N8N-API-KEY": "dev-n8n-local-secret"}
    verify_payload = {"code": code, "chat_id": "123456789"}
    verify_response = client.post("/api/telegram/verify-code", json=verify_payload, headers=headers)
    assert verify_response.status_code == status.HTTP_400_BAD_REQUEST
    assert "expired" in verify_response.json()["detail"].lower()

def test_telegram_verify_code_wrong(monkeypatch):
    monkeypatch.setenv("N8N_API_KEY", "dev-n8n-local-secret")
    client = build_client()
    
    # Verify with non-existent code
    headers = {"X-N8N-API-KEY": "dev-n8n-local-secret"}
    verify_payload = {"code": "WRONGG", "chat_id": "123456789"}
    verify_response = client.post("/api/telegram/verify-code", json=verify_payload, headers=headers)
    assert verify_response.status_code == status.HTTP_400_BAD_REQUEST
    assert "invalid" in verify_response.json()["detail"].lower()

def test_telegram_verify_code_duplicate(monkeypatch):
    monkeypatch.setenv("N8N_API_KEY", "dev-n8n-local-secret")
    headers = {"X-N8N-API-KEY": "dev-n8n-local-secret"}
    
    client1 = build_client(current_user_id=MOCK_USER_ID)
    client2 = build_client(current_user_id=600)

    # 1. User 1 connects and binds chat_id "123456789"
    resp1 = client1.post("/api/telegram/connect")
    code1 = resp1.json()["code"]
    verify_resp1 = client1.post("/api/telegram/verify-code", json={"code": code1, "chat_id": "123456789"}, headers=headers)
    assert verify_resp1.status_code == status.HTTP_200_OK

    # 2. User 2 connects and attempts to bind SAME chat_id "123456789"
    resp2 = client2.post("/api/telegram/connect")
    code2 = resp2.json()["code"]
    verify_resp2 = client2.post("/api/telegram/verify-code", json={"code": code2, "chat_id": "123456789"}, headers=headers)
    assert verify_resp2.status_code == status.HTTP_400_BAD_REQUEST
    assert "already bound" in verify_resp2.json()["detail"].lower()

def test_telegram_disconnect(monkeypatch):
    monkeypatch.setenv("N8N_API_KEY", "dev-n8n-local-secret")
    client = build_client()

    # 1. Bind
    resp = client.post("/api/telegram/connect")
    code = resp.json()["code"]
    headers = {"X-N8N-API-KEY": "dev-n8n-local-secret"}
    client.post("/api/telegram/verify-code", json={"code": code, "chat_id": "123456789"}, headers=headers)

    # Verify bound in DB
    db = TestingSessionLocal()
    user = db.query(User).filter(User.id == MOCK_USER_ID).first()
    assert user.telegram_chat_id == "123456789"
    db.close()

    # 2. Disconnect
    disc_resp = client.post("/api/telegram/disconnect")
    assert disc_resp.status_code == status.HTTP_200_OK
    assert disc_resp.json()["status"] == "disconnected"

    # Verify cleared in DB
    db = TestingSessionLocal()
    user = db.query(User).filter(User.id == MOCK_USER_ID).first()
    assert user.telegram_chat_id is None
    assert user.telegram_id is None
    
    factory = db.query(Factory).filter(Factory.id == MOCK_FACTORY_ID).first()
    assert factory.telegram_chat_id is None
    db.close()

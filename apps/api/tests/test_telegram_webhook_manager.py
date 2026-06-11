import pytest
from unittest.mock import patch, MagicMock
import os
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from db import Base, get_db
from models import Factory, User
from auth import get_current_user, get_current_active_user, check_permissions
from routers.integrations import router

@pytest.fixture
def test_db(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-encryption-key-that-is-long-enough-for-jwt")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    
    # Create test factory
    factory = Factory(
        id=1,
        name="Test Factory",
        subscription_status="active",
        telegram_bot_token="123456:test-token",
        telegram_chat_id="12345"
    )
    db.add(factory)
    db.flush()
    
    # Create test users
    owner = User(id=1, factory_id=1, username="owner", role="Owner", password_hash="hash", is_active=True)
    supervisor = User(id=2, factory_id=1, username="supervisor", role="Supervisor", password_hash="hash", is_active=True)
    super_admin = User(id=3, factory_id=1, username="super_admin", role="Owner", password_hash="hash", is_active=True)
    
    db.add_all([owner, supervisor, super_admin])
    db.commit()
    db.close()
    return SessionLocal

def _create_client_for_user(user_id: int, SessionLocal):
    app = FastAPI()
    app.include_router(router)
    
    def override_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
            
    def override_user():
        session = SessionLocal()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            session.expunge(user)
            if user_id == 3:
                user.role = "Super Admin"
            return user
        finally:
            session.close()
            
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_current_active_user] = override_user
    
    import inspect
    import httpx
    if "app" not in inspect.signature(httpx.Client.__init__).parameters:
        original_init = httpx.Client.__init__
        def patched_init(self, *args, app=None, **kwargs):
            return original_init(self, *args, **kwargs)
        httpx.Client.__init__ = patched_init
        
    return TestClient(app)

@pytest.fixture
def owner_client(test_db):
    return _create_client_for_user(1, test_db)

@pytest.fixture
def supervisor_client(test_db):
    return _create_client_for_user(2, test_db)

@pytest.fixture
def admin_client(test_db):
    return _create_client_for_user(3, test_db)

@pytest.fixture
def super_admin_client(test_db):
    return _create_client_for_user(3, test_db)


@pytest.fixture
def mock_httpx_post(monkeypatch):
    """Mock httpx.post for testing webhook registration."""
    async def mock_post(*args, **kwargs):
        # Extract URL safely, skipping self client arg if present
        url = ""
        if len(args) > 1 and isinstance(args[1], str):
            url = args[1]
        elif len(args) > 0 and isinstance(args[0], str):
            url = args[0]
        else:
            url = kwargs.get('url', '')
        
        if 'getWebhookInfo' in url:
            # Return configured webhook
            return MagicMock(
                json=lambda: {
                    "ok": True,
                    "result": {
                        "url": "https://munshiai.co.in/api/integrations/telegram/webhook",
                        "pending_update_count": 0,
                        "last_error_date": None,
                        "last_error_message": "",
                    }
                }
            )
        elif 'setWebhook' in url:
            # Return successful registration
            return MagicMock(
                json=lambda: {
                    "ok": True,
                    "result": True
                }
            )
        return MagicMock(json=lambda: {"ok": False, "description": "Unknown"})
    
    import httpx
    monkeypatch.setattr(httpx.AsyncClient, 'get', mock_post)
    monkeypatch.setattr(httpx.AsyncClient, 'post', mock_post)


def test_auto_register_webhook_env_vars_configured(monkeypatch, mock_httpx_post):
    """Test that webhook gets registered when env vars are configured."""
    from services.telegram_webhook_manager import get_webhook_config, register_webhook
    
    # Set up env vars
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "TestBot")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    monkeypatch.setenv("PUBLIC_API_ORIGIN", "https://munshiai.co.in")
    
    token, username, secret, expected_url = get_webhook_config()
    
    assert token == "123456:test-token"
    assert username == "TestBot"
    assert secret == "webhook-secret"
    assert expected_url == "https://munshiai.co.in/api/integrations/telegram/webhook"


def test_register_webhook_success(monkeypatch, mock_httpx_post):
    """Test successful webhook registration."""
    from services.telegram_webhook_manager import register_webhook
    
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    
    success, message = register_webhook()
    
    assert success is True
    assert "successfully" in message.lower()


def test_register_webhook_missing_token(monkeypatch):
    """Test webhook registration fails without token."""
    from services.telegram_webhook_manager import register_webhook, get_webhook_config
    
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    # Don't set TELEGRAM_BOT_TOKEN
    
    token, username, secret, expected_url = get_webhook_config()
    
    assert not token
    assert username == "MunshiHermesAi_Bot"
    assert secret == "webhook-secret"
    
    success, message = register_webhook()
    assert success is False
    assert "not configured" in message.lower()


def test_get_webhook_status_not_configured(monkeypatch):
    """Test webhook status when not configured."""
    from services.telegram_webhook_manager import get_webhook_status
    
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    
    status = get_webhook_status()
    
    assert status["configured"] is False
    assert status["last_error_message"] == "TELEGRAM_BOT_TOKEN not configured"
    assert status["expected_url"] == "https://munshiai.co.in/api/integrations/telegram/webhook"


def test_endpoint_register_webhook_success(admin_client, monkeypatch, mock_httpx_post):
    """Test Super Admin can register webhook via endpoint."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    
    response = admin_client.post(
        "/api/integrations/telegram/register-webhook",
        json={"use_default": True}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "successfully" in data["message"].lower()
    assert "webhook" in data["webhook_url"]


def test_endpoint_register_webhook_missing_creds(admin_client, monkeypatch):
    """Test Super Admin gets error when missing credentials."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    
    response = admin_client.post(
        "/api/integrations/telegram/register-webhook",
        json={"use_default": True}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "not configured" in data["message"].lower()


def test_endpoint_register_webhook_supervisor_rejected(
    supervisor_client, monkeypatch
):
    """Test regular users cannot register webhook."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    
    response = supervisor_client.post(
        "/api/integrations/telegram/register-webhook",
        json={"use_default": True}
    )
    
    assert response.status_code == 403


def test_webhook_configured_in_status_endpoint(owner_client, monkeypatch):
    """Test webhook configuration status appears in user status."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    
    response = owner_client.get("/api/integrations/telegram/status")
    
    assert response.status_code == 200
    data = response.json()
    assert "webhook_configured" in data
    assert data["webhook_configured"] is True


def test_diagnostic_endpoint_includes_webhook_info(
    super_admin_client, monkeypatch, mock_httpx_post
):
    """Test diagnostics endpoint returns webhook configuration info."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    
    response = super_admin_client.get("/api/integrations/telegram/diagnostics")
    
    assert response.status_code == 200
    data = response.json()
    
    # Check required fields
    required_fields = [
        "bot_token_configured",
        "webhook_secret_configured",
        "expected_webhook_url",
        "webhook_configured",
        "webhook_url",
        "pending_update_count",
        "last_error_message",
    ]
    
    for field in required_fields:
        assert field in data, f"Missing field: {field}"
    
    # Check values
    assert data["bot_token_configured"] is True
    assert data["webhook_secret_configured"] is True
    assert data["webhook_configured"] is True
    assert "bot" in data["telegram_bot_username"].lower()

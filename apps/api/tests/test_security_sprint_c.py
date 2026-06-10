from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from main import _rate_limit_store, app
from routers.integrations import enforce_webhook_rate_limit


from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from db import Base, get_db

# Test DB configuration
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


from routers.super_admin import _super_admin_failed_attempts, _super_admin_lockouts


@pytest.fixture(autouse=True)
def clear_rate_limits(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _rate_limit_store.clear()
    _super_admin_failed_attempts.clear()
    _super_admin_lockouts.clear()
    yield
    app.dependency_overrides.pop(get_db, None)
    _rate_limit_store.clear()
    _super_admin_failed_attempts.clear()
    _super_admin_lockouts.clear()


def test_auth_uses_structured_logging_without_debug_prints():
    auth_source = (Path(__file__).resolve().parents[1] / "auth.py").read_text(encoding="utf-8")

    assert "AUTH DEBUG" not in auth_source
    assert "print(" not in auth_source
    assert "logging.getLogger(__name__)" in auth_source


def test_super_admin_login_allows_five_requests_then_returns_429():
    client = TestClient(app)
    payload = {"email": "invalid@example.com", "password": "invalid-password"}

    for _ in range(5):
        assert client.post("/api/super-admin/login", json=payload).status_code != 429

    response = client.post("/api/super-admin/login", json=payload)

    assert response.status_code == 429
    assert "too many login attempts" in response.json()["detail"].lower()


def test_n8n_webhook_allows_sixty_requests_then_returns_429():
    client = TestClient(app)
    payload = {"factory_id": 1, "message": "health"}

    for _ in range(60):
        assert client.post("/api/n8n/test", json=payload).status_code == 200

    assert client.post("/api/n8n/test", json=payload).status_code == 429


def test_telegram_webhook_allows_sixty_requests_then_returns_429(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-webhook-secret")
    client = TestClient(app)
    headers = {"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret"}
    payload = {"update_id": 1}

    for _ in range(60):
        assert client.post(
            "/api/integrations/telegram/webhook",
            headers=headers,
            json=payload,
        ).status_code == 200

    assert client.post(
        "/api/integrations/telegram/webhook",
        headers=headers,
        json=payload,
    ).status_code == 429


def test_ai_webhook_has_independent_sixty_request_bucket():
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/ai/n8n-webhook",
            "headers": [],
            "client": ("203.0.113.10", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )

    for _ in range(60):
        enforce_webhook_rate_limit(request, "ai_n8n")

    with pytest.raises(HTTPException) as exc_info:
        enforce_webhook_rate_limit(request, "ai_n8n")

    assert exc_info.value.status_code == 429

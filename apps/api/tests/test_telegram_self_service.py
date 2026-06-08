import inspect
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import get_current_user
from db import Base, get_db
from models import Factory, TelegramConnectToken, User
from routers.integrations import router


if "app" not in inspect.signature(httpx.Client.__init__).parameters:
    original_init = httpx.Client.__init__

    def patched_init(self, *args, app=None, **kwargs):
        return original_init(self, *args, **kwargs)

    httpx.Client.__init__ = patched_init


@pytest.fixture()
def telegram_app(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-bot-token")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "MunshiHermesAi_Bot")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "telegram-test-encryption-key-that-is-long-enough")

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add_all([
        Factory(id=1, name="Factory A", subscription_status="active"),
        Factory(id=2, name="Factory B", subscription_status="active"),
    ])
    db.flush()
    db.add_all([
        User(id=11, factory_id=1, username="owner-a", password_hash="x", role="Owner", is_active=True),
        User(id=22, factory_id=2, username="owner-b", password_hash="x", role="Owner", is_active=True),
    ])
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(router)
    active_user_id = {"value": 11}

    def override_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_user():
        session = SessionLocal()
        try:
            user = session.query(User).filter(User.id == active_user_id["value"]).one()
            session.expunge(user)
            return user
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    client = TestClient(app)
    try:
        yield client, SessionLocal, active_user_id
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def create_link(client: TestClient) -> tuple[str, dict]:
    response = client.post("/api/integrations/telegram/connect-link")
    assert response.status_code == 200, response.text
    payload = response.json()
    raw_token = parse_qs(urlparse(payload["telegram_url"]).query)["start"][0]
    return raw_token, payload


def webhook(client: TestClient, raw_token: str, chat_id: str = "10001", username: str = "factory_owner"):
    return client.post(
        "/api/integrations/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
        json={
            "update_id": 1,
            "message": {
                "text": f"/start {raw_token}",
                "chat": {"id": chat_id},
                "from": {"username": username},
            },
        },
    )


def test_connect_link_generation_is_opaque_and_factory_bound(telegram_app):
    client, SessionLocal, _ = telegram_app
    raw_token, payload = create_link(client)

    assert payload["status"] == "pending"
    assert "factory_id" not in payload["telegram_url"]
    assert "owner_id" not in payload["telegram_url"]
    assert len(raw_token) >= 40

    db = SessionLocal()
    try:
        token = db.query(TelegramConnectToken).one()
        assert token.factory_id == 1
        assert token.owner_id == 11
        assert token.token_hash != raw_token
        assert token.expires_at is not None
    finally:
        db.close()


def test_invalid_and_expired_tokens_are_rejected(telegram_app):
    client, SessionLocal, _ = telegram_app
    invalid = webhook(client, "not-a-real-token")
    assert invalid.status_code == 200
    assert invalid.json()["status"] == "invalid"

    raw_token, _ = create_link(client)
    db = SessionLocal()
    token = db.query(TelegramConnectToken).one()
    token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    db.close()

    expired = webhook(client, raw_token)
    assert expired.status_code == 200
    assert expired.json()["status"] == "expired"


def test_successful_bind_and_token_is_one_time(telegram_app):
    client, SessionLocal, _ = telegram_app
    raw_token, _ = create_link(client)
    with patch("routers.integrations.send_telegram_message") as sender:
        response = webhook(client, raw_token)
        replay = webhook(client, raw_token)

    assert response.json()["status"] == "connected"
    assert replay.json()["status"] == "invalid"
    sender.assert_called_once()

    db = SessionLocal()
    try:
        factory = db.query(Factory).filter(Factory.id == 1).one()
        owner = db.query(User).filter(User.id == 11).one()
        token = db.query(TelegramConnectToken).one()
        assert factory.telegram_chat_id == "10001"
        assert factory.telegram_username == "factory_owner"
        assert factory.telegram_connected_at is not None
        assert owner.telegram_chat_id == "10001"
        assert token.used_at is not None
    finally:
        db.close()


def test_chat_id_cannot_cross_factory_boundary(telegram_app):
    client, SessionLocal, active_user_id = telegram_app
    first_token, _ = create_link(client)
    with patch("routers.integrations.send_telegram_message"):
        assert webhook(client, first_token, chat_id="shared-chat").json()["status"] == "connected"

    active_user_id["value"] = 22
    second_token, _ = create_link(client)
    response = webhook(client, second_token, chat_id="shared-chat")
    assert response.json()["status"] == "conflict"

    db = SessionLocal()
    try:
        assert db.query(Factory).filter(Factory.id == 1).one().telegram_chat_id == "shared-chat"
        assert db.query(Factory).filter(Factory.id == 2).one().telegram_chat_id is None
    finally:
        db.close()


def test_message_requires_connection_and_disconnect_is_factory_scoped(telegram_app):
    client, SessionLocal, _ = telegram_app
    assert client.post("/api/integrations/telegram/test-message").status_code == 409

    db = SessionLocal()
    factory_a = db.query(Factory).filter(Factory.id == 1).one()
    factory_b = db.query(Factory).filter(Factory.id == 2).one()
    owner_a = db.query(User).filter(User.id == 11).one()
    factory_a.telegram_chat_id = "chat-a"
    factory_a.telegram_bot_token = "legacy-token-a"
    owner_a.telegram_chat_id = "chat-a"
    owner_a.telegram_id = "chat-a"
    factory_b.telegram_chat_id = "chat-b"
    factory_b.telegram_bot_token = "legacy-token-b"
    db.commit()
    db.close()

    with patch("routers.integrations.send_telegram_message") as sender:
        sent = client.post("/api/integrations/telegram/test-message")
    assert sent.status_code == 200
    sender.assert_called_once()

    disconnected = client.post("/api/integrations/telegram/disconnect")
    assert disconnected.status_code == 200

    db = SessionLocal()
    try:
        assert db.query(Factory).filter(Factory.id == 1).one().telegram_chat_id is None
        assert db.query(Factory).filter(Factory.id == 2).one().telegram_chat_id == "chat-b"
    finally:
        db.close()

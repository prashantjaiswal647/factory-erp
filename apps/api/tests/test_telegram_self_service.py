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
from models import Factory, TelegramActionSession, TelegramConnectToken, TelegramUserBinding, User
from routers.integrations import router
from services.telegram_delivery import TelegramDeliveryError


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
        Factory(id=1, name="Factory A", subscription_status="active", telegram_bot_token="123456:test-bot-token"),
        Factory(id=2, name="Factory B", subscription_status="active", telegram_bot_token="123456:test-bot-token"),
    ])
    db.flush()
    db.add_all([
        User(id=11, factory_id=1, username="owner-a", password_hash="x", role="Owner", is_active=True),
        User(id=12, factory_id=1, username="sub-owner-a", password_hash="x", role="Sub-Owner", is_active=True),
        User(id=13, factory_id=1, username="supervisor-a", password_hash="x", role="Supervisor", is_active=True),
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


def menu_webhook(client: TestClient, chat_id: str):
    return client.post(
        "/api/integrations/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
        json={"update_id": 2, "message": {"text": "/menu", "chat": {"id": chat_id}}},
    )


def callback_webhook(client: TestClient, chat_id: str, callback_data: str):
    return client.post(
        "/api/integrations/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
        json={
            "update_id": 3,
            "callback_query": {
                "id": "callback-1",
                "data": callback_data,
                "message": {"chat": {"id": chat_id}},
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
    # Two outgoing messages: the welcome + the auto test message.
    assert sender.call_count == 2
    welcome_call, test_call = sender.call_args_list
    assert "Factory Details" in welcome_call.args[1]
    assert welcome_call.kwargs["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "menu:view"
    assert "test message successful" in test_call.args[1]

    db = SessionLocal()
    try:
        factory = db.query(Factory).filter(Factory.id == 1).one()
        owner = db.query(User).filter(User.id == 11).one()
        token = db.query(TelegramConnectToken).one()
        assert factory.telegram_chat_id == "10001"
        assert factory.telegram_username == "factory_owner"
        assert factory.telegram_connected_at is not None
        assert owner.telegram_chat_id == "10001"
        binding = db.query(TelegramUserBinding).filter(TelegramUserBinding.user_id == 11).one()
        assert binding.role == "Owner"
        assert binding.telegram_chat_id == "10001"
        assert binding.welcome_sent_at is not None
        assert binding.last_message_status == "sent"
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


def test_owner_and_sub_owner_bind_separate_chat_ids_and_status_is_user_scoped(telegram_app):
    client, SessionLocal, active_user_id = telegram_app
    owner_token, _ = create_link(client)
    with patch("routers.integrations.send_telegram_message"):
        assert webhook(client, owner_token, chat_id="owner-chat", username="owner_user").json()["status"] == "connected"

    active_user_id["value"] = 12
    sub_owner_token, _ = create_link(client)
    with patch("routers.integrations.send_telegram_message"):
        assert webhook(client, sub_owner_token, chat_id="sub-owner-chat", username="sub_owner_user").json()["status"] == "connected"

    sub_status = client.get("/api/integrations/telegram/status")
    assert sub_status.status_code == 200
    assert sub_status.json()["role"] == "Sub-Owner"
    assert sub_status.json()["telegram_username"] == "sub_owner_user"

    active_user_id["value"] = 11
    owner_status = client.get("/api/integrations/telegram/status")
    assert owner_status.json()["role"] == "Owner"
    assert owner_status.json()["telegram_username"] == "owner_user"

    db = SessionLocal()
    try:
        bindings = db.query(TelegramUserBinding).filter(TelegramUserBinding.factory_id == 1).all()
        assert {(row.user_id, row.telegram_chat_id) for row in bindings} == {
            (11, "owner-chat"),
            (12, "sub-owner-chat"),
        }
        assert db.query(Factory).filter(Factory.id == 1).one().telegram_chat_id == "owner-chat"
    finally:
        db.close()


def test_supervisor_cannot_access_user_telegram_integration(telegram_app):
    client, _, active_user_id = telegram_app
    active_user_id["value"] = 13

    assert client.post("/api/integrations/telegram/connect-link").status_code == 403
    assert client.get("/api/integrations/telegram/status").status_code == 403
    assert client.post("/api/integrations/telegram/test-message").status_code == 403
    assert client.post("/api/integrations/telegram/disconnect").status_code == 403


def test_role_menu_and_callbacks_resolve_user_binding(telegram_app):
    client, _, active_user_id = telegram_app
    owner_token, _ = create_link(client)
    with patch("routers.integrations.send_telegram_message"):
        webhook(client, owner_token, chat_id="owner-menu")

    with patch("routers.integrations.send_telegram_message") as sender:
        menu = menu_webhook(client, "owner-menu")
        callback = callback_webhook(client, "owner-menu", "telegram_test_message")
    assert menu.json()["status"] == "ok"
    assert callback.json()["status"] == "ok"
    assert "test successful" in callback.json()["message"]
    assert sender.call_args.kwargs["reply_markup"]["inline_keyboard"]

    active_user_id["value"] = 12
    sub_token, _ = create_link(client)
    with patch("routers.integrations.send_telegram_message"):
        webhook(client, sub_token, chat_id="sub-menu")
    forbidden = callback_webhook(client, "sub-menu", "owner_staff_actions")
    assert forbidden.json()["status"] == "invalid"


def test_nested_menu_callbacks_and_back_navigation(telegram_app):
    client, SessionLocal, _ = telegram_app
    owner_token, _ = create_link(client)
    with patch("routers.integrations.send_telegram_message"):
        webhook(client, owner_token, chat_id="nested-menu")

    with patch("routers.integrations.send_telegram_message") as sender:
        menu = menu_webhook(client, "nested-menu")
        view = callback_webhook(client, "nested-menu", "menu:view")
        back = callback_webhook(client, "nested-menu", "menu:main")

    assert menu.json()["status"] == "ok"
    assert view.json()["status"] == "ok"
    assert "Read-only" in view.json()["message"]
    assert back.json()["message"] == "Munshi AI main menu"
    view_keyboard = sender.call_args_list[1].kwargs["reply_markup"]["inline_keyboard"]
    assert [button["callback_data"] for row in view_keyboard for button in row] == [
        "view:outstanding", "view:production", "view:inventory",
        "view:payments", "view:expenses", "view:attendance", "menu:main",
    ]
    main_keyboard = sender.call_args.kwargs["reply_markup"]["inline_keyboard"]
    assert [button["callback_data"] for row in main_keyboard for button in row] == [
        "menu:view", "menu:action", "menu:alerts", "menu:settings",
    ]

    db = SessionLocal()
    try:
        session = db.query(TelegramActionSession).filter(
            TelegramActionSession.factory_id == 1,
            TelegramActionSession.chat_id == "nested-menu",
            TelegramActionSession.action == "menu_navigation",
            TelegramActionSession.status == "pending",
        ).one()
        assert session.step == "main"
    finally:
        db.close()


def test_action_placeholder_requires_confirmation_and_never_writes_business_data(telegram_app):
    client, SessionLocal, _ = telegram_app
    owner_token, _ = create_link(client)
    with patch("routers.integrations.send_telegram_message"):
        webhook(client, owner_token, chat_id="action-menu")

    with patch("routers.integrations.send_telegram_message") as sender:
        menu = callback_webhook(client, "action-menu", "menu:action")
        action = callback_webhook(client, "action-menu", "action:payment")
        save = callback_webhook(client, "action-menu", "confirm:save")
        cancel = callback_webhook(client, "action-menu", "confirm:cancel")

    action_keyboard = sender.call_args_list[0].kwargs["reply_markup"]["inline_keyboard"]
    assert [button["callback_data"] for row in action_keyboard for button in row] == [
        "action:payment", "action:production", "action:expense",
        "action:inventory", "action:attendance", "action:invoice", "menu:main",
    ]
    assert menu.json()["status"] == "ok"
    assert action.json()["status"] == "ok"
    assert "database update" in action.json()["message"]
    confirm_keyboard = sender.call_args_list[1].kwargs["reply_markup"]["inline_keyboard"]
    assert {button["callback_data"] for row in confirm_keyboard for button in row} == {
        "confirm:save", "confirm:edit", "confirm:cancel",
    }
    assert "database update disabled" in save.json()["message"]
    assert "Koi data save nahi hua" in cancel.json()["message"]

    db = SessionLocal()
    try:
        sessions = db.query(TelegramActionSession).filter(
            TelegramActionSession.factory_id == 1,
            TelegramActionSession.chat_id == "action-menu",
            TelegramActionSession.action == "menu_action",
        ).all()
        assert len(sessions) == 1
        assert sessions[0].status == "cancelled"
    finally:
        db.close()


def test_unknown_chat_and_welcome_failure_are_safe(telegram_app):
    client, SessionLocal, _ = telegram_app
    assert menu_webhook(client, "unknown-chat").json()["status"] == "invalid"
    assert callback_webhook(client, "unknown-chat", "telegram_test_message").json()["status"] == "invalid"

    raw_token, _ = create_link(client)
    with patch("routers.integrations.send_telegram_message", side_effect=TelegramDeliveryError("delivery failed")):
        response = webhook(client, raw_token, chat_id="failed-welcome")
    assert response.json()["status"] == "connected"

    db = SessionLocal()
    try:
        binding = db.query(TelegramUserBinding).filter(TelegramUserBinding.telegram_chat_id == "failed-welcome").one()
        assert binding.is_active is True
        assert binding.welcome_sent_at is None
        assert binding.last_message_status == "failed"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Z2.7A: 6-digit code binding flow + connect-code endpoint
# ---------------------------------------------------------------------------


def _create_code(client: TestClient) -> str:
    response = client.post("/api/integrations/telegram/connect-code")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["code"]) == 6
    assert payload["code"].isalnum() and payload["code"].isupper()
    assert payload["bot_username"] == "MunshiHermesAi_Bot"
    return payload["code"]


def _bind_code_webhook(client: TestClient, code: str, chat_id: str = "20001", username: str = "code_owner", first_name: str = "Owner"):
    return client.post(
        "/api/integrations/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
        json={
            "update_id": 100,
            "message": {
                "text": f"/start bind_{code}",
                "chat": {"id": chat_id},
                "from": {"username": username, "first_name": first_name},
            },
        },
    )


def test_connect_code_endpoint_returns_deep_link_and_code(telegram_app):
    client, SessionLocal, _ = telegram_app
    response = client.post("/api/integrations/telegram/connect-code")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["code"]) == 6
    assert payload["code"].isalnum() and payload["code"].isupper()
    assert payload["deep_link"].startswith("https://t.me/")
    assert payload["deep_link"].endswith(f"?start=bind_{payload['code']}")
    assert payload["bot_username"] == "MunshiHermesAi_Bot"
    assert payload["expires_at"]

    db = SessionLocal()
    try:
        owner = db.query(User).filter(User.id == 11).one()
        assert owner.telegram_binding_code == payload["code"]
        assert owner.telegram_binding_expiry is not None
    finally:
        db.close()


def test_connect_code_endpoint_rejects_supervisor(telegram_app):
    client, _, active_user_id = telegram_app
    active_user_id["value"] = 13
    response = client.post("/api/integrations/telegram/connect-code")
    assert response.status_code == 403


def test_connect_code_overwrites_previous_unused_code(telegram_app):
    client, SessionLocal, _ = telegram_app
    first = client.post("/api/integrations/telegram/connect-code").json()["code"]
    second = client.post("/api/integrations/telegram/connect-code").json()["code"]
    assert first != second
    db = SessionLocal()
    try:
        owner = db.query(User).filter(User.id == 11).one()
        assert owner.telegram_binding_code == second
    finally:
        db.close()


def test_bind_code_flow_creates_binding_and_sends_welcome_then_test(telegram_app):
    client, SessionLocal, _ = telegram_app
    code = _create_code(client)
    with patch("routers.integrations.send_telegram_message") as sender:
        response = _bind_code_webhook(client, code, chat_id="code-chat", username="code_owner", first_name="Owner")
    assert response.json()["status"] == "connected"
    # Welcome + auto test message both sent.
    assert sender.call_count == 2
    welcome_call, test_call = sender.call_args_list
    assert "Factory Details" in welcome_call.args[1]
    assert "test message successful" in test_call.args[1]

    db = SessionLocal()
    try:
        owner = db.query(User).filter(User.id == 11).one()
        factory = db.query(Factory).filter(Factory.id == 1).one()
        binding = db.query(TelegramUserBinding).filter(TelegramUserBinding.user_id == 11).one()
        assert binding.telegram_chat_id == "code-chat"
        assert binding.telegram_username == "code_owner"
        assert binding.telegram_first_name == "Owner"
        assert binding.welcome_sent_at is not None
        assert binding.last_message_status == "sent"
        assert owner.telegram_chat_id == "code-chat"
        assert owner.telegram_binding_code is None
        assert owner.telegram_binding_expiry is None
        assert factory.telegram_chat_id == "code-chat"
        assert factory.telegram_username == "code_owner"
    finally:
        db.close()


def test_bind_code_flow_expired_code_is_rejected(telegram_app):
    client, SessionLocal, _ = telegram_app
    code = _create_code(client)
    db = SessionLocal()
    owner = db.query(User).filter(User.id == 11).one()
    owner.telegram_binding_expiry = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    db.close()

    response = _bind_code_webhook(client, code)
    assert response.json()["status"] == "expired"

    db = SessionLocal()
    try:
        owner = db.query(User).filter(User.id == 11).one()
        assert owner.telegram_binding_code is None
        assert owner.telegram_binding_expiry is None
        assert db.query(TelegramUserBinding).count() == 0
    finally:
        db.close()


def test_bind_code_flow_unknown_code_is_rejected(telegram_app):
    client, _, _ = telegram_app
    response = _bind_code_webhook(client, "ZZZZZZ")
    assert response.json()["status"] == "invalid"


def test_bind_code_flow_replay_after_success_is_safe(telegram_app):
    client, SessionLocal, _ = telegram_app
    code = _create_code(client)
    with patch("routers.integrations.send_telegram_message"):
        first = _bind_code_webhook(client, code)
    assert first.json()["status"] == "connected"

    # The code is one-time: replaying the same code must fail because the
    # user's telegram_binding_code was cleared on success.
    with patch("routers.integrations.send_telegram_message") as sender:
        replay = _bind_code_webhook(client, code)
    assert replay.json()["status"] == "invalid"
    # No new binding written, no welcome / test sent.
    assert sender.call_count == 0

    db = SessionLocal()
    try:
        bindings = db.query(TelegramUserBinding).filter(TelegramUserBinding.user_id == 11).all()
        assert len(bindings) == 1
    finally:
        db.close()


def test_bind_code_flow_cross_factory_chat_id_rejected(telegram_app):
    client, SessionLocal, active_user_id = telegram_app
    _create_code(client)
    with patch("routers.integrations.send_telegram_message"):
        first = _bind_code_webhook(client, _create_code(client), chat_id="shared-code-chat")
    assert first.json()["status"] == "connected"

    active_user_id["value"] = 22
    _create_code(client)
    second = _bind_code_webhook(client, _create_code(client), chat_id="shared-code-chat")
    assert second.json()["status"] == "conflict"

    db = SessionLocal()
    try:
        factory_b = db.query(Factory).filter(Factory.id == 2).one()
        owner_b = db.query(User).filter(User.id == 22).one()
        assert factory_b.telegram_chat_id is None
        assert owner_b.telegram_chat_id is None
        # factory_a still owns the chat_id
        factory_a = db.query(Factory).filter(Factory.id == 1).one()
        assert factory_a.telegram_chat_id == "shared-code-chat"
    finally:
        db.close()


def test_bind_code_flow_sub_owner_does_not_overwrite_factory_chat_id(telegram_app):
    client, SessionLocal, active_user_id = telegram_app
    active_user_id["value"] = 11
    owner_code = _create_code(client)
    with patch("routers.integrations.send_telegram_message"):
        assert _bind_code_webhook(client, owner_code, chat_id="owner-code-chat").json()["status"] == "connected"

    active_user_id["value"] = 12
    sub_code = _create_code(client)
    with patch("routers.integrations.send_telegram_message"):
        assert _bind_code_webhook(client, sub_code, chat_id="sub-code-chat").json()["status"] == "connected"

    db = SessionLocal()
    try:
        factory = db.query(Factory).filter(Factory.id == 1).one()
        # Factory chat_id must still belong to the Owner binding, not the Sub-Owner.
        assert factory.telegram_chat_id == "owner-code-chat"
        bindings = db.query(TelegramUserBinding).filter(TelegramUserBinding.factory_id == 1).all()
        assert {row.telegram_chat_id for row in bindings} == {"owner-code-chat", "sub-code-chat"}
    finally:
        db.close()


def test_bind_code_flow_welcome_failure_does_not_send_test_message(telegram_app):
    client, SessionLocal, _ = telegram_app
    code = _create_code(client)
    with patch(
        "routers.integrations.send_telegram_message",
        side_effect=TelegramDeliveryError("welcome boom"),
    ) as sender:
        response = _bind_code_webhook(client, code, chat_id="code-fail-chat")
    assert response.json()["status"] == "connected"
    # Welcome failed, so the auto test message must not be attempted.
    assert sender.call_count == 1

    db = SessionLocal()
    try:
        binding = db.query(TelegramUserBinding).filter(TelegramUserBinding.telegram_chat_id == "code-fail-chat").one()
        assert binding.welcome_sent_at is None
        assert binding.last_message_status == "failed"
    finally:
        db.close()


def test_unified_status_returns_first_name_and_connected_at(telegram_app):
    client, _, _ = telegram_app
    code = _create_code(client)
    with patch("routers.integrations.send_telegram_message"):
        _bind_code_webhook(client, code, chat_id="code-status-chat", username="status_owner", first_name="Status")
    response = client.get("/api/integrations/telegram/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["connected"] is True
    assert payload["telegram_username"] == "status_owner"
    assert payload["telegram_first_name"] == "Status"
    assert payload["connected_at"] is not None
    assert payload["last_message_status"] == "sent"


def test_bind_code_flow_is_case_insensitive(telegram_app):
    client, SessionLocal, _ = telegram_app
    code = _create_code(client)
    # The bot forwards exactly what the user types; lower-case should also work.
    response = client.post(
        "/api/integrations/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
        json={
            "update_id": 999,
            "message": {
                "text": f"/start bind_{code.lower()}",
                "chat": {"id": "code-lower-chat"},
                "from": {"username": "lower_owner", "first_name": "Lower"},
            },
        },
    )
    assert response.json()["status"] == "connected"

    db = SessionLocal()
    try:
        binding = db.query(TelegramUserBinding).filter(TelegramUserBinding.telegram_chat_id == "code-lower-chat").one()
        assert binding.telegram_username == "lower_owner"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# P4.10: Telegram Command Center Callback and Menu Tests
# ---------------------------------------------------------------------------


def test_owner_menu_contains_full_set_of_buttons(telegram_app):
    client, _, _ = telegram_app
    # Bind Owner (user_id = 11) to chat-owner-menu
    code = _create_code(client)
    with patch("routers.integrations.send_telegram_message") as sender:
        _bind_code_webhook(client, code, chat_id="chat-owner-menu")
    
    with patch("routers.integrations.send_telegram_message") as sender:
        # Trigger /menu
        response = menu_webhook(client, "chat-owner-menu")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        
        sender.assert_called_once()
        markup = sender.call_args.kwargs["reply_markup"]["inline_keyboard"]
    
    # Main menu intentionally contains only four top-level buttons.
    callbacks = [btn["callback_data"] for row in markup for btn in row]
    assert callbacks == ["menu:view", "menu:action", "menu:alerts", "menu:settings"]


def test_sub_owner_menu_contains_limited_set_of_buttons(telegram_app):
    client, _, active_user_id = telegram_app
    active_user_id["value"] = 12  # Sub-Owner (user_id = 12)
    
    code = _create_code(client)
    with patch("routers.integrations.send_telegram_message") as sender:
        _bind_code_webhook(client, code, chat_id="chat-sub-owner-menu")
        
    with patch("routers.integrations.send_telegram_message") as sender:
        response = menu_webhook(client, "chat-sub-owner-menu")
        assert response.status_code == 200
        
        sender.assert_called_once()
        markup = sender.call_args.kwargs["reply_markup"]["inline_keyboard"]
    
    callbacks = [btn["callback_data"] for row in markup for btn in row]
    
    assert callbacks == ["menu:view", "menu:action", "menu:alerts", "menu:settings"]


def test_unknown_chat_callback_is_rejected(telegram_app):
    client, _, _ = telegram_app
    response = callback_webhook(client, "nonexistent-chat-id", "owner_today_summary")
    assert response.status_code == 200
    assert response.json()["status"] == "invalid"
    assert "not connected" in response.json()["message"].lower() or "invalid connection" in response.json()["message"].lower() or "not active" in response.json()["message"].lower() or "does not exist" in response.json()["message"].lower()


def test_owner_collection_war_room_callback(telegram_app):
    client, SessionLocal, _ = telegram_app
    # Set up some outstanding bills for Factory A (factory_id = 1)
    db = SessionLocal()
    from models import Customer, OutstandingBill
    c1 = Customer(id=101, factory_id=1, name="Customer One")
    c2 = Customer(id=102, factory_id=1, name="Customer Two")
    db.add_all([c1, c2])
    db.flush()
    
    db.add_all([
        OutstandingBill(
            id=1,
            factory_id=1,
            customer_id=101,
            tracking_number="B-1",
            bill_date=datetime.now(timezone.utc).date() - timedelta(days=20),
            bill_amount=15000.00,
            balance_amount=15000.00,
            status="active"
        ),
        OutstandingBill(
            id=2,
            factory_id=1,
            customer_id=102,
            tracking_number="B-2",
            bill_date=datetime.now(timezone.utc).date() - timedelta(days=5),
            bill_amount=5000.00,
            balance_amount=5000.00,
            status="active"
        ),
    ])
    db.commit()
    db.close()

    # Bind Owner
    code = _create_code(client)
    with patch("routers.integrations.send_telegram_message"):
        _bind_code_webhook(client, code, chat_id="chat-cwr")

    # Send callback
    response = callback_webhook(client, "chat-cwr", "owner_collection_war_room")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    msg = data["message"]
    assert "Collection War Room" in msg
    assert "Total Outstanding" in msg
    assert "₹20,000.00" in msg
    assert "Overdue Amount" in msg
    assert "₹15,000.00" in msg  # > 15 days overdue
    assert "Customer One" in msg


def test_sub_owner_cannot_access_owner_callbacks(telegram_app):
    client, _, active_user_id = telegram_app
    
    # 1. Bind Owner
    active_user_id["value"] = 11
    owner_code = _create_code(client)
    with patch("routers.integrations.send_telegram_message"):
        _bind_code_webhook(client, owner_code, chat_id="owner-c-chat")
        
    # 2. Bind Sub-Owner
    active_user_id["value"] = 12
    sub_code = _create_code(client)
    with patch("routers.integrations.send_telegram_message"):
        _bind_code_webhook(client, sub_code, chat_id="sub-c-chat")
        
    # Sub-owner calling Owner CWR should be forbidden/rejected
    response = callback_webhook(client, "sub-c-chat", "owner_collection_war_room")
    assert response.status_code == 200
    assert response.json()["status"] == "invalid"
    assert "not available" in response.json()["message"].lower() or "not authorized" in response.json()["message"].lower()


def test_refresh_briefing_callback(telegram_app):
    client, _, _ = telegram_app
    code = _create_code(client)
    with patch("routers.integrations.send_telegram_message"):
        _bind_code_webhook(client, code, chat_id="briefing-chat")
        
    with patch("services.briefing_recovery_merge.compose_daily_briefing_with_recovery") as mock_compose:
        mock_compose.return_value = {"message_text": "Mock Daily Briefing Content"}
        response = callback_webhook(client, "briefing-chat", "owner_refresh_briefing")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["message"] == "Mock Daily Briefing Content"


def test_cross_factory_isolation_in_callbacks(telegram_app):
    client, SessionLocal, active_user_id = telegram_app
    
    # Add Factory B outstanding bill to ensure it doesn't leak to Factory A
    db = SessionLocal()
    from models import Customer, OutstandingBill
    c_b = Customer(id=201, factory_id=2, name="Customer Factory B")
    db.add(c_b)
    db.flush()
    db.add(
        OutstandingBill(
            id=3,
            factory_id=2,
            customer_id=201,
            tracking_number="B-B1",
            bill_date=datetime.now(timezone.utc).date() - timedelta(days=20),
            bill_amount=99999.00,
            balance_amount=99999.00,
            status="active"
        )
    )
    db.commit()
    db.close()

    # Bind Owner of Factory A
    active_user_id["value"] = 11
    code_a = _create_code(client)
    with patch("routers.integrations.send_telegram_message"):
        _bind_code_webhook(client, code_a, chat_id="chat-isolation-a")

    response = callback_webhook(client, "chat-isolation-a", "owner_collection_war_room")
    assert response.status_code == 200
    msg = response.json()["message"]
    # Total Outstanding must NOT include Factory B's 99999.00
    assert "99,999.00" not in msg
    assert "Customer Factory B" not in msg


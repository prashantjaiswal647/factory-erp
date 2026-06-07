"""
Integration tests for Telegram Action Layer (P4.1)

Tests the full /api/v1/telegram/action endpoint using mocks to avoid
PostgreSQL-specific JSONB/UUID types. All DB interactions are mocked
at the service layer.

Verifies:
1. Unknown chat_id is rejected (status=error)
2. Invalid API key returns 401
3. Duplicate callback returns status=duplicate
4. A1, A2, A3, A4, A5, A6 actions all return status=ok
5. Factory isolation — each factory resolved by its own chat_id
6. Unknown action returns graceful ok with error message
"""

import os
import inspect
import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from db import get_db
from routers.telegram_actions import router


TEST_N8N_API_KEY = "test-n8n-secret-integration"
_ORIGINAL_N8N_API_KEY = None


def _apply_httpx_patch():
    """Patch httpx.Client to accept 'app' kwarg used by Starlette TestClient."""
    if "app" in inspect.signature(httpx.Client.__init__).parameters:
        return
    original = httpx.Client.__init__
    if getattr(original, "_p4_compatible", False):
        return
    def patched(self, *args, app=None, **kwargs):
        return original(self, *args, **kwargs)
    patched._p4_compatible = True
    httpx.Client.__init__ = patched


def setup_module(module):
    global _ORIGINAL_N8N_API_KEY
    _ORIGINAL_N8N_API_KEY = os.environ.get("N8N_API_KEY")
    os.environ["N8N_API_KEY"] = TEST_N8N_API_KEY
    _apply_httpx_patch()


def teardown_module(module):
    if _ORIGINAL_N8N_API_KEY is None:
        os.environ.pop("N8N_API_KEY", None)
    else:
        os.environ["N8N_API_KEY"] = _ORIGINAL_N8N_API_KEY


# ---------------------------------------------------------------------------
# App factory — db override not needed since all service calls are mocked
# ---------------------------------------------------------------------------

def build_app():
    app = FastAPI()
    app.include_router(router)
    return app


VALID_HEADERS = {"X-N8N-API-KEY": TEST_N8N_API_KEY}

FACTORY_1_CHAT = "chat_factory_1_integration"
FACTORY_2_CHAT = "chat_factory_2_integration"


def _make_mock_factory(factory_id: int, chat_id: str) -> MagicMock:
    f = MagicMock()
    f.id = factory_id
    f.telegram_chat_id = chat_id
    f.telegram_token = None
    f.telegram_bot_token = f"bot_token_{factory_id}"
    f.is_active = True
    return f


def _make_mock_owner(factory_id: int) -> MagicMock:
    u = MagicMock()
    u.id = factory_id * 10
    u.factory_id = factory_id
    u.full_name = f"Owner {factory_id}"
    u.username = f"owner_{factory_id}"
    u.role = "Owner"
    return u


def make_payload(chat_id, callback_data, callback_id="cb_unique") -> dict:
    return {"callback_id": callback_id, "chat_id": chat_id, "callback_data": callback_data}


# ---------------------------------------------------------------------------
# Shared mock patches for most tests
# ---------------------------------------------------------------------------

def _base_patches(factory_id=100, chat_id=FACTORY_1_CHAT, dedupe_result=True):
    """Return a context manager stack that mocks all external dependencies."""
    mock_factory = _make_mock_factory(factory_id, chat_id)
    mock_owner = _make_mock_owner(factory_id)

    patches = [
        patch("routers.telegram_actions._resolve_factory", return_value=mock_factory),
        patch("routers.telegram_actions._owner_for_factory", return_value=mock_owner),
        patch("routers.telegram_actions.dedupe_check", return_value=dedupe_result),
        patch("routers.telegram_actions._send_reply"),
        patch("routers.telegram_actions._answer_callback"),
        # DB session mock
        patch("routers.telegram_actions.get_db", return_value=iter([MagicMock()])),
    ]
    return patches


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_invalid_api_key_returns_401():
    client = TestClient(build_app())
    resp = client.post(
        "/api/v1/telegram/action",
        json=make_payload(FACTORY_1_CHAT, "A1:view"),
        headers={"X-N8N-API-KEY": "wrong-key"},
    )
    assert resp.status_code == 401


def test_missing_api_key_returns_401():
    client = TestClient(build_app())
    resp = client.post(
        "/api/v1/telegram/action",
        json=make_payload(FACTORY_1_CHAT, "A1:view"),
        headers={},
    )
    assert resp.status_code == 401


def test_unknown_chat_id_rejected():
    client = TestClient(build_app())
    with patch("routers.telegram_actions._resolve_factory", return_value=None), \
         patch("routers.telegram_actions.get_db", return_value=iter([MagicMock()])):
        resp = client.post(
            "/api/v1/telegram/action",
            json=make_payload("unknown_chat_999", "A1:view", "cb_unk_001"),
            headers=VALID_HEADERS,
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


def test_duplicate_callback_returns_duplicate():
    client = TestClient(build_app())
    mock_factory = _make_mock_factory(100, FACTORY_1_CHAT)
    mock_owner = _make_mock_owner(100)

    with patch("routers.telegram_actions._resolve_factory", return_value=mock_factory), \
         patch("routers.telegram_actions._owner_for_factory", return_value=mock_owner), \
         patch("routers.telegram_actions.dedupe_check", return_value=False), \
         patch("routers.telegram_actions._send_reply"), \
         patch("routers.telegram_actions._answer_callback"), \
         patch("routers.telegram_actions.get_db", return_value=iter([MagicMock()])):
        resp = client.post(
            "/api/v1/telegram/action",
            json=make_payload(FACTORY_1_CHAT, "A1:view", "cb_dup"),
            headers=VALID_HEADERS,
        )
    assert resp.json()["status"] == "duplicate"


def test_a1_outstanding_ok():
    client = TestClient(build_app())
    mock_factory = _make_mock_factory(100, FACTORY_1_CHAT)
    mock_owner = _make_mock_owner(100)

    with patch("routers.telegram_actions._resolve_factory", return_value=mock_factory), \
         patch("routers.telegram_actions._owner_for_factory", return_value=mock_owner), \
         patch("routers.telegram_actions.dedupe_check", return_value=True), \
         patch("routers.telegram_actions._send_reply"), \
         patch("routers.telegram_actions._answer_callback"), \
         patch("routers.telegram_actions.handle_outstanding_view") as mock_handler, \
         patch("routers.telegram_actions.get_db", return_value=iter([MagicMock()])):
        from services.telegram_actions import TelegramActionResult
        mock_handler.return_value = TelegramActionResult(message="Outstanding OK")
        resp = client.post(
            "/api/v1/telegram/action",
            json=make_payload(FACTORY_1_CHAT, "A1:view", "cb_a1"),
            headers=VALID_HEADERS,
        )
    assert resp.json()["status"] == "ok"
    mock_handler.assert_called_once()


def test_a2_inventory_ok():
    client = TestClient(build_app())
    mock_factory = _make_mock_factory(100, FACTORY_1_CHAT)
    mock_owner = _make_mock_owner(100)

    with patch("routers.telegram_actions._resolve_factory", return_value=mock_factory), \
         patch("routers.telegram_actions._owner_for_factory", return_value=mock_owner), \
         patch("routers.telegram_actions.dedupe_check", return_value=True), \
         patch("routers.telegram_actions._send_reply"), \
         patch("routers.telegram_actions._answer_callback"), \
         patch("routers.telegram_actions.handle_inventory_view") as mock_handler, \
         patch("routers.telegram_actions.get_db", return_value=iter([MagicMock()])):
        from services.telegram_actions import TelegramActionResult
        mock_handler.return_value = TelegramActionResult(message="Inventory OK")
        resp = client.post(
            "/api/v1/telegram/action",
            json=make_payload(FACTORY_1_CHAT, "A2:view", "cb_a2"),
            headers=VALID_HEADERS,
        )
    assert resp.json()["status"] == "ok"


def test_a3_start_ok():
    client = TestClient(build_app())
    mock_factory = _make_mock_factory(100, FACTORY_1_CHAT)
    mock_owner = _make_mock_owner(100)

    with patch("routers.telegram_actions._resolve_factory", return_value=mock_factory), \
         patch("routers.telegram_actions._owner_for_factory", return_value=mock_owner), \
         patch("routers.telegram_actions.dedupe_check", return_value=True), \
         patch("routers.telegram_actions._send_reply"), \
         patch("routers.telegram_actions._answer_callback"), \
         patch("routers.telegram_actions.handle_production_start") as mock_handler, \
         patch("routers.telegram_actions.get_db", return_value=iter([MagicMock()])):
        from services.telegram_actions import TelegramActionResult
        mock_handler.return_value = TelegramActionResult(message="Production start OK")
        resp = client.post(
            "/api/v1/telegram/action",
            json=make_payload(FACTORY_1_CHAT, "A3:start", "cb_a3_s"),
            headers=VALID_HEADERS,
        )
    assert resp.json()["status"] == "ok"


def test_a3_cancel_ok():
    client = TestClient(build_app())
    mock_factory = _make_mock_factory(100, FACTORY_1_CHAT)
    mock_owner = _make_mock_owner(100)

    with patch("routers.telegram_actions._resolve_factory", return_value=mock_factory), \
         patch("routers.telegram_actions._owner_for_factory", return_value=mock_owner), \
         patch("routers.telegram_actions.dedupe_check", return_value=True), \
         patch("routers.telegram_actions._send_reply"), \
         patch("routers.telegram_actions._answer_callback"), \
         patch("routers.telegram_actions.handle_production_cancel") as mock_handler, \
         patch("routers.telegram_actions.get_db", return_value=iter([MagicMock()])):
        from services.telegram_actions import TelegramActionResult
        mock_handler.return_value = TelegramActionResult(message="Cancelled")
        resp = client.post(
            "/api/v1/telegram/action",
            json=make_payload(FACTORY_1_CHAT, "A3:cancel", "cb_a3_c"),
            headers=VALID_HEADERS,
        )
    assert resp.json()["status"] == "ok"


def test_a4_start_ok():
    client = TestClient(build_app())
    mock_factory = _make_mock_factory(100, FACTORY_1_CHAT)
    mock_owner = _make_mock_owner(100)

    with patch("routers.telegram_actions._resolve_factory", return_value=mock_factory), \
         patch("routers.telegram_actions._owner_for_factory", return_value=mock_owner), \
         patch("routers.telegram_actions.dedupe_check", return_value=True), \
         patch("routers.telegram_actions._send_reply"), \
         patch("routers.telegram_actions._answer_callback"), \
         patch("routers.telegram_actions.handle_attendance_start") as mock_handler, \
         patch("routers.telegram_actions.get_db", return_value=iter([MagicMock()])):
        from services.telegram_actions import TelegramActionResult
        mock_handler.return_value = TelegramActionResult(message="Attendance start OK")
        resp = client.post(
            "/api/v1/telegram/action",
            json=make_payload(FACTORY_1_CHAT, "A4:start", "cb_a4_s"),
            headers=VALID_HEADERS,
        )
    assert resp.json()["status"] == "ok"


def test_a4_cancel_ok():
    client = TestClient(build_app())
    mock_factory = _make_mock_factory(100, FACTORY_1_CHAT)
    mock_owner = _make_mock_owner(100)

    with patch("routers.telegram_actions._resolve_factory", return_value=mock_factory), \
         patch("routers.telegram_actions._owner_for_factory", return_value=mock_owner), \
         patch("routers.telegram_actions.dedupe_check", return_value=True), \
         patch("routers.telegram_actions._send_reply"), \
         patch("routers.telegram_actions._answer_callback"), \
         patch("routers.telegram_actions.handle_attendance_cancel") as mock_handler, \
         patch("routers.telegram_actions.get_db", return_value=iter([MagicMock()])):
        from services.telegram_actions import TelegramActionResult
        mock_handler.return_value = TelegramActionResult(message="Cancelled")
        resp = client.post(
            "/api/v1/telegram/action",
            json=make_payload(FACTORY_1_CHAT, "A4:cancel", "cb_a4_c"),
            headers=VALID_HEADERS,
        )
    assert resp.json()["status"] == "ok"


def test_a5_briefing_ok():
    client = TestClient(build_app())
    mock_factory = _make_mock_factory(100, FACTORY_1_CHAT)
    mock_owner = _make_mock_owner(100)

    with patch("routers.telegram_actions._resolve_factory", return_value=mock_factory), \
         patch("routers.telegram_actions._owner_for_factory", return_value=mock_owner), \
         patch("routers.telegram_actions.dedupe_check", return_value=True), \
         patch("routers.telegram_actions._send_reply"), \
         patch("routers.telegram_actions._answer_callback"), \
         patch("routers.telegram_actions.handle_briefing_full") as mock_handler, \
         patch("routers.telegram_actions.get_db", return_value=iter([MagicMock()])):
        from services.telegram_actions import TelegramActionResult
        mock_handler.return_value = TelegramActionResult(message="Briefing OK")
        resp = client.post(
            "/api/v1/telegram/action",
            json=make_payload(FACTORY_1_CHAT, "A5:full", "cb_a5"),
            headers=VALID_HEADERS,
        )
    assert resp.json()["status"] == "ok"


def test_a6_ask_ok():
    client = TestClient(build_app())
    mock_factory = _make_mock_factory(100, FACTORY_1_CHAT)
    mock_owner = _make_mock_owner(100)

    with patch("routers.telegram_actions._resolve_factory", return_value=mock_factory), \
         patch("routers.telegram_actions._owner_for_factory", return_value=mock_owner), \
         patch("routers.telegram_actions.dedupe_check", return_value=True), \
         patch("routers.telegram_actions._send_reply"), \
         patch("routers.telegram_actions._answer_callback"), \
         patch("routers.telegram_actions.handle_ask_start") as mock_handler, \
         patch("routers.telegram_actions.get_db", return_value=iter([MagicMock()])):
        from services.telegram_actions import TelegramActionResult
        mock_handler.return_value = TelegramActionResult(message="Ask Munshi stub")
        resp = client.post(
            "/api/v1/telegram/action",
            json=make_payload(FACTORY_1_CHAT, "A6:start", "cb_a6"),
            headers=VALID_HEADERS,
        )
    assert resp.json()["status"] == "ok"


def test_unknown_action_returns_ok_graceful():
    """Unknown action codes must not crash — return ok with helpful message."""
    client = TestClient(build_app())
    mock_factory = _make_mock_factory(100, FACTORY_1_CHAT)
    mock_owner = _make_mock_owner(100)

    with patch("routers.telegram_actions._resolve_factory", return_value=mock_factory), \
         patch("routers.telegram_actions._owner_for_factory", return_value=mock_owner), \
         patch("routers.telegram_actions.dedupe_check", return_value=True), \
         patch("routers.telegram_actions._send_reply"), \
         patch("routers.telegram_actions._answer_callback"), \
         patch("routers.telegram_actions.get_db", return_value=iter([MagicMock()])):
        resp = client.post(
            "/api/v1/telegram/action",
            json=make_payload(FACTORY_1_CHAT, "ZZ:unknown", "cb_unk"),
            headers=VALID_HEADERS,
        )
    assert resp.status_code == 200
    # Must not 500; must return a valid response
    data = resp.json()
    assert data["status"] in ("ok", "error")


def test_factory_isolation_two_factories_separate_resolution():
    """Each factory resolves independently from its own chat_id."""
    client = TestClient(build_app())
    mock_factory_1 = _make_mock_factory(100, FACTORY_1_CHAT)
    mock_factory_2 = _make_mock_factory(200, FACTORY_2_CHAT)
    mock_owner_1 = _make_mock_owner(100)
    mock_owner_2 = _make_mock_owner(200)

    resolved_factories = []

    def resolve_side_effect(db, chat_id):
        if chat_id == FACTORY_1_CHAT:
            return mock_factory_1
        elif chat_id == FACTORY_2_CHAT:
            return mock_factory_2
        return None

    def owner_side_effect(db, factory_id):
        if factory_id == 100:
            return mock_owner_1
        elif factory_id == 200:
            return mock_owner_2
        return None

    def handler_side_effect(db, factory_id, chat_id, payload):
        resolved_factories.append(factory_id)
        from services.telegram_actions import TelegramActionResult
        return TelegramActionResult(message=f"OK for factory {factory_id}")

    with patch("routers.telegram_actions._resolve_factory", side_effect=resolve_side_effect), \
         patch("routers.telegram_actions._owner_for_factory", side_effect=owner_side_effect), \
         patch("routers.telegram_actions.dedupe_check", return_value=True), \
         patch("routers.telegram_actions._send_reply"), \
         patch("routers.telegram_actions._answer_callback"), \
         patch("routers.telegram_actions.handle_inventory_view", side_effect=handler_side_effect), \
         patch("routers.telegram_actions.get_db", return_value=iter([MagicMock()])):

        resp1 = client.post(
            "/api/v1/telegram/action",
            json=make_payload(FACTORY_1_CHAT, "A2:view", "cb_iso_f1"),
            headers=VALID_HEADERS,
        )

    with patch("routers.telegram_actions._resolve_factory", side_effect=resolve_side_effect), \
         patch("routers.telegram_actions._owner_for_factory", side_effect=owner_side_effect), \
         patch("routers.telegram_actions.dedupe_check", return_value=True), \
         patch("routers.telegram_actions._send_reply"), \
         patch("routers.telegram_actions._answer_callback"), \
         patch("routers.telegram_actions.handle_inventory_view", side_effect=handler_side_effect), \
         patch("routers.telegram_actions.get_db", return_value=iter([MagicMock()])):

        resp2 = client.post(
            "/api/v1/telegram/action",
            json=make_payload(FACTORY_2_CHAT, "A2:view", "cb_iso_f2"),
            headers=VALID_HEADERS,
        )

    assert resp1.json()["status"] == "ok"
    assert resp2.json()["status"] == "ok"
    assert 100 in resolved_factories
    assert 200 in resolved_factories
    # Factories must be resolved independently
    assert resolved_factories[0] != resolved_factories[1], "Each factory must be isolated"

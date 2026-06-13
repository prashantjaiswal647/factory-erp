import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from decimal import Decimal
from datetime import date

from db import get_db
from models import Factory, User, TelegramUserBinding, SalesInvoice, Customer, OutstandingBill, DailyProduction, ShiftWastage
from routers.telegram_actions import router
from services.telegram_actions import TelegramActionResult, InlineButton
from tests.test_telegram_action_layer import build_app, VALID_HEADERS, FACTORY_1_CHAT, _make_mock_factory, TEST_N8N_API_KEY, _apply_httpx_patch

_ORIGINAL_N8N_API_KEY = None

def setup_module(module):
    global _ORIGINAL_N8N_API_KEY
    _ORIGINAL_N8N_API_KEY = os.environ.get("N8N_API_KEY")
    os.environ["N8N_API_KEY"] = TEST_N8N_API_KEY
    _apply_httpx_patch()

def teardown_module(module):
    global _ORIGINAL_N8N_API_KEY
    if _ORIGINAL_N8N_API_KEY is None:
        os.environ.pop("N8N_API_KEY", None)
    else:
        os.environ["N8N_API_KEY"] = _ORIGINAL_N8N_API_KEY

# ---------------------------------------------------------------------------
# Test setup helpers
# ---------------------------------------------------------------------------

def _make_mock_sub_owner(factory_id: int) -> MagicMock:
    u = MagicMock()
    u.id = factory_id * 10 + 1
    u.factory_id = factory_id
    u.full_name = f"Sub Owner {factory_id}"
    u.username = f"sub_owner_{factory_id}"
    u.role = "Sub-Owner"
    return u


def _make_mock_owner(factory_id: int) -> MagicMock:
    u = MagicMock()
    u.id = factory_id * 10
    u.factory_id = factory_id
    u.full_name = f"Owner {factory_id}"
    u.username = f"owner_{factory_id}"
    u.role = "Owner"
    return u


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_a10_dashboard_summary_owner():
    mock_db = MagicMock()
    # Mock queries so it doesn't fail on resolution of binding/user
    mock_db.query.return_value.filter.return_value.first.return_value = None

    app = build_app()
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)

    mock_factory = _make_mock_factory(100, FACTORY_1_CHAT)
    mock_owner = _make_mock_owner(100)

    with patch("routers.telegram_actions._resolve_factory", return_value=mock_factory), \
         patch("routers.telegram_actions._owner_for_factory", return_value=mock_owner), \
         patch("routers.telegram_actions.dedupe_check", return_value=True), \
         patch("routers.telegram_actions._send_reply"), \
         patch("routers.telegram_actions._answer_callback"):

        with patch("routers.telegram_actions.handle_dashboard_summary_view") as mock_handler:
            mock_handler.return_value = TelegramActionResult(message="Owner summary info with financial details")
            
            resp = client.post(
                "/api/v1/telegram/action",
                json={"callback_id": "cb_a10_owner", "chat_id": FACTORY_1_CHAT, "callback_data": "A10:view"},
                headers=VALID_HEADERS,
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
            mock_handler.assert_called_once()


def test_a10_dashboard_summary_sub_owner_masking():
    mock_factory = _make_mock_factory(100, FACTORY_1_CHAT)
    mock_sub_owner = _make_mock_sub_owner(100)
    mock_binding = MagicMock(spec=TelegramUserBinding)
    mock_binding.factory_id = 100
    mock_binding.user_id = mock_sub_owner.id
    mock_binding.role = "Sub-Owner"

    mock_db = MagicMock()
    # When querying models, handle role resolution correctly
    def db_query_side_effect(model):
        q = MagicMock()
        if model is TelegramUserBinding:
            q.filter.return_value.first.return_value = mock_binding
        elif model is User:
            q.filter.return_value.first.return_value = mock_sub_owner
        else:
            q.filter.return_value.scalar.return_value = 10
        return q

    mock_db.query.side_effect = db_query_side_effect

    app = build_app()
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)

    with patch("routers.telegram_actions._resolve_factory", return_value=mock_factory), \
         patch("routers.telegram_actions.dedupe_check", return_value=True), \
         patch("routers.telegram_actions._send_reply") as mock_send, \
         patch("routers.telegram_actions._answer_callback"):

        resp = client.post(
            "/api/v1/telegram/action",
            json={"callback_id": "cb_a10_sub", "chat_id": FACTORY_1_CHAT, "callback_data": "A10:view"},
            headers=VALID_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        
        args, kwargs = mock_send.call_args
        sent_message = args[2].message
        assert "[Masked]" in sent_message
        assert "Revenue" in sent_message
        assert "Outstanding" in sent_message


def test_a12_invoices_search_sub_owner_restricted():
    mock_factory = _make_mock_factory(100, FACTORY_1_CHAT)
    mock_sub_owner = _make_mock_sub_owner(100)
    mock_binding = MagicMock(spec=TelegramUserBinding)
    mock_binding.factory_id = 100
    mock_binding.user_id = mock_sub_owner.id
    mock_binding.role = "Sub-Owner"

    mock_db = MagicMock()
    def db_query_side_effect(model):
        q = MagicMock()
        if model is TelegramUserBinding:
            q.filter.return_value.first.return_value = mock_binding
        elif model is User:
            q.filter.return_value.first.return_value = mock_sub_owner
        else:
            q.filter.return_value.first.return_value = None
        return q

    mock_db.query.side_effect = db_query_side_effect

    app = build_app()
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)

    with patch("routers.telegram_actions._resolve_factory", return_value=mock_factory), \
         patch("routers.telegram_actions.dedupe_check", return_value=True), \
         patch("routers.telegram_actions._send_reply") as mock_send, \
         patch("routers.telegram_actions._answer_callback"):

        resp = client.post(
            "/api/v1/telegram/action",
            json={"callback_id": "cb_a12_sub", "chat_id": FACTORY_1_CHAT, "callback_data": "A12:start"},
            headers=VALID_HEADERS,
        )
        assert resp.status_code == 200
        args, kwargs = mock_send.call_args
        sent_message = args[2].message
        assert "Unauthorized" in sent_message


def test_w2_wastage_guided_flow():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    app = build_app()
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app)

    mock_factory = _make_mock_factory(100, FACTORY_1_CHAT)
    mock_owner = _make_mock_owner(100)

    with patch("routers.telegram_actions._resolve_factory", return_value=mock_factory), \
         patch("routers.telegram_actions._owner_for_factory", return_value=mock_owner), \
         patch("routers.telegram_actions.dedupe_check", return_value=True), \
         patch("routers.telegram_actions._send_reply") as mock_send, \
         patch("routers.telegram_actions._answer_callback"):

        # 1. Start the wastage session
        with patch("services.telegram_actions.create_session") as mock_create:
            resp = client.post(
                "/api/v1/telegram/action",
                json={"callback_id": "cb_w2_start", "chat_id": FACTORY_1_CHAT, "callback_data": "W2:start"},
                headers=VALID_HEADERS,
            )
            assert resp.json()["status"] == "ok"
            mock_create.assert_called_once()

        # 2. Select Shift
        mock_session = MagicMock()
        mock_session.payload_json = {}
        with patch("services.telegram_actions.get_session", return_value=mock_session), \
             patch("services.telegram_actions.update_session") as mock_update:
            resp = client.post(
                "/api/v1/telegram/action",
                json={"callback_id": "cb_w2_shift", "chat_id": FACTORY_1_CHAT, "callback_data": "W2:shift:Day"},
                headers=VALID_HEADERS,
            )
            assert resp.json()["status"] == "ok"
            mock_update.assert_called_once()

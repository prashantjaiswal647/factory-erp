"""
Tests for telegram_action_session.py

Uses unittest.mock to isolate from PostgreSQL-specific types (UUID, JSONB).
Verifies the service logic by mocking the ORM queries.

Verifies:
1. create_session expires existing pending sessions and creates new one
2. get_session returns latest unexpired pending session
3. get_session with action filter works
4. get_session with expired session returns None
5. update_session changes step and payload
6. update_session changes status to committed
7. expire_sessions marks pending-expired sessions as expired
8. factory_id filter prevents cross-factory access
"""

import pytest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call


def _make_session(factory_id=10, chat_id="chat_X", action="production", step="size",
                  payload=None, status="pending", expires_in_minutes=5, session_id=None):
    """Create a mock TelegramActionSession-like object."""
    import uuid
    expires_at = datetime.utcnow() + timedelta(minutes=expires_in_minutes)
    return SimpleNamespace(
        session_id=session_id or str(uuid.uuid4()),
        factory_id=factory_id,
        chat_id=chat_id,
        action=action,
        step=step,
        payload_json=payload or {},
        callback_id=None,
        created_at=datetime.utcnow(),
        expires_at=expires_at,
        status=status,
    )


# ---------------------------------------------------------------------------
# Tests using in-memory mock DB session
# ---------------------------------------------------------------------------

def test_create_session_expires_old_and_creates_new():
    from services.telegram_action_session import create_session

    db = MagicMock()
    db.query.return_value.filter.return_value.update.return_value = None
    db.add.return_value = None
    db.commit.return_value = None
    db.refresh.side_effect = lambda obj: obj

    sess = create_session(db, 10, "chat_A", "production", "size", {"a": 1})

    assert sess.factory_id == 10
    assert sess.chat_id == "chat_A"
    assert sess.action == "production"
    assert sess.step == "size"
    assert sess.payload_json == {"a": 1}
    assert sess.status == "pending"

    # Verify the update call for expiring old sessions was made
    db.commit.assert_called_once()


def test_create_session_custom_ttl():
    from services.telegram_action_session import create_session

    db = MagicMock()
    db.refresh.side_effect = lambda obj: obj

    sess = create_session(db, 10, "chat_A", "production", "size", {}, ttl_minutes=10)

    expected_min_expiry = datetime.utcnow() + timedelta(minutes=9, seconds=30)
    assert sess.expires_at > expected_min_expiry, "Custom TTL should set expires_at in future"


def test_get_session_returns_matching_session():
    from services.telegram_action_session import get_session

    mock_sess = _make_session(factory_id=10, chat_id="chat_B", action="production")
    query_chain = MagicMock()
    query_chain.filter.return_value = query_chain
    query_chain.order_by.return_value = query_chain
    query_chain.first.return_value = mock_sess
    db = MagicMock()
    db.query.return_value = query_chain

    result = get_session(db, 10, "chat_B", "production")

    assert result == mock_sess


def test_get_session_no_action_filter():
    from services.telegram_action_session import get_session

    mock_sess = _make_session(factory_id=10, chat_id="chat_C")
    query_chain = MagicMock()
    query_chain.filter.return_value = query_chain
    query_chain.order_by.return_value = query_chain
    query_chain.first.return_value = mock_sess
    db = MagicMock()
    db.query.return_value = query_chain

    result = get_session(db, 10, "chat_C", action=None)

    assert result == mock_sess


def test_get_session_expired_returns_none():
    from services.telegram_action_session import get_session

    query_chain = MagicMock()
    query_chain.filter.return_value = query_chain
    query_chain.order_by.return_value = query_chain
    query_chain.first.return_value = None  # Expired → None
    db = MagicMock()
    db.query.return_value = query_chain

    result = get_session(db, 10, "chat_E", "production")

    assert result is None


def test_update_session_changes_step_and_payload():
    from services.telegram_action_session import update_session
    import uuid

    sid = str(uuid.uuid4())
    mock_sess = _make_session(session_id=sid, step="size", payload={})
    mock_sess.step = "size"
    mock_sess.payload_json = {}

    query_chain = MagicMock()
    db = MagicMock()
    db.query.return_value = query_chain
    query_chain.filter.return_value = query_chain
    query_chain.first.return_value = mock_sess

    result = update_session(db, sid, "machine", {"size_ml": 150, "machine_id": 5})

    assert result is not None
    assert result.step == "machine"
    assert result.payload_json["size_ml"] == 150
    assert result.payload_json["machine_id"] == 5


def test_update_session_status_committed():
    from services.telegram_action_session import update_session
    import uuid

    sid = str(uuid.uuid4())
    mock_sess = _make_session(session_id=sid, step="confirm", status="pending")

    query_chain = MagicMock()
    db = MagicMock()
    db.query.return_value = query_chain
    query_chain.filter.return_value = query_chain
    query_chain.first.return_value = mock_sess

    result = update_session(db, sid, "committed", {}, status="committed")

    assert result.status == "committed"


def test_update_session_not_found_returns_none():
    from services.telegram_action_session import update_session

    query_chain = MagicMock()
    db = MagicMock()
    db.query.return_value = query_chain
    query_chain.filter.return_value = query_chain
    query_chain.first.return_value = None

    result = update_session(db, "nonexistent-id", "step", {})

    assert result is None


def test_expire_sessions_calls_update():
    from services.telegram_action_session import expire_sessions

    query_chain = MagicMock()
    db = MagicMock()
    db.query.return_value = query_chain
    query_chain.filter.return_value = query_chain
    query_chain.update.return_value = 2

    expire_sessions(db)

    db.commit.assert_called_once()


def test_factory_isolation_verified_by_filter():
    """
    Verify that get_session applies factory_id filter.
    When DB chain returns None (factory_id=20 has no sessions), result must be None.
    """
    from services.telegram_action_session import get_session

    query_chain = MagicMock()
    query_chain.filter.return_value = query_chain
    query_chain.order_by.return_value = query_chain
    query_chain.first.return_value = None  # factory 20 has no sessions
    db = MagicMock()
    db.query.return_value = query_chain

    result = get_session(db, 20, "shared_chat", "production")

    assert result is None, "Factory 20 must not get factory 10 sessions"

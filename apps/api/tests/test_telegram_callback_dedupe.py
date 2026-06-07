"""
Tests for telegram_callback_dedupe.py

Uses a selective metadata approach: only creates tables that are SQLite-compatible
(telegram_callback_dedupe uses String PK, not UUID/JSONB).

Verifies:
1. First-time callback returns True (accepted)
2. Same callback_id returns False (duplicate)
3. cleanup_callback_dedupes removes old records
4. Different callback_ids are both accepted
5. Cleanup preserves fresh records
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, String, Integer, DateTime, func
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Isolated SQLite-compatible test schema
# ---------------------------------------------------------------------------

class TestBase(DeclarativeBase):
    pass


class TelegramCallbackDedupeTest(TestBase):
    """SQLite-compatible test version of TelegramCallbackDedupe."""
    __tablename__ = "telegram_callback_dedupe"

    callback_id = Column(String(64), primary_key=True)
    factory_id = Column(Integer, nullable=False, index=True)
    action = Column(String(64), nullable=False)
    received_at = Column(DateTime, nullable=False, default=datetime.utcnow)


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    TestBase.metadata.drop_all(bind=engine)
    TestBase.metadata.create_all(bind=engine)
    yield
    TestBase.metadata.drop_all(bind=engine)


# We patch the model used by the service with our test model
@pytest.fixture(autouse=True)
def patch_model(monkeypatch):
    import services.telegram_callback_dedupe as dedupe_module
    monkeypatch.setattr(dedupe_module, "TelegramCallbackDedupe", TelegramCallbackDedupeTest)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_first_callback_accepted(patch_model):
    from services.telegram_callback_dedupe import dedupe_check
    db = TestingSessionLocal()
    try:
        result = dedupe_check(db, "cb_001", 1, "A1")
        assert result is True, "First callback should be accepted"
    finally:
        db.close()


def test_duplicate_callback_rejected(patch_model):
    from services.telegram_callback_dedupe import dedupe_check
    db = TestingSessionLocal()
    try:
        dedupe_check(db, "cb_002", 1, "A1")
        result = dedupe_check(db, "cb_002", 1, "A1")
        assert result is False, "Duplicate callback should be rejected"
    finally:
        db.close()


def test_same_callback_id_second_factory_rejected(patch_model):
    """Callback_id is globally unique; second insert for same ID is rejected regardless of factory."""
    from services.telegram_callback_dedupe import dedupe_check
    db = TestingSessionLocal()
    try:
        result1 = dedupe_check(db, "cb_shared", 1, "A1")
        result2 = dedupe_check(db, "cb_shared", 2, "A1")
        assert result1 is True
        assert result2 is False
    finally:
        db.close()


def test_different_callback_ids_both_accepted(patch_model):
    from services.telegram_callback_dedupe import dedupe_check
    db = TestingSessionLocal()
    try:
        r1 = dedupe_check(db, "cb_003", 1, "A2")
        r2 = dedupe_check(db, "cb_004", 1, "A2")
        assert r1 is True
        assert r2 is True
    finally:
        db.close()


def test_cleanup_removes_old_records(patch_model):
    from services.telegram_callback_dedupe import cleanup_callback_dedupes
    db = TestingSessionLocal()
    try:
        old_record = TelegramCallbackDedupeTest(
            callback_id="cb_old",
            factory_id=1,
            action="A1",
            received_at=datetime.utcnow() - timedelta(hours=25),
        )
        db.add(old_record)
        fresh_record = TelegramCallbackDedupeTest(
            callback_id="cb_fresh",
            factory_id=1,
            action="A1",
            received_at=datetime.utcnow(),
        )
        db.add(fresh_record)
        db.commit()

        cleanup_callback_dedupes(db)

        remaining = db.query(TelegramCallbackDedupeTest).all()
        ids = {r.callback_id for r in remaining}
        assert "cb_old" not in ids, "Old record should be cleaned up"
        assert "cb_fresh" in ids, "Fresh record should remain"
    finally:
        db.close()


def test_cleanup_preserves_new_records(patch_model):
    from services.telegram_callback_dedupe import dedupe_check, cleanup_callback_dedupes
    db = TestingSessionLocal()
    try:
        dedupe_check(db, "cb_new1", 1, "A3")
        dedupe_check(db, "cb_new2", 1, "A4")
        cleanup_callback_dedupes(db)
        remaining = db.query(TelegramCallbackDedupeTest).count()
        assert remaining >= 2, "New records must survive cleanup"
    finally:
        db.close()

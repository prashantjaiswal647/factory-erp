import asyncio
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import Factory, User
from services.master_backup_email import deliver_master_backup
from services.master_backup_scheduler import due_frequencies, run_backup_email_batch
from services.timezone_utils import KOLKATA_ZONE


@pytest.fixture()
def email_db(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = session_factory()
    factory = Factory(id=1, name="Email Factory", factory_name="Email Factory", subscription_status="active")
    owner = User(
        id=1,
        factory_id=1,
        username="owner",
        email="owner@example.com",
        password_hash="test",
        role="Owner",
        is_active=True,
    )
    db.add_all([factory, owner])
    db.commit()
    delivery_root = tmp_path / "scheduled-email"
    monkeypatch.setattr("services.master_backup_email.DELIVERY_ROOT", delivery_root)
    try:
        yield db, session_factory, factory, owner
    finally:
        db.close()
        engine.dispose()


def test_weekly_and_monthly_backups_are_sent_as_separate_emails(email_db):
    db, _, factory, owner = email_db
    messages = []

    async def sender(**message):
        messages.append(message)

    target = date(2026, 2, 1)
    assert asyncio.run(deliver_master_backup(db, factory, owner, "weekly", target, sender=sender))
    assert asyncio.run(deliver_master_backup(db, factory, owner, "monthly", target, sender=sender))

    assert len(messages) == 2
    assert "Weekly" in messages[0]["subject"]
    assert "Monthly" in messages[1]["subject"]
    assert messages[0]["filename"] != messages[1]["filename"]
    assert messages[0]["backup_bytes"][:2] == b"PK"
    assert messages[1]["backup_bytes"][:2] == b"PK"


def test_same_backup_period_is_not_emailed_twice(email_db):
    db, _, factory, owner = email_db
    messages = []

    async def sender(**message):
        messages.append(message)

    target = date(2026, 6, 14)
    assert asyncio.run(deliver_master_backup(db, factory, owner, "weekly", target, sender=sender))
    assert not asyncio.run(deliver_master_backup(db, factory, owner, "weekly", target, sender=sender))
    assert len(messages) == 1


def test_scheduler_batch_emails_active_owner(email_db):
    _, session_factory, _, _ = email_db
    messages = []

    async def sender(**message):
        messages.append(message)

    metrics = run_backup_email_batch(
        "monthly",
        date(2026, 7, 1),
        session_factory=session_factory,
        sender=sender,
    )
    assert metrics == {"total_factories": 1, "sent": 1, "skipped": 0, "failed": 0}
    assert messages[0]["recipient"] == "owner@example.com"


def test_due_frequencies_keeps_weekly_and_monthly_runs_independent():
    first_sunday = datetime(2026, 2, 1, 21, 0, tzinfo=KOLKATA_ZONE)
    assert due_frequencies(first_sunday) == ["weekly", "monthly"]

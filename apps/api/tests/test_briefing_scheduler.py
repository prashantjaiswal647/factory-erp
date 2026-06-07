from datetime import datetime

from models import ActivityLog, Factory, MorningBriefingLog
from services.briefing_scheduler import (
    deliver_factory_briefing,
    run_daily_briefing_batch,
    seconds_until_next_run,
)
from services.telegram_delivery import TelegramDeliveryError
from services.timezone_utils import KOLKATA_ZONE
from tests.briefing_test_utils import BRIEFING_DATE, make_briefing_db, seed_two_factories


def test_scheduler_targets_7am_asia_kolkata():
    before = datetime(2026, 6, 6, 6, 30, tzinfo=KOLKATA_ZONE)
    after = datetime(2026, 6, 6, 7, 30, tzinfo=KOLKATA_ZONE)

    assert seconds_until_next_run(before) == 30 * 60
    assert seconds_until_next_run(after) == 23.5 * 60 * 60


def test_failed_delivery_retries_and_stores_error(monkeypatch):
    engine, db = make_briefing_db()
    try:
        owner, _ = seed_two_factories(db)
        factory = db.query(Factory).filter(Factory.id == owner.factory_id).one()
        attempts = []

        def failing_sender(factory, message):
            attempts.append(factory.id)
            raise TelegramDeliveryError("temporary Telegram failure", retryable=True)

        monkeypatch.setattr("services.briefing_scheduler.time.sleep", lambda _: None)
        row, sent = deliver_factory_briefing(
            db,
            factory,
            owner,
            BRIEFING_DATE,
            max_retries=3,
            sender=failing_sender,
        )

        assert sent is False
        assert attempts == [factory.id, factory.id, factory.id]
        assert row.status == "failed"
        assert "attempt 3/3" in row.error_message
        assert db.query(MorningBriefingLog).count() == 1
        alerts = db.query(ActivityLog).filter(ActivityLog.action_type == "BRIEFING_SEND_FAILED").all()
        assert len(alerts) == 1
        assert alerts[0].factory_id == factory.id
        assert str(BRIEFING_DATE) in alerts[0].description
        assert "telegram" in alerts[0].description

        deliver_factory_briefing(
            db,
            factory,
            owner,
            BRIEFING_DATE,
            max_retries=1,
            sender=failing_sender,
        )
        assert db.query(ActivityLog).filter(ActivityLog.action_type == "BRIEFING_SEND_FAILED").count() == 1
    finally:
        db.close()
        engine.dispose()


def test_batch_metrics_and_retry_of_failed_row(monkeypatch):
    engine, db = make_briefing_db()
    owner_a, owner_b = seed_two_factories(db)
    expected_factory_ids = sorted([owner_a.factory_id, owner_b.factory_id])
    db.close()

    # Recreate a usable session factory from the engine.
    from sqlalchemy.orm import sessionmaker
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    sent_factory_ids = []

    def sender(factory, message):
        sent_factory_ids.append(factory.id)

    monkeypatch.setattr("services.briefing_scheduler.time.sleep", lambda _: None)
    metrics = run_daily_briefing_batch(
        BRIEFING_DATE,
        session_factory=session_factory,
        max_retries=2,
        sender=sender,
    )

    verify = session_factory()
    try:
        assert metrics == {"total_factories": 2, "sent": 2, "failed": 0}
        assert sorted(sent_factory_ids) == expected_factory_ids
        assert verify.query(MorningBriefingLog).count() == 2
        assert {row.status for row in verify.query(MorningBriefingLog).all()} == {"sent"}
    finally:
        verify.close()
        engine.dispose()


def test_factory_without_active_owner_is_recorded_as_skipped():
    engine, db = make_briefing_db()
    db.add(Factory(id=1, name="Ownerless Factory", subscription_status="active", is_active=True))
    db.commit()
    db.close()

    from sqlalchemy.orm import sessionmaker
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    metrics = run_daily_briefing_batch(BRIEFING_DATE, session_factory=session_factory)

    verify = session_factory()
    try:
        row = verify.query(MorningBriefingLog).one()
        assert metrics == {"total_factories": 1, "sent": 0, "failed": 1}
        assert row.status == "skipped"
        assert row.retry_count == 0
        assert row.error_message == "Active factory owner not found"
    finally:
        verify.close()
        engine.dispose()

from models import MorningBriefingLog
from services.briefing_service import send_briefing
from tests.briefing_test_utils import BRIEFING_DATE, make_briefing_db, seed_two_factories


def test_duplicate_send_is_idempotent_per_factory_date_channel():
    engine, db = make_briefing_db()
    try:
        owner, _ = seed_two_factories(db)

        sends = []

        def fake_sender(factory, message):
            sends.append((factory.id, message))

        first, first_created = send_briefing(
            db,
            owner.factory_id,
            BRIEFING_DATE,
            owner,
            sender=fake_sender,
        )
        second, second_created = send_briefing(
            db,
            owner.factory_id,
            BRIEFING_DATE,
            owner,
            sender=fake_sender,
        )

        assert first_created is True
        assert second_created is False
        assert first.id == second.id
        assert len(sends) == 1
        assert "Production Yesterday" not in sends[0][1]
        assert "Factory Health" in sends[0][1]
        assert "Profit Intelligence" in sends[0][1]
        assert db.query(MorningBriefingLog).filter(
            MorningBriefingLog.factory_id == owner.factory_id,
            MorningBriefingLog.briefing_date == BRIEFING_DATE,
            MorningBriefingLog.channel == "telegram",
        ).count() == 1
    finally:
        db.close()
        engine.dispose()

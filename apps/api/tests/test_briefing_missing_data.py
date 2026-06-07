from datetime import date

from models import Factory, User
from services.briefing_service import build_briefing
from tests.briefing_test_utils import make_briefing_db


def test_missing_data_never_hallucinates_zero_null_or_empty_values():
    engine, db = make_briefing_db()
    try:
        db.add(Factory(id=1, name="Empty Briefing Factory", subscription_status="active"))
        owner = User(
            id=1,
            factory_id=1,
            username="empty-owner",
            full_name="Empty Owner",
            password_hash="unused",
            role="Owner",
        )
        db.add(owner)
        db.commit()

        result = build_briefing(db, 1, date(2026, 6, 5), owner.full_name)

        assert len(result["missing_data"]) == 9
        assert result["message_text"].count("Data not available") == 9
        assert "💵 Sales Yesterday\nInvoices: Data not available" in result["message_text"]
        assert "Sales: Data not available" in result["message_text"]
        assert result["risk_items"] == []
        assert ": 0" not in result["message_text"]
        assert "null" not in result["message_text"].lower()
        assert ": \n" not in result["message_text"]
    finally:
        db.close()
        engine.dispose()

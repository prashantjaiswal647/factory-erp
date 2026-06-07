from fastapi.testclient import TestClient

from main import app
from models import ActivityLog
from services.briefing_service import audit_briefing, build_briefing
from tests.briefing_test_utils import BRIEFING_DATE, make_briefing_db, seed_two_factories


def test_briefing_factory_isolation_and_factory_scoped_audits():
    engine, db = make_briefing_db()
    try:
        owner_a, _ = seed_two_factories(db)
        result = build_briefing(db, owner_a.factory_id, BRIEFING_DATE, owner_a.full_name)

        assert result["snapshot"]["production"] == {"produced": 70, "target": 100, "gap": 30}
        assert result["snapshot"]["workers"] == {"present": 1, "absent": 1}
        assert result["snapshot"]["collections"]["received"] == 2500
        assert result["snapshot"]["collections"]["outstanding"] == 125000
        assert result["snapshot"]["sales"]["amount"] == 12000
        assert result["snapshot"]["sales"]["invoice_count"] == 1
        assert result["snapshot"]["risk_summary"] == {
            "bottom_days_left": 2,
            "blank_days_left": 7,
        }
        assert [item["label"] for item in result["risk_items"]] == [
            "Bottom Roll",
            "Alpha Buyer",
            "Blank Stock",
        ]
        assert "Secret Beta Buyer" not in result["message_text"]
        assert "99,999" not in result["message_text"]
        assert "77,777" not in result["message_text"]
        assert "800" not in result["message_text"]
        assert "900" not in result["message_text"]
        assert "654,321" not in result["message_text"]

        for action in ("GENERATED", "PREVIEWED", "SENT"):
            audit_briefing(db, owner_a.factory_id, owner_a, action, BRIEFING_DATE)
        db.commit()

        audits = db.query(ActivityLog).filter(ActivityLog.entity_type == "morning_briefing").all()
        assert {audit.action_type for audit in audits} == {
            "BRIEFING_GENERATED",
            "BRIEFING_PREVIEWED",
            "BRIEFING_SENT",
        }
        assert {audit.factory_id for audit in audits} == {owner_a.factory_id}
    finally:
        db.close()
        engine.dispose()


def test_briefing_routes_reject_unauthenticated_requests():
    import inspect
    import httpx

    if "app" not in inspect.signature(httpx.Client.__init__).parameters:
        original_init = httpx.Client.__init__

        def patched_init(self, *args, app=None, **kwargs):
            return original_init(self, *args, **kwargs)

        httpx.Client.__init__ = patched_init
    client = TestClient(app)

    assert client.get("/api/briefings/today").status_code == 401
    assert client.post("/api/briefings/preview").status_code == 401
    assert client.post("/api/briefings/send").status_code == 401

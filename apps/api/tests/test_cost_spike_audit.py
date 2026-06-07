from datetime import timedelta

from models import ActivityLog, CostVarianceAlertLog, Factory
from services.briefing_observability import cost_spike_events
from services.cost_scheduler import deliver_cost_spike_alert, render_cost_spike_alert
from services.cost_variance import compute_variance_summary
from tests.test_cost_per_cup import make_db, seed_production
from tests.test_cost_variance import TODAY


def _seed_spike(db, factory_id: int = 1):
    seed_production(db, factory_id, TODAY - timedelta(days=1), boxes=1, material="100", labour="50", electricity="25")
    seed_production(db, factory_id, TODAY, boxes=1, material="200", labour="50", electricity="25")
    return compute_variance_summary(db, factory_id, TODAY)


def test_successful_spike_alert_creates_structured_activity_log_once():
    engine, db = make_db()
    try:
        summary = _seed_spike(db)
        factory = db.get(Factory, 1)
        first, first_sent = deliver_cost_spike_alert(db, factory, summary, language="en", sender=lambda *_: None)
        second, second_sent = deliver_cost_spike_alert(db, factory, summary, language="en", sender=lambda *_: None)

        assert first_sent is True
        assert second_sent is False
        assert second.id == first.id
        activities = db.query(ActivityLog).filter_by(action_type="COST_SPIKE_DETECTED").all()
        assert len(activities) == 1
        activity = activities[0]
        assert activity.factory_id == 1
        assert activity.entity_type == "daily_variance_snapshot"
        assert activity.entity_id == summary["snapshot_id"]
        assert activity.metadata_json == {
            "today_cpc": summary["today_cpc"],
            "seven_day_cpc": summary["seven_day_cpc"],
            "variance_percent": summary["variance_percent"],
            "primary_driver": summary["primary_driver"],
        }
    finally:
        db.close()
        engine.dispose()


def test_cost_spike_observability_is_factory_scoped_when_filtered():
    engine, db = make_db()
    try:
        summary_a = _seed_spike(db, 1)
        summary_b = _seed_spike(db, 2)
        deliver_cost_spike_alert(db, db.get(Factory, 1), summary_a, sender=lambda *_: None)
        deliver_cost_spike_alert(db, db.get(Factory, 2), summary_b, sender=lambda *_: None)

        result = cost_spike_events(db, page=1, page_size=25, factory_id=1)
        assert result["total"] == 1
        assert result["items"][0]["factory_id"] == 1
        assert result["items"][0]["factory_name"] == "Cost Factory 1"
        assert result["items"][0]["primary_driver"] == summary_a["primary_driver"]
    finally:
        db.close()
        engine.dispose()


def test_cost_spike_alert_language_rendering():
    summary = {
        "today_cpc": "0.5800",
        "seven_day_cpc": "0.5300",
        "variance_percent": "+9.4000",
        "primary_driver": "Material Cost",
    }
    english = render_cost_spike_alert(summary, "en")
    hindi = render_cost_spike_alert(summary, "hi")
    hinglish = render_cost_spike_alert(summary, "hinglish")

    assert "Cost Spike Alert" in english
    assert "Primary Driver:\nMaterial Cost" in english
    assert "लागत बढ़ने की चेतावनी" in hindi
    assert "मुख्य कारण:\nसामग्री लागत" in hindi
    assert "7 Din ka Average" in hinglish
    assert "Mukhya Karan:\nMaterial Cost" in hinglish


def test_variance_api_payload_contains_bar_chart_driver_data():
    engine, db = make_db()
    try:
        summary = _seed_spike(db)
        assert {
            "material_change_percent",
            "labour_change_percent",
            "electricity_change_percent",
            "overhead_change_percent",
        }.issubset(summary)
    finally:
        db.close()
        engine.dispose()


def test_failed_alert_does_not_create_cost_spike_activity():
    engine, db = make_db()
    try:
        summary = _seed_spike(db)
        factory = db.get(Factory, 1)

        def fail(*_):
            raise RuntimeError("delivery failed")

        row, sent = deliver_cost_spike_alert(db, factory, summary, sender=fail)
        assert sent is False
        assert row.status == "failed"
        assert db.query(CostVarianceAlertLog).count() == 1
        assert db.query(ActivityLog).filter_by(action_type="COST_SPIKE_DETECTED").count() == 0
    finally:
        db.close()
        engine.dispose()

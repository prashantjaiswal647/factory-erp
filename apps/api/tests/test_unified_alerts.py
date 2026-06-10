from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import Factory, UnifiedAlert
from services.unified_alerts import render_briefing_alerts, top_alerts, upsert_alert


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_alert_dedupe_and_severity_escalation():
    db = _session()
    factory = Factory(name="Factory A")
    db.add(factory)
    db.flush()

    first = upsert_alert(
        db, factory_id=factory.id, dedupe_key="cost:2026-06-09",
        title="Cost spike", message="Warning", severity="WARNING", source_module="cost",
    )
    second = upsert_alert(
        db, factory_id=factory.id, dedupe_key="cost:2026-06-09",
        title="Cost spike", message="Critical", severity="CRITICAL", source_module="cost",
    )
    db.commit()

    assert first.id == second.id
    assert db.query(UnifiedAlert).count() == 1
    assert second.severity == "CRITICAL"


def test_top_alerts_are_factory_scoped_and_severity_sorted():
    db = _session()
    first_factory = Factory(name="Factory A")
    second_factory = Factory(name="Factory B")
    db.add_all([first_factory, second_factory])
    db.flush()
    upsert_alert(db, factory_id=first_factory.id, dedupe_key="info", title="Info", message="I", severity="INFO", source_module="inventory")
    critical = upsert_alert(db, factory_id=first_factory.id, dedupe_key="critical", title="Critical", message="C", severity="CRITICAL", source_module="machine")
    upsert_alert(db, factory_id=second_factory.id, dedupe_key="other", title="Other", message="O", severity="CRITICAL", source_module="cost")

    rows = top_alerts(db, first_factory.id, 5)

    assert [row.id for row in rows] == [critical.id, rows[1].id]
    assert all(row.factory_id == first_factory.id for row in rows)


def test_briefing_renders_only_top_three_alerts():
    rows = [
        UnifiedAlert(
            id=index, factory_id=1, dedupe_key=str(index), title=f"Alert {index}",
            message="Message", severity="CRITICAL", status="OPEN", source_module="cost",
            suggested_action="Review", first_detected_at=datetime.now(timezone.utc),
            last_detected_at=datetime.now(timezone.utc),
        )
        for index in range(1, 5)
    ]

    rendered = render_briefing_alerts(rows)

    assert "Alert 1" in rendered
    assert "Alert 3" in rendered
    assert "Alert 4" not in rendered

from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base, get_db
from models import Factory, MorningBriefingLog
from routers.briefing_admin import router
from routers.super_admin import require_super_admin


REPORTING_DATE = date(2026, 6, 14)


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _compatibility_patch():
    import inspect

    if "app" in inspect.signature(httpx.Client.__init__).parameters:
        return
    original = httpx.Client.__init__
    if getattr(original, "_briefing_admin_compatible", False):
        return

    def patched(self, *args, app=None, **kwargs):
        return original(self, *args, **kwargs)

    patched._briefing_admin_compatible = True
    httpx.Client.__init__ = patched


def _app(authenticated: bool) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    if authenticated:
        app.dependency_overrides[require_super_admin] = lambda: "admin@munshiai.co.in"
    return app


def _seed():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    now = datetime.now(timezone.utc)
    today = REPORTING_DATE
    db = SessionLocal()
    db.add_all(
        [
            Factory(
                id=1,
                name="Connected Factory",
                is_active=True,
                telegram_chat_id="chat-1",
                telegram_bot_token="encrypted-or-legacy-token",
            ),
            Factory(id=2, name="Disconnected Factory", is_active=True),
            Factory(id=3, name="No Delivery Factory", is_active=True),
        ]
    )
    db.add_all(
        [
            MorningBriefingLog(
                factory_id=1,
                briefing_date=today,
                generated_at=now,
                sent_at=now,
                message_text="sent",
                status="sent",
                channel="telegram",
                retry_count=0,
            ),
            MorningBriefingLog(
                factory_id=1,
                briefing_date=today - timedelta(days=2),
                generated_at=now - timedelta(days=2),
                message_text="failed",
                status="failed",
                channel="telegram",
                error_message="attempt 3/3: connection failed",
                retry_count=3,
            ),
            MorningBriefingLog(
                factory_id=2,
                briefing_date=today - timedelta(days=8),
                generated_at=now - timedelta(days=8),
                sent_at=now - timedelta(days=8),
                message_text="sent old",
                status="sent",
                channel="telegram",
                retry_count=1,
            ),
        ]
    )
    db.commit()
    db.close()


@pytest.fixture(autouse=True)
def isolated_briefing_data(monkeypatch):
    _compatibility_patch()
    monkeypatch.setattr(
        "services.briefing_observability.get_kolkata_now",
        lambda: datetime(2026, 6, 14, 9, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))),
    )
    _seed()


def test_super_admin_access_only_and_unauthorized_rejected():
    unauthorized = TestClient(_app(authenticated=False))
    assert unauthorized.get("/api/admin/briefings/overview").status_code == 401
    assert unauthorized.get("/api/admin/briefings/logs").status_code == 401
    assert unauthorized.get("/api/admin/briefings/factory-health").status_code == 401
    assert unauthorized.get("/api/admin/briefings/cost-spikes").status_code == 401


def test_overview_metrics_and_failure_aggregation():
    response = TestClient(_app(authenticated=True)).get("/api/admin/briefings/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_factories"] == 3
    assert payload["telegram_connected_factories"] == 1
    assert payload["active_briefing_factories"] == 2
    assert payload["delivery_success_rate"] == 66.67
    assert payload["delivery_failure_rate"] == 33.33
    assert payload["metrics"]["today_sent"] == 1
    assert payload["metrics"]["seven_day_failed"] == 1
    assert payload["metrics"]["thirty_day_sent"] == 2
    assert payload["last_failed_delivery"]["factory_name"] == "Connected Factory"


def test_logs_pagination_filters_and_sanitized_failure_fields():
    client = TestClient(_app(authenticated=True))
    first_page = client.get("/api/admin/briefings/logs?page=1&page_size=2")
    assert first_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert len(first_page.json()["items"]) == 2
    assert first_page.json()["pages"] == 2

    failed = client.get("/api/admin/briefings/logs?factory_id=1&status=failed")
    item = failed.json()["items"][0]
    assert failed.json()["total"] == 1
    assert item["status"] == "failed"
    assert item["retry_count"] == 3
    assert item["error_message"] == "attempt 3/3: connection failed"
    assert "token" not in item


def test_factory_health_metrics_and_pagination():
    response = TestClient(_app(authenticated=True)).get(
        "/api/admin/briefings/factory-health?page=1&page_size=2"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["pages"] == 2
    connected = next(item for item in payload["items"] if item["factory_id"] == 1)
    assert connected["telegram_connected"] is True
    assert connected["delivery_percent"] == 50.0
    assert connected["seven_day_success_percent"] == 50.0
    assert connected["thirty_day_success_percent"] == 50.0

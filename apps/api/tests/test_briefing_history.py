import inspect
from datetime import datetime, timedelta, timezone, date
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import get_current_user
from db import Base, get_db
from models import Factory, User, TelegramUserBinding, BriefingSnapshot
from routers.briefings import router as briefings_router
from routers.integrations import router as integrations_router
from services.briefing_recovery_merge import compose_daily_briefing_with_recovery


@pytest.fixture()
def history_app(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-bot-token")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "MunshiHermesAi_Bot")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "webhook-secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "telegram-test-encryption-key-that-is-long-enough")

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add_all([
        Factory(id=1, name="Factory A", subscription_status="active", telegram_bot_token="123456:test-bot-token"),
        Factory(id=2, name="Factory B", subscription_status="active", telegram_bot_token="123456:test-bot-token"),
    ])
    db.flush()
    db.add_all([
        User(id=11, factory_id=1, username="owner-a", password_hash="x", role="Owner", is_active=True),
        User(id=12, factory_id=1, username="sub-owner-a", password_hash="x", role="Sub-Owner", is_active=True),
        User(id=22, factory_id=2, username="owner-b", password_hash="x", role="Owner", is_active=True),
    ])
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(briefings_router)
    app.include_router(integrations_router)
    active_user_id = {"value": 11}

    def override_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_user():
        session = SessionLocal()
        try:
            user = session.query(User).filter(User.id == active_user_id["value"]).one()
            session.expunge(user)
            return user
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    client = TestClient(app)
    try:
        yield client, SessionLocal, active_user_id
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_briefing_snapshot_saved_and_prevents_duplicates(history_app):
    client, SessionLocal, _ = history_app
    db = SessionLocal()

    # Stub the build_briefing logic or run compose directly
    # compose_daily_briefing_with_recovery stores BriefingSnapshot inside the database.
    owner = db.query(User).filter(User.id == 11).one()
    
    with patch("services.briefing_recovery_merge.collect_recovery_snapshot") as mock_rec, \
         patch("services.briefing_service.build_briefing") as mock_brief:
        mock_rec.return_value = {
            "yesterday_collections_paise": 3200000,
            "total_outstanding_paise": 124000000,
            "overdue_outstanding_paise": 80000000,
            "top_due_customer_name": "Customer X",
            "top_due_amount_paise": 5000000,
            "top_due_days_old": 18,
            "high_risk_customers_count": 2,
        }
        mock_brief.return_value = {
            "message_text": "Owner Daily Briefing Content",
            "snapshot": {
                "factory_health": {"overall_score": 82},
                "production": {"total_boxes": 100},
                "sales": {"amount": 50000.0, "outstanding_amount": 1240000.0},
            }
        }
        
        # 1. First generation saves BriefingSnapshot
        compose_daily_briefing_with_recovery(db, 1, date(2026, 6, 9), owner)
        
        # 2. Check saved snapshot
        snaps = db.query(BriefingSnapshot).filter(BriefingSnapshot.factory_id == 1).all()
        assert len(snaps) == 1
        assert snaps[0].health_score == 82
        assert snaps[0].role == "Owner"
        assert "Owner Daily Briefing Content" in snaps[0].message_text
        
        # 3. Duplicate same-date briefing does not create duplicates
        compose_daily_briefing_with_recovery(db, 1, date(2026, 6, 9), owner)
        snaps_dup = db.query(BriefingSnapshot).filter(BriefingSnapshot.factory_id == 1).all()
        assert len(snaps_dup) == 1


def test_history_api_returns_last_30_days_and_respects_roles(history_app):
    client, SessionLocal, active_user_id = history_app
    db = SessionLocal()
    
    # Pre-populate history snapshots
    for offset in range(35):
        s_date = date.today() - timedelta(days=offset)
        db.add(BriefingSnapshot(
            factory_id=1,
            user_id=11,
            role="Owner",
            briefing_date=s_date,
            message_text=f"Briefing {offset}",
            snapshot_json={
                "snapshot": {
                    "production": {"total_boxes": 100 + offset},
                    "sales": {"amount": 5000.0, "outstanding_amount": 10000.0},
                },
                "recovery_snapshot": {"yesterday_collections_paise": 500000}
            },
            health_score=80.0
        ))
    db.commit()

    # 1. Retrieve history as Owner - should see financial fields
    active_user_id["value"] = 11
    response = client.get("/api/briefings/history?days=30")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 31  # 0 to 30 days inclusive of s_date
    assert data[0]["health_score"] == 80.0
    assert data[0]["production_total"] == 100
    assert data[0]["sales_total"] == 5000.0
    assert data[0]["collections_total"] == 5000.0
    assert data[0]["outstanding_total"] == 10000.0
    
    # 2. Retrieve history as Sub-Owner - should have financial fields masked (None)
    active_user_id["value"] = 12
    # Create Sub-Owner snapshots as well
    for offset in range(5):
        s_date = date.today() - timedelta(days=offset)
        db.add(BriefingSnapshot(
            factory_id=1,
            user_id=12,
            role="Sub-Owner",
            briefing_date=s_date,
            message_text=f"Briefing Sub {offset}",
            snapshot_json={
                "snapshot": {
                    "production": {"total_boxes": 50 + offset},
                }
            },
            health_score=75.0
        ))
    db.commit()
    db.close()
    
    response_sub = client.get("/api/briefings/history?days=30")
    assert response_sub.status_code == 200
    data_sub = response_sub.json()
    assert len(data_sub) == 5
    assert data_sub[0]["role_version"] == "Sub-Owner"
    assert data_sub[0]["production_total"] == 50
    assert data_sub[0]["sales_total"] is None
    assert data_sub[0]["collections_total"] is None
    assert data_sub[0]["outstanding_total"] is None


def test_briefing_detail_api_works_and_enforces_roles_and_isolation(history_app):
    client, SessionLocal, active_user_id = history_app
    db = SessionLocal()
    
    # Setup test snapshots
    s1 = BriefingSnapshot(
        id=1001,
        factory_id=1,
        user_id=11,
        role="Owner",
        briefing_date=date(2026, 6, 9),
        message_text="Owner details",
        snapshot_json={"snapshot": {"sales": {"amount": 10000.0}}},
        health_score=90.0
    )
    s2 = BriefingSnapshot(
        id=1002,
        factory_id=1,
        user_id=12,
        role="Sub-Owner",
        briefing_date=date(2026, 6, 9),
        message_text="Sub-owner details",
        snapshot_json={"snapshot": {"sales": {"amount": 10000.0}}},
        health_score=85.0
    )
    s3 = BriefingSnapshot(
        id=1003,
        factory_id=2,
        user_id=22,
        role="Owner",
        briefing_date=date(2026, 6, 9),
        message_text="Cross factory details",
        snapshot_json={"snapshot": {"sales": {"amount": 10000.0}}},
        health_score=95.0
    )
    db.add_all([s1, s2, s3])
    db.commit()
    db.close()

    # 1. Owner requests owner briefing detail
    active_user_id["value"] = 11
    res1 = client.get("/api/briefings/history/1001")
    assert res1.status_code == 200
    assert res1.json()["snapshot_json"]["snapshot"]["sales"]["amount"] == 10000.0

    # 2. Owner requests cross factory briefing detail -> Forbidden
    res2 = client.get("/api/briefings/history/1003")
    assert res2.status_code == 403

    # 3. Sub-Owner requests sub-owner briefing detail -> Masks financial details
    active_user_id["value"] = 12
    res3 = client.get("/api/briefings/history/1002")
    assert res3.status_code == 200
    details = res3.json()
    assert details["snapshot_json"]["snapshot"]["sales"]["amount"] is None

    # 4. Sub-Owner requests Owner briefing detail -> Forbidden
    res4 = client.get("/api/briefings/history/1001")
    assert res4.status_code == 403


def test_telegram_history_button_callback(history_app):
    client, SessionLocal, active_user_id = history_app
    db = SessionLocal()
    
    # 1. Bind Owner and setup historical snapshots
    db.add(TelegramUserBinding(
        user_id=11,
        factory_id=1,
        role="Owner",
        telegram_chat_id="chat-owner-history",
        telegram_username="owner_history",
        is_active=True
    ))
    db.add(BriefingSnapshot(
        factory_id=1,
        user_id=11,
        role="Owner",
        briefing_date=date(2026, 6, 9),
        message_text="Test Owner Briefing 1",
        snapshot_json={
            "snapshot": {
                "production": {"total_boxes": 100},
                "sales": {"outstanding_amount": 1240000.0},
            },
            "recovery_snapshot": {"yesterday_collections_paise": 3200000}
        },
        health_score=82.0
    ))
    db.add(BriefingSnapshot(
        factory_id=1,
        user_id=11,
        role="Owner",
        briefing_date=date(2026, 6, 8),
        message_text="Test Owner Briefing 2",
        snapshot_json={
            "snapshot": {
                "production": {"total_boxes": 120},
                "sales": {"outstanding_amount": 1280000.0},
            },
            "recovery_snapshot": {"yesterday_collections_paise": 1800000}
        },
        health_score=76.0
    ))
    db.commit()
    db.close()

    # Invoke Callback
    response = client.post(
        "/api/integrations/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "webhook-secret"},
        json={
            "update_id": 9991,
            "callback_query": {
                "id": "callback-hist",
                "data": "owner_briefing_history",
                "message": {"chat": {"id": "chat-owner-history"}},
            },
        },
    )
    assert response.status_code == 200
    msg = response.json()["message"]
    assert "Last 7 briefings summary:" in msg
    assert "09 Jun — Health 82 — Collection ₹32k — Outstanding ₹12.4L" in msg
    assert "08 Jun — Health 76 — Collection ₹18k — Outstanding ₹12.8L" in msg

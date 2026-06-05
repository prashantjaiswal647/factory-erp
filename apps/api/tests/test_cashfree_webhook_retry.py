import asyncio
import base64
import hashlib
import hmac
import json
import time

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import CashfreeWebhookEvent
from routers import payments_webhook_cashfree


def make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def make_request(payload: dict, secret: str) -> Request:
    body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = base64.b64encode(
        hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).digest()
    ).decode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/payments/webhook/cashfree",
            "headers": [
                (b"x-webhook-timestamp", timestamp.encode()),
                (b"x-webhook-signature", signature.encode()),
            ],
        },
        receive,
    )


def deliver_existing_event(monkeypatch, existing_status: str):
    db = make_db()
    secret = "test-cashfree-secret"
    monkeypatch.setenv("CASHFREE_WEBHOOK_SECRET", secret)
    event_id = f"event-{existing_status}"
    db.add(
        CashfreeWebhookEvent(
            cf_event_id=event_id,
            cf_event_type="OLD_EVENT",
            payload={"old": True},
            signature="old-signature",
            status=existing_status,
            error_message="previous failure",
        )
    )
    db.commit()
    processed = []

    def process_event(session, event_type, payload):
        processed.append((event_type, payload))
        return {"factory_id": None}

    monkeypatch.setattr(
        payments_webhook_cashfree, "process_cashfree_event", process_event
    )
    payload = {
        "type": "SUBSCRIPTION_STATUS_CHANGED",
        "data": {"event_id": event_id},
    }
    result = asyncio.run(
        payments_webhook_cashfree.cashfree_webhook(
            make_request(payload, secret),
            db,
        )
    )
    db.expire_all()
    event = (
        db.query(CashfreeWebhookEvent)
        .filter(CashfreeWebhookEvent.cf_event_id == event_id)
        .one()
    )
    return db, result, event, processed, payload


def test_failed_webhook_event_is_retried_and_processed(monkeypatch):
    db, result, event, processed, payload = deliver_existing_event(
        monkeypatch, "failed"
    )
    try:
        assert result == {"ok": True, "factory_id": None}
        assert processed == [("SUBSCRIPTION_STATUS_CHANGED", payload)]
        assert event.status == "processed"
        assert event.error_message is None
        assert event.processed_at is not None
    finally:
        db.close()


def test_received_webhook_event_is_retried_and_processed(monkeypatch):
    db, result, event, processed, payload = deliver_existing_event(
        monkeypatch, "received"
    )
    try:
        assert result == {"ok": True, "factory_id": None}
        assert processed == [("SUBSCRIPTION_STATUS_CHANGED", payload)]
        assert event.status == "processed"
        assert event.error_message is None
        assert event.processed_at is not None
    finally:
        db.close()


def test_processed_webhook_event_is_duplicate_without_reprocessing(monkeypatch):
    db, result, event, processed, _ = deliver_existing_event(
        monkeypatch, "processed"
    )
    try:
        assert result == {"ok": True, "duplicate": True}
        assert processed == []
        assert event.status == "processed"
        assert event.error_message == "previous failure"
    finally:
        db.close()

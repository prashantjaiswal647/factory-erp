import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db import get_db
from models import CashfreeWebhookEvent
from payments.signing import get_webhook_secret, verify_cashfree_signature
from payments.webhook_handler import process_cashfree_event


router = APIRouter(prefix="/api/v1/payments/webhook", tags=["payments-webhook"])


@router.post("/cashfree")
async def cashfree_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("x-webhook-signature", "")
    timestamp = request.headers.get("x-webhook-timestamp", "")
    try:
        secret = get_webhook_secret()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="Webhook is not configured") from exc
    if not verify_cashfree_signature(raw_body, signature, timestamp, secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    event_id = payload.get("event_id") or data.get("event_id")
    if not event_id:
        raise HTTPException(status_code=400, detail="Cashfree event_id is required")
    event_type = str(payload.get("type") or data.get("event_type") or "")
    event_id = str(event_id)
    event = (
        db.query(CashfreeWebhookEvent)
        .filter(CashfreeWebhookEvent.cf_event_id == event_id)
        .first()
    )
    if event is not None and event.status == "processed":
        return {"ok": True, "duplicate": True}

    if event is None:
        event = CashfreeWebhookEvent(
            cf_event_id=event_id,
            cf_event_type=event_type or None,
            payload=payload,
            signature=signature,
            status="received",
        )
        try:
            db.add(event)
            db.commit()
        except IntegrityError:
            db.rollback()
            event = (
                db.query(CashfreeWebhookEvent)
                .filter(CashfreeWebhookEvent.cf_event_id == event_id)
                .one()
            )
            if event.status == "processed":
                return {"ok": True, "duplicate": True}
    if event.status != "received" or event.error_message is not None:
        event.status = "received"
        event.error_message = None
        event.processed_at = None
    event.cf_event_type = event_type or None
    event.payload = payload
    event.signature = signature
    db.commit()
    try:
        result = process_cashfree_event(db, event_type, payload)
        event = db.query(CashfreeWebhookEvent).filter(
            CashfreeWebhookEvent.cf_event_id == event_id
        ).one()
        event.status = "processed"
        event.processed_at = datetime.now(timezone.utc)
        event.factory_id = result["factory_id"]
        db.commit()
        return {"ok": True, **result}
    except Exception as exc:
        db.rollback()
        failed = db.query(CashfreeWebhookEvent).filter(
            CashfreeWebhookEvent.cf_event_id == event_id
        ).one()
        failed.status = "failed"
        failed.error_message = str(exc)[:2000]
        db.commit()
        raise HTTPException(status_code=500, detail="Webhook processing failed") from exc

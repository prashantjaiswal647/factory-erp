from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, time as time_value, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db import SessionLocal
from models import ActivityLog, Factory, MorningBriefingLog, TelegramUserBinding, User
from services.briefing_service import audit_briefing, build_briefing
from services.unified_alerts import sync_factory_alerts
from services.telegram_delivery import send_telegram_message
from services.timezone_utils import KOLKATA_ZONE, get_kolkata_now


logger = logging.getLogger(__name__)
DEFAULT_RETRIES = 3
FAILURE_ALERT_ACTION = "BRIEFING_SEND_FAILED"


def _owner_for_factory(db: Session, factory_id: int) -> User | None:
    return (
        db.query(User)
        .filter(User.factory_id == factory_id, User.role == "Owner", User.is_active.is_(True))
        .order_by(User.id.asc())
        .first()
    )


def _record_skipped_log(db: Session, factory: Factory, briefing_date: date, reason: str) -> MorningBriefingLog:
    row = (
        db.query(MorningBriefingLog)
        .filter(
            MorningBriefingLog.factory_id == factory.id,
            MorningBriefingLog.briefing_date == briefing_date,
            MorningBriefingLog.channel == "telegram",
        )
        .with_for_update()
        .first()
    )
    if row is None:
        row = MorningBriefingLog(
            factory_id=factory.id,
            briefing_date=briefing_date,
            message_text="Morning briefing was not generated.",
            status="skipped",
            channel="telegram",
            error_message=reason[:500],
            retry_count=0,
        )
        db.add(row)
    elif row.status != "sent":
        row.status = "skipped"
        row.error_message = reason[:500]
    db.commit()
    db.refresh(row)
    return row


def _claim_log(db: Session, factory: Factory, owner: User, briefing_date: date) -> tuple[MorningBriefingLog, bool]:
    existing = (
        db.query(MorningBriefingLog)
        .filter(
            MorningBriefingLog.factory_id == factory.id,
            MorningBriefingLog.briefing_date == briefing_date,
            MorningBriefingLog.channel == "telegram",
        )
        .with_for_update()
        .first()
    )
    if existing is not None:
        return existing, False

    briefing = build_briefing(
        db,
        factory.id,
        briefing_date,
        owner.full_name or owner.username,
        owner.preferred_language,
        summary_mode=True,
    )
    row = MorningBriefingLog(
        factory_id=factory.id,
        briefing_date=briefing_date,
        message_text=briefing["message_text"],
        status="generated",
        channel="telegram",
    )
    db.add(row)
    audit_briefing(db, factory.id, owner, "GENERATED", briefing_date)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        row = (
            db.query(MorningBriefingLog)
            .filter(
                MorningBriefingLog.factory_id == factory.id,
                MorningBriefingLog.briefing_date == briefing_date,
                MorningBriefingLog.channel == "telegram",
            )
            .with_for_update()
            .one()
        )
        return row, False
    return row, True


def _create_failure_alert(
    db: Session,
    factory: Factory,
    owner: User,
    row: MorningBriefingLog,
) -> ActivityLog:
    existing = (
        db.query(ActivityLog)
        .filter(
            ActivityLog.factory_id == factory.id,
            ActivityLog.action_type == FAILURE_ALERT_ACTION,
            ActivityLog.entity_type == "morning_briefing",
            ActivityLog.entity_id == row.id,
        )
        .first()
    )
    if existing is not None:
        return existing

    safe_error = (row.error_message or "Unknown delivery error")[:500]
    summary = (
        f"Morning briefing send failed for factory_id={factory.id}, "
        f"briefing_date={row.briefing_date.isoformat()}, channel={row.channel}"
    )
    alert = ActivityLog(
        factory_id=factory.id,
        event_type="super_admin_alert",
        description=f"{summary}. Error: {safe_error}",
        log_date=date.today(),
        user_id=owner.id,
        user_name=owner.full_name or owner.username,
        user_role=owner.role,
        action_type=FAILURE_ALERT_ACTION,
        action_summary=summary,
        entity_type="morning_briefing",
        entity_id=row.id,
        short_statement=summary,
        committed_at=datetime.now(KOLKATA_ZONE),
    )
    db.add(alert)
    db.flush()
    return alert


def deliver_factory_briefing(
    db: Session,
    factory: Factory,
    owner: User,
    briefing_date: date,
    *,
    max_retries: int = DEFAULT_RETRIES,
    sender=send_telegram_message,
) -> tuple[MorningBriefingLog, bool]:
    sync_factory_alerts(db, factory.id, today=briefing_date, send_critical=True)
    row, _ = _claim_log(db, factory, owner, briefing_date)
    if row.status == "sent":
        db.commit()
        return row, False

    for attempt in range(1, max(1, max_retries) + 1):
        try:
            sender(factory, row.message_text)
            row.status = "sent"
            row.sent_at = datetime.now(KOLKATA_ZONE)
            row.error_message = None
            row.retry_count = attempt - 1
            audit_briefing(db, factory.id, owner, "SENT", briefing_date)
            db.commit()
            db.refresh(row)
            return row, True
        except Exception as exc:
            row.status = "failed"
            row.retry_count = attempt
            row.error_message = f"attempt {attempt}/{max_retries}: {str(exc)[:500]}"
            db.flush()
            retryable = getattr(exc, "retryable", True)
            if retryable and attempt < max_retries:
                time.sleep(min(attempt * 2, 5))
            else:
                break

    _create_failure_alert(db, factory, owner, row)
    logger.error(
        "Morning briefing send failed factory_id=%s date=%s channel=%s attempts=%s",
        factory.id,
        briefing_date,
        row.channel,
        max(1, max_retries),
    )
    db.commit()
    db.refresh(row)
    return row, False


def run_daily_briefing_batch(
    briefing_date: date | None = None,
    *,
    session_factory=SessionLocal,
    max_retries: int | None = None,
    sender=send_telegram_message,
) -> dict[str, int]:
    target_date = briefing_date or (get_kolkata_now().date() - timedelta(days=1))
    retry_limit = max_retries or int(os.getenv("MORNING_BRIEFING_MAX_RETRIES", str(DEFAULT_RETRIES)))
    metrics = {"total_factories": 0, "sent": 0, "failed": 0}

    db = session_factory()
    try:
        factories = db.query(Factory).filter(Factory.is_active.is_(True)).order_by(Factory.id.asc()).all()
        metrics["total_factories"] = len(factories)
        for factory in factories:
            owner = _owner_for_factory(db, factory.id)
            if owner is None:
                _record_skipped_log(db, factory, target_date, "Active factory owner not found")
                metrics["failed"] += 1
                logger.warning("Morning briefing skipped for factory_id=%s: active owner not found", factory.id)
                continue
            try:
                row, sent_now = deliver_factory_briefing(
                    db,
                    factory,
                    owner,
                    target_date,
                    max_retries=retry_limit,
                    sender=sender,
                )
                if row.status == "sent":
                    metrics["sent"] += 1
                else:
                    metrics["failed"] += 1
                if not sent_now and row.status == "sent":
                    logger.info("Morning briefing already sent factory_id=%s date=%s", factory.id, target_date)
            except Exception:
                db.rollback()
                metrics["failed"] += 1
                logger.exception("Morning briefing failed factory_id=%s date=%s", factory.id, target_date)

            # P4.5 D3: Sub-Owner operational briefing (separate channel,
            # separate row in MorningBriefingLog keyed by recipient).
            try:
                from services.briefing_recovery_merge import (
                    compose_daily_briefing_with_recovery,
                )
                from services.telegram_delivery import send_telegram_message as _sender

                subowner_bindings = (
                    db.query(TelegramUserBinding)
                    .filter(
                        TelegramUserBinding.factory_id == factory.id,
                        TelegramUserBinding.role == "Sub-Owner",
                        TelegramUserBinding.is_active.is_(True),
                    )
                    .all()
                )
                for binding in subowner_bindings:
                    subowner = (
                        db.query(User).filter(User.id == binding.user_id).first()
                    )
                    if subowner is None or not subowner.is_active:
                        continue
                    result = compose_daily_briefing_with_recovery(
                        db,
                        factory.id,
                        target_date,
                        subowner,
                    )
                    # Use a per-recipient log key to avoid dedup collision
                    # with the Owner's morning_briefing_log row.
                    sub_log = (
                        db.query(MorningBriefingLog)
                        .filter(
                            MorningBriefingLog.factory_id == factory.id,
                            MorningBriefingLog.briefing_date == target_date,
                            MorningBriefingLog.channel == "telegram_subowner",
                        )
                        .with_for_update()
                        .first()
                    )
                    if sub_log is not None and sub_log.status == "sent":
                        continue
                    if sub_log is None:
                        sub_log = MorningBriefingLog(
                            factory_id=factory.id,
                            briefing_date=target_date,
                            message_text=result["message_text"],
                            status="generated",
                            channel="telegram_subowner",
                        )
                        db.add(sub_log)
                    else:
                        sub_log.message_text = result["message_text"]
                    db.commit()
                    # Direct send to the Sub-Owner's chat_id. Use the
                    # existing sender with a one-off chat_id override.
                    class _FactoryProxy:
                        pass
                    proxy = _FactoryProxy()
                    proxy.id = factory.id
                    proxy.telegram_chat_id = binding.telegram_chat_id
                    try:
                        _sender(proxy, result["message_text"])
                        sub_log.status = "sent"
                        sub_log.sent_at = datetime.now(KOLKATA_ZONE)
                        sub_log.retry_count = 0
                        db.commit()
                        metrics["sent"] += 1
                    except Exception:
                        sub_log.status = "failed"
                        sub_log.retry_count = 1
                        db.commit()
                        logger.warning(
                            "sub-owner briefing send failed factory_id=%s subowner_id=%s",
                            factory.id,
                            subowner.id,
                        )
            except Exception:
                db.rollback()
                logger.exception(
                    "Sub-owner briefing dispatch failed factory_id=%s",
                    factory.id,
                )

        logger.info("Morning briefing batch metrics=%s date=%s", metrics, target_date)
        return metrics
    finally:
        db.close()


def seconds_until_next_run(now: datetime | None = None) -> float:
    current = now or get_kolkata_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=KOLKATA_ZONE)
    next_run = datetime.combine(current.date(), time_value(hour=7), tzinfo=KOLKATA_ZONE)
    if current >= next_run:
        next_run += timedelta(days=1)
    return max((next_run - current).total_seconds(), 1.0)


def run_scheduler_forever() -> None:
    logger.info("Morning briefing scheduler started timezone=Asia/Kolkata schedule=07:00")
    while True:
        delay = seconds_until_next_run()
        logger.info("Next morning briefing batch in %.0f seconds", delay)
        time.sleep(delay)
        try:
            run_daily_briefing_batch()
        except Exception:
            logger.exception("Morning briefing scheduler batch crashed")


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run_scheduler_forever()

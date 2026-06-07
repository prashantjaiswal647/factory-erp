from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, time as time_value, timedelta

from sqlalchemy.exc import IntegrityError

from db import SessionLocal
from models import Factory, User, WeeklyDigestLog
from services.telegram_delivery import send_telegram_message
from services.timezone_utils import KOLKATA_ZONE, get_kolkata_now
from services.weekly_profit_digest import build_weekly_digest, week_range


logger = logging.getLogger(__name__)


def deliver_weekly_digest(db, factory: Factory, owner: User, report_date: date, *, sender=send_telegram_message):
    week_start, week_end = week_range(report_date)
    existing = (
        db.query(WeeklyDigestLog)
        .filter(WeeklyDigestLog.factory_id == factory.id, WeeklyDigestLog.week_start == week_start)
        .first()
    )
    if existing is not None:
        return existing, False
    row = WeeklyDigestLog(factory_id=factory.id, week_start=week_start, week_end=week_end)
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return (
            db.query(WeeklyDigestLog)
            .filter(WeeklyDigestLog.factory_id == factory.id, WeeklyDigestLog.week_start == week_start)
            .one(),
            False,
        )
    digest = build_weekly_digest(db, factory.id, report_date, owner.preferred_language)
    try:
        sender(factory, digest["message_text"])
        row.message_sent = True
        row.sent_at = datetime.now(KOLKATA_ZONE)
        row.error_message = None
        db.commit()
        db.refresh(row)
        return row, True
    except Exception as exc:
        row.error_message = str(exc)[:500]
        db.commit()
        logger.exception("Weekly digest failed factory_id=%s week_start=%s", factory.id, week_start)
        return row, False


def run_weekly_digest_batch(
    report_date: date | None = None,
    *,
    session_factory=SessionLocal,
    sender=send_telegram_message,
) -> dict[str, int]:
    target_date = report_date or get_kolkata_now().date()
    metrics = {"total_factories": 0, "sent": 0, "failed": 0}
    db = session_factory()
    try:
        factories = db.query(Factory).filter(Factory.is_active.is_(True)).order_by(Factory.id.asc()).all()
        metrics["total_factories"] = len(factories)
        for factory in factories:
            owner = (
                db.query(User)
                .filter(User.factory_id == factory.id, User.role == "Owner", User.is_active.is_(True))
                .order_by(User.id.asc())
                .first()
            )
            if owner is None:
                metrics["failed"] += 1
                continue
            try:
                row, _ = deliver_weekly_digest(db, factory, owner, target_date, sender=sender)
                metrics["sent" if row.message_sent else "failed"] += 1
            except Exception:
                db.rollback()
                metrics["failed"] += 1
                logger.exception("Weekly digest batch failed factory_id=%s", factory.id)
        logger.info("Weekly digest metrics=%s report_date=%s", metrics, target_date)
        return metrics
    finally:
        db.close()


def seconds_until_next_run(now: datetime | None = None) -> float:
    current = now or get_kolkata_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=KOLKATA_ZONE)
    days_until_sunday = (6 - current.weekday()) % 7
    next_run = datetime.combine(current.date() + timedelta(days=days_until_sunday), time_value(20, 0), tzinfo=KOLKATA_ZONE)
    if current >= next_run:
        next_run += timedelta(days=7)
    return max((next_run - current).total_seconds(), 1.0)


def run_scheduler_forever() -> None:
    logger.info("Weekly digest scheduler started timezone=Asia/Kolkata schedule=Sunday 20:00")
    while True:
        delay = seconds_until_next_run()
        logger.info("Next weekly digest batch in %.0f seconds", delay)
        time.sleep(delay)
        try:
            run_weekly_digest_batch()
        except Exception:
            logger.exception("Weekly digest scheduler batch crashed")


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run_scheduler_forever()

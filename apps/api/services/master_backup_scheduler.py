from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import date, datetime, time as time_value, timedelta

from db import SessionLocal
from models import Factory, User
from services.master_backup_email import deliver_master_backup, send_backup_email
from services.timezone_utils import KOLKATA_ZONE, get_kolkata_now


logger = logging.getLogger(__name__)
WEEKLY_RUN_TIME = time_value(20, 30)
MONTHLY_RUN_TIME = time_value(8, 30)


def due_frequencies(now: datetime) -> list[str]:
    due = []
    if now.weekday() == 6 and now.time() >= WEEKLY_RUN_TIME:
        due.append("weekly")
    if now.day == 1 and now.time() >= MONTHLY_RUN_TIME:
        due.append("monthly")
    return due


def run_backup_email_batch(
    frequency: str,
    target_date: date | None = None,
    *,
    session_factory=SessionLocal,
    sender=send_backup_email,
) -> dict[str, int]:
    delivery_date = target_date or get_kolkata_now().date()
    metrics = {"total_factories": 0, "sent": 0, "skipped": 0, "failed": 0}
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
                delivered_now = asyncio.run(
                    deliver_master_backup(
                        db, factory, owner, frequency, delivery_date, sender=sender
                    )
                )
                metrics["sent" if delivered_now else "skipped"] += 1
            except Exception:
                db.rollback()
                metrics["failed"] += 1
                logger.exception(
                    "Master backup email failed factory_id=%s frequency=%s period=%s",
                    factory.id,
                    frequency,
                    delivery_date,
                )
        logger.info("Master backup email metrics=%s frequency=%s", metrics, frequency)
        return metrics
    finally:
        db.close()


def seconds_until_next_check(now: datetime | None = None) -> float:
    current = now or get_kolkata_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=KOLKATA_ZONE)
    next_minute = current.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return max((next_minute - current).total_seconds(), 1.0)


def run_scheduler_forever() -> None:
    logger.info(
        "Master backup email scheduler started timezone=Asia/Kolkata "
        "weekly=Sunday 20:30 monthly=day-1 08:30"
    )
    while True:
        now = get_kolkata_now()
        for frequency in due_frequencies(now):
            try:
                run_backup_email_batch(frequency, now.date())
            except Exception:
                logger.exception("Master backup email scheduler batch crashed frequency=%s", frequency)
        time.sleep(seconds_until_next_check(now))


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run_scheduler_forever()

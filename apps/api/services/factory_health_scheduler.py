from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, time as time_value, timedelta

from db import SessionLocal
from models import Factory
from services.factory_health import compute_factory_health
from services.timezone_utils import KOLKATA_ZONE, get_kolkata_now


logger = logging.getLogger(__name__)


def run_factory_health_batch(snapshot_date: date | None = None, *, session_factory=SessionLocal) -> dict[str, int]:
    target_date = snapshot_date or get_kolkata_now().date()
    metrics = {"total_factories": 0, "computed": 0, "failed": 0}
    db = session_factory()
    try:
        factories = db.query(Factory).filter(Factory.is_active.is_(True)).order_by(Factory.id.asc()).all()
        metrics["total_factories"] = len(factories)
        for factory in factories:
            try:
                compute_factory_health(db, factory.id, target_date)
                db.commit()
                metrics["computed"] += 1
            except Exception:
                db.rollback()
                metrics["failed"] += 1
                logger.exception("Factory health computation failed factory_id=%s date=%s", factory.id, target_date)
        logger.info("Factory health batch metrics=%s date=%s", metrics, target_date)
        return metrics
    finally:
        db.close()


def seconds_until_next_run(now: datetime | None = None) -> float:
    current = now or get_kolkata_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=KOLKATA_ZONE)
    next_run = datetime.combine(current.date(), time_value(hour=23, minute=58), tzinfo=KOLKATA_ZONE)
    if current >= next_run:
        next_run += timedelta(days=1)
    return max((next_run - current).total_seconds(), 1.0)


def run_scheduler_forever() -> None:
    logger.info("Factory health scheduler started timezone=Asia/Kolkata schedule=23:58")
    while True:
        delay = seconds_until_next_run()
        logger.info("Next factory health batch in %.0f seconds", delay)
        time.sleep(delay)
        try:
            run_factory_health_batch()
        except Exception:
            logger.exception("Factory health scheduler batch crashed")


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run_scheduler_forever()

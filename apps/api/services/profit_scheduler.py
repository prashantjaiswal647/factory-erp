from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, time as time_value, timedelta

from sqlalchemy.exc import IntegrityError

from db import SessionLocal
from models import Factory, ProfitAlertLog
from services.profit_intelligence import compute_profit_snapshot, persist_per_size_profit, render_profit_alert, should_send_profit_alert
from services.telegram_delivery import send_telegram_message
from services.timezone_utils import KOLKATA_ZONE, get_kolkata_now
from services.wastage_intelligence import compute_wastage_snapshot


logger = logging.getLogger(__name__)


def deliver_profit_alert(db, factory: Factory, snapshot: dict, *, sender=send_telegram_message) -> tuple[ProfitAlertLog | None, bool]:
    if not should_send_profit_alert(snapshot):
        return None, False
    snapshot_date = date.fromisoformat(snapshot["snapshot_date"])
    existing = (
        db.query(ProfitAlertLog)
        .filter(ProfitAlertLog.factory_id == factory.id, ProfitAlertLog.snapshot_date == snapshot_date)
        .first()
    )
    if existing is not None:
        return existing, False
    row = ProfitAlertLog(
        factory_id=factory.id,
        snapshot_date=snapshot_date,
        status=snapshot["profit_status"],
        message_sent=False,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return (
            db.query(ProfitAlertLog)
            .filter(ProfitAlertLog.factory_id == factory.id, ProfitAlertLog.snapshot_date == snapshot_date)
            .one(),
            False,
        )
    try:
        sender(factory, render_profit_alert(snapshot))
        row.message_sent = True
        db.commit()
        db.refresh(row)
        return row, True
    except Exception:
        db.commit()
        logger.exception("Profit alert failed factory_id=%s date=%s", factory.id, snapshot_date)
        return row, False


def run_profit_batch(
    snapshot_date: date | None = None,
    *,
    session_factory=SessionLocal,
    sender=send_telegram_message,
) -> dict[str, int]:
    target_date = snapshot_date or get_kolkata_now().date()
    metrics = {"total_factories": 0, "computed": 0, "alerts_sent": 0, "failed": 0}
    db = session_factory()
    try:
        factories = db.query(Factory).filter(Factory.is_active.is_(True)).order_by(Factory.id.asc()).all()
        metrics["total_factories"] = len(factories)
        for factory in factories:
            try:
                compute_wastage_snapshot(db, factory.id, target_date)
                snapshot = compute_profit_snapshot(db, factory.id, target_date)
                persist_per_size_profit(db, factory.id, target_date)
                db.commit()
                metrics["computed"] += 1
                _, sent = deliver_profit_alert(db, factory, snapshot, sender=sender)
                if sent:
                    metrics["alerts_sent"] += 1
            except Exception:
                db.rollback()
                metrics["failed"] += 1
                logger.exception("Profit computation failed factory_id=%s date=%s", factory.id, target_date)
        logger.info("Profit batch metrics=%s date=%s", metrics, target_date)
        return metrics
    finally:
        db.close()


def seconds_until_next_run(now: datetime | None = None) -> float:
    current = now or get_kolkata_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=KOLKATA_ZONE)
    next_run = datetime.combine(current.date(), time_value(hour=23, minute=59), tzinfo=KOLKATA_ZONE)
    if current >= next_run:
        next_run += timedelta(days=1)
    return max((next_run - current).total_seconds(), 1.0)


def run_scheduler_forever() -> None:
    logger.info("Profit scheduler started timezone=Asia/Kolkata schedule=23:59")
    while True:
        delay = seconds_until_next_run()
        logger.info("Next profit batch in %.0f seconds", delay)
        time.sleep(delay)
        try:
            run_profit_batch()
        except Exception:
            logger.exception("Profit scheduler batch crashed")


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run_scheduler_forever()

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, time as time_value, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db import SessionLocal
from models import ActivityLog, CostVarianceAlertLog, Factory, User
from services.cost_spike_translations import cost_spike_translations_for
from services.cost_variance import compute_variance_summary, should_send_spike_alert
from services.telegram_delivery import send_telegram_message
from services.timezone_utils import KOLKATA_ZONE, get_kolkata_now


logger = logging.getLogger(__name__)


def render_cost_spike_alert(summary: dict, language: str = "en") -> str:
    labels = cost_spike_translations_for(language)
    driver = labels["drivers"].get(summary["primary_driver"], summary["primary_driver"])
    return "\n".join(
        [
            labels["title"],
            "",
            f"{labels['cost_per_cup']}:",
            f"₹{summary['today_cpc']}",
            "",
            f"{labels['seven_day_average']}:",
            f"₹{summary['seven_day_cpc']}",
            "",
            f"{labels['increase']}:",
            f"{summary['variance_percent'].lstrip('+')}%",
            "",
            f"{labels['primary_driver']}:",
            driver,
        ]
    )


def _record_cost_spike_activity(db: Session, factory: Factory, summary: dict) -> ActivityLog:
    snapshot_id = int(summary["snapshot_id"])
    existing = (
        db.query(ActivityLog)
        .filter(
            ActivityLog.factory_id == factory.id,
            ActivityLog.action_type == "COST_SPIKE_DETECTED",
            ActivityLog.entity_type == "daily_variance_snapshot",
            ActivityLog.entity_id == snapshot_id,
        )
        .first()
    )
    if existing is not None:
        return existing
    statement = (
        f"Cost spike detected: {summary['variance_percent']}% variance, "
        f"primary driver {summary['primary_driver']}"
    )
    row = ActivityLog(
        factory_id=factory.id,
        event_type="cost_variance",
        description=statement,
        log_date=date.fromisoformat(summary["snapshot_date"]),
        action_type="COST_SPIKE_DETECTED",
        action_summary=statement,
        entity_type="daily_variance_snapshot",
        entity_id=snapshot_id,
        short_statement=statement,
        committed_at=datetime.now(KOLKATA_ZONE),
        metadata_json={
            "today_cpc": summary["today_cpc"],
            "seven_day_cpc": summary["seven_day_cpc"],
            "variance_percent": summary["variance_percent"],
            "primary_driver": summary["primary_driver"],
        },
    )
    db.add(row)
    db.flush()
    return row


def deliver_cost_spike_alert(
    db: Session,
    factory: Factory,
    summary: dict,
    *,
    language: str = "hinglish",
    sender=send_telegram_message,
) -> tuple[CostVarianceAlertLog | None, bool]:
    if not should_send_spike_alert(summary):
        return None, False
    snapshot_date = date.fromisoformat(summary["snapshot_date"])
    existing = (
        db.query(CostVarianceAlertLog)
        .filter(
            CostVarianceAlertLog.factory_id == factory.id,
            CostVarianceAlertLog.snapshot_date == snapshot_date,
            CostVarianceAlertLog.channel == "telegram",
        )
        .first()
    )
    if existing is not None:
        if existing.status == "sent":
            _record_cost_spike_activity(db, factory, summary)
            db.commit()
        return existing, False

    row = CostVarianceAlertLog(
        factory_id=factory.id,
        snapshot_date=snapshot_date,
        channel="telegram",
        status="generated",
        message_text=render_cost_spike_alert(summary, language),
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(CostVarianceAlertLog)
            .filter(
                CostVarianceAlertLog.factory_id == factory.id,
                CostVarianceAlertLog.snapshot_date == snapshot_date,
                CostVarianceAlertLog.channel == "telegram",
            )
            .one()
        )
        return existing, False

    try:
        sender(factory, row.message_text)
        row.status = "sent"
        row.sent_at = datetime.now(KOLKATA_ZONE)
        _record_cost_spike_activity(db, factory, summary)
        db.commit()
        db.refresh(row)
        return row, True
    except Exception as exc:
        row.status = "failed"
        row.retry_count = 1
        row.error_message = str(exc)[:500]
        db.commit()
        db.refresh(row)
        logger.error("Cost spike alert failed factory_id=%s date=%s", factory.id, snapshot_date)
        return row, False


def run_nightly_cost_batch(
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
                summary = compute_variance_summary(db, factory.id, target_date)
                db.commit()
                metrics["computed"] += 1
                owner = (
                    db.query(User)
                    .filter(User.factory_id == factory.id, User.role == "Owner", User.is_active.is_(True))
                    .order_by(User.id.asc())
                    .first()
                )
                _, sent = deliver_cost_spike_alert(
                    db,
                    factory,
                    summary,
                    language=owner.preferred_language if owner else "hinglish",
                    sender=sender,
                )
                if sent:
                    metrics["alerts_sent"] += 1
            except Exception:
                db.rollback()
                metrics["failed"] += 1
                logger.exception("Nightly cost processing failed factory_id=%s date=%s", factory.id, target_date)
        logger.info("Nightly cost batch metrics=%s date=%s", metrics, target_date)
        return metrics
    finally:
        db.close()


def seconds_until_next_run(now: datetime | None = None) -> float:
    current = now or get_kolkata_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=KOLKATA_ZONE)
    next_run = datetime.combine(current.date(), time_value(hour=23, minute=55), tzinfo=KOLKATA_ZONE)
    if current >= next_run:
        next_run += timedelta(days=1)
    return max((next_run - current).total_seconds(), 1.0)


def run_scheduler_forever() -> None:
    logger.info("Cost variance scheduler started timezone=Asia/Kolkata schedule=23:55")
    while True:
        delay = seconds_until_next_run()
        logger.info("Next cost variance batch in %.0f seconds", delay)
        time.sleep(delay)
        try:
            run_nightly_cost_batch()
        except Exception:
            logger.exception("Cost variance scheduler batch crashed")


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run_scheduler_forever()

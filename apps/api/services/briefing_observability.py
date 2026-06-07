from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import CostVarianceAlertLog, DailyVarianceSnapshot, Factory, MorningBriefingLog
from services.timezone_utils import get_kolkata_now


DELIVERY_STATUSES = {"sent", "failed"}


def _percentage(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 2) if denominator else 0.0


def _telegram_connected(factory: Factory) -> bool:
    return bool(
        factory.telegram_chat_id
        and (factory.telegram_token or factory.telegram_bot_token)
    )


def delivery_counts(db: Session, start_date: date, end_date: date) -> dict[str, int]:
    rows = (
        db.query(MorningBriefingLog.status, func.count(MorningBriefingLog.id))
        .filter(
            MorningBriefingLog.briefing_date >= start_date,
            MorningBriefingLog.briefing_date <= end_date,
            MorningBriefingLog.status.in_(DELIVERY_STATUSES),
        )
        .group_by(MorningBriefingLog.status)
        .all()
    )
    counts = {status: count for status, count in rows}
    return {"sent": counts.get("sent", 0), "failed": counts.get("failed", 0)}


def briefing_overview(db: Session) -> dict:
    today = get_kolkata_now().date()
    factories = db.query(Factory).order_by(Factory.id).all()
    today_counts = delivery_counts(db, today, today)
    seven_counts = delivery_counts(db, today - timedelta(days=6), today)
    thirty_counts = delivery_counts(db, today - timedelta(days=29), today)
    all_sent = db.query(MorningBriefingLog).filter(MorningBriefingLog.status == "sent").count()
    all_failed = db.query(MorningBriefingLog).filter(MorningBriefingLog.status == "failed").count()
    delivery_total = all_sent + all_failed
    active_since = today - timedelta(days=29)

    last_success = (
        db.query(MorningBriefingLog)
        .filter(MorningBriefingLog.status == "sent")
        .order_by(MorningBriefingLog.sent_at.desc(), MorningBriefingLog.generated_at.desc())
        .first()
    )
    last_failure = (
        db.query(MorningBriefingLog)
        .filter(MorningBriefingLog.status == "failed")
        .order_by(MorningBriefingLog.generated_at.desc())
        .first()
    )
    active_factories = (
        db.query(func.count(func.distinct(MorningBriefingLog.factory_id)))
        .filter(MorningBriefingLog.briefing_date >= active_since)
        .scalar()
        or 0
    )

    def event(row: MorningBriefingLog | None):
        if row is None:
            return None
        factory = db.query(Factory).filter(Factory.id == row.factory_id).first()
        return {
            "factory_id": row.factory_id,
            "factory_name": factory.name if factory else f"Factory {row.factory_id}",
            "briefing_date": row.briefing_date,
            "at": row.sent_at or row.generated_at,
        }

    return {
        "total_factories": len(factories),
        "telegram_connected_factories": sum(1 for factory in factories if _telegram_connected(factory)),
        "active_briefing_factories": active_factories,
        "delivery_success_rate": _percentage(all_sent, delivery_total),
        "delivery_failure_rate": _percentage(all_failed, delivery_total),
        "last_successful_delivery": event(last_success),
        "last_failed_delivery": event(last_failure),
        "metrics": {
            "today_sent": today_counts["sent"],
            "today_failed": today_counts["failed"],
            "seven_day_sent": seven_counts["sent"],
            "seven_day_failed": seven_counts["failed"],
            "thirty_day_sent": thirty_counts["sent"],
            "thirty_day_failed": thirty_counts["failed"],
            "delivery_success_rate": _percentage(all_sent, delivery_total),
        },
    }


def briefing_logs(
    db: Session,
    *,
    page: int,
    page_size: int,
    factory_id: int | None = None,
    briefing_date: date | None = None,
    status: str | None = None,
) -> dict:
    query = db.query(MorningBriefingLog, Factory).join(Factory, Factory.id == MorningBriefingLog.factory_id)
    if factory_id is not None:
        query = query.filter(MorningBriefingLog.factory_id == factory_id)
    if briefing_date is not None:
        query = query.filter(MorningBriefingLog.briefing_date == briefing_date)
    if status is not None:
        query = query.filter(MorningBriefingLog.status == status)
    total = query.count()
    rows = (
        query.order_by(MorningBriefingLog.briefing_date.desc(), MorningBriefingLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [
            {
                "id": log.id,
                "factory_id": log.factory_id,
                "factory_name": factory.name,
                "briefing_date": log.briefing_date,
                "generated_at": log.generated_at,
                "sent_at": log.sent_at,
                "status": log.status,
                "channel": log.channel,
                "error_message": log.error_message,
                "retry_count": log.retry_count,
            }
            for log, factory in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size,
    }


def factory_health(db: Session, *, page: int, page_size: int) -> dict:
    today = get_kolkata_now().date()
    factories_query = db.query(Factory).order_by(Factory.name.asc(), Factory.id.asc())
    total = factories_query.count()
    factories = factories_query.offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for factory in factories:
        logs = (
            db.query(MorningBriefingLog)
            .filter(MorningBriefingLog.factory_id == factory.id)
            .order_by(MorningBriefingLog.briefing_date.desc(), MorningBriefingLog.id.desc())
            .all()
        )
        delivered = [row for row in logs if row.status in DELIVERY_STATUSES]
        sent = [row for row in delivered if row.status == "sent"]

        def period_rate(days: int) -> float:
            start = today - timedelta(days=days - 1)
            period = [row for row in delivered if row.briefing_date >= start]
            return _percentage(sum(1 for row in period if row.status == "sent"), len(period))

        last_sent = next((row for row in logs if row.status == "sent"), None)
        last_failed = next((row for row in logs if row.status == "failed"), None)
        items.append(
            {
                "factory_id": factory.id,
                "factory_name": factory.name,
                "telegram_connected": _telegram_connected(factory),
                "last_briefing_sent": last_sent.sent_at if last_sent else None,
                "last_briefing_failed": last_failed.generated_at if last_failed else None,
                "delivery_percent": _percentage(len(sent), len(delivered)),
                "seven_day_success_percent": period_rate(7),
                "thirty_day_success_percent": period_rate(30),
            }
        )
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size,
    }


def cost_spike_events(
    db: Session,
    *,
    page: int,
    page_size: int,
    factory_id: int | None = None,
    snapshot_date: date | None = None,
    status: str | None = None,
) -> dict:
    query = (
        db.query(CostVarianceAlertLog, DailyVarianceSnapshot, Factory)
        .join(
            DailyVarianceSnapshot,
            (DailyVarianceSnapshot.factory_id == CostVarianceAlertLog.factory_id)
            & (DailyVarianceSnapshot.snapshot_date == CostVarianceAlertLog.snapshot_date),
        )
        .join(Factory, Factory.id == CostVarianceAlertLog.factory_id)
    )
    if factory_id is not None:
        query = query.filter(CostVarianceAlertLog.factory_id == factory_id)
    if snapshot_date is not None:
        query = query.filter(CostVarianceAlertLog.snapshot_date == snapshot_date)
    if status is not None:
        query = query.filter(CostVarianceAlertLog.status == status)
    total = query.count()
    rows = (
        query.order_by(CostVarianceAlertLog.snapshot_date.desc(), CostVarianceAlertLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [
            {
                "id": alert.id,
                "factory_id": alert.factory_id,
                "factory_name": factory.name,
                "snapshot_date": alert.snapshot_date,
                "variance_percent": float(snapshot.variance_percent) if snapshot.variance_percent is not None else None,
                "primary_driver": snapshot.primary_driver,
                "status": alert.status,
                "channel": alert.channel,
                "sent_at": alert.sent_at,
            }
            for alert, snapshot, factory in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size,
    }

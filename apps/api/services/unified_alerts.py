from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import (
    ActivityLog,
    DailyVarianceSnapshot,
    DailyWastageSnapshot,
    ExpenseLog,
    Factory,
    FactoryExpense,
    OutstandingBill,
    PurchaseEntry,
    TelegramUserBinding,
    UnifiedAlert,
)
from services.briefing_aggregation import collect_yesterday_factory_snapshot


SEVERITY_RANK = {"INFO": 1, "WARNING": 2, "CRITICAL": 3}


def upsert_alert(
    db: Session,
    *,
    factory_id: int,
    dedupe_key: str,
    title: str,
    message: str,
    severity: str,
    source_module: str,
    related_entity_type: str | None = None,
    related_entity_id: str | int | None = None,
    related_route: str | None = None,
    suggested_action: str | None = None,
    assigned_role: str = "Owner",
    metadata: dict | None = None,
    send_critical: bool = False,
    sender=None,
) -> UnifiedAlert:
    severity = severity.upper()
    if severity not in SEVERITY_RANK:
        raise ValueError("Invalid alert severity")
    now = datetime.now(timezone.utc)
    row = db.query(UnifiedAlert).filter(
        UnifiedAlert.factory_id == factory_id,
        UnifiedAlert.dedupe_key == dedupe_key,
    ).first()
    should_send = row is None or SEVERITY_RANK[severity] > SEVERITY_RANK.get(row.severity, 0)
    if row is None:
        row = UnifiedAlert(factory_id=factory_id, dedupe_key=dedupe_key, first_detected_at=now)
        db.add(row)
    elif row.status == "RESOLVED":
        row.status = "OPEN"
        row.resolved_at = None
        row.resolved_by_user_id = None

    row.title = title
    row.message = message
    row.severity = severity
    row.source_module = source_module
    row.related_entity_type = related_entity_type
    row.related_entity_id = str(related_entity_id) if related_entity_id is not None else None
    row.related_route = related_route
    row.suggested_action = suggested_action
    row.assigned_role = assigned_role
    row.last_detected_at = now
    row.metadata_json = metadata
    db.flush()

    if severity == "CRITICAL" and send_critical and should_send and row.telegram_sent_at is None:
        _send_critical_alert(db, row, sender=sender)
    return row


def _send_critical_alert(db: Session, alert: UnifiedAlert, sender=None) -> None:
    from services.telegram_delivery import get_owner_telegram_targets, send_message_to_targets

    factory = db.query(Factory).filter(Factory.id == alert.factory_id).first()
    if factory is None:
        return
    message = (
        "CRITICAL ALERT\n\n"
        f"{alert.title}\n{alert.message}\n"
        f"Action: {alert.suggested_action or 'Open Munshi AI Alert Center.'}"
    )
    try:
        targets = get_owner_telegram_targets(db, alert.factory_id)
        if not targets:
            return
        (sender or send_message_to_targets)(factory, message, targets)
        alert.telegram_sent_at = datetime.now(timezone.utc)
    except Exception as exc:
        upsert_alert(
            db,
            factory_id=alert.factory_id,
            dedupe_key=f"telegram_delivery:{alert.id}",
            title="Telegram delivery failed",
            message=f"Critical alert delivery failed: {type(exc).__name__}",
            severity="WARNING",
            source_module="telegram_delivery",
            related_entity_type="unified_alert",
            related_entity_id=alert.id,
            related_route="/integrations",
            suggested_action="Check Telegram connection and bot permissions.",
            send_critical=False,
        )


def top_alerts(db: Session, factory_id: int, limit: int = 5) -> list[UnifiedAlert]:
    severity_order = {
        "CRITICAL": 3,
        "WARNING": 2,
        "INFO": 1,
    }
    rows = db.query(UnifiedAlert).filter(
        UnifiedAlert.factory_id == factory_id,
        UnifiedAlert.status != "RESOLVED",
    ).all()
    return sorted(
        rows,
        key=lambda row: (severity_order.get(row.severity, 0), row.last_detected_at or row.first_detected_at),
        reverse=True,
    )[:limit]


def sync_factory_alerts(
    db: Session,
    factory_id: int,
    *,
    today: date | None = None,
    send_critical: bool = False,
    sender=None,
) -> None:
    target_date = today or date.today()
    operational = collect_yesterday_factory_snapshot(db, factory_id, target_date)
    for risk in operational.get("risk_items", []):
        if risk.get("type") != "low_stock":
            continue
        label = str(risk.get("label") or "Inventory")
        days_left = risk.get("days_left")
        severity = str(risk.get("severity") or "warning").upper()
        upsert_alert(
            db, factory_id=factory_id,
            dedupe_key=f"inventory:{label.lower().replace(' ', '_')}",
            title=f"{label} low stock",
            message=f"Estimated stock cover is {days_left} days.",
            severity=severity, source_module="inventory",
            related_route="/inventory",
            suggested_action="Review consumption and create a replenishment purchase.",
            send_critical=send_critical, sender=sender,
        )

    production = operational.get("production") or {}
    gap = int(production.get("gap") or 0)
    target = int(production.get("target") or 0)
    if gap > 0 and target > 0:
        gap_percent = (gap / target) * 100
        upsert_alert(
            db, factory_id=factory_id, dedupe_key=f"production_gap:{target_date}",
            title="Production target gap",
            message=f"Production is short by {gap} units ({gap_percent:.1f}% of target).",
            severity="CRITICAL" if gap_percent >= 50 else "WARNING",
            source_module="production", related_route="/production",
            suggested_action="Review machine output, staffing and pending shift plan.",
            send_critical=send_critical, sender=sender,
        )

    failed_bindings = db.query(TelegramUserBinding).filter(
        TelegramUserBinding.factory_id == factory_id,
        TelegramUserBinding.is_active.is_(True),
        TelegramUserBinding.last_message_status == "failed",
    ).all()
    for binding in failed_bindings:
        upsert_alert(
            db, factory_id=factory_id, dedupe_key=f"telegram_binding_failure:{binding.id}",
            title="Telegram delivery failed",
            message=f"Last Telegram message failed for the {binding.role} binding.",
            severity="WARNING", source_module="telegram_delivery",
            related_entity_type="telegram_user_binding", related_entity_id=binding.id,
            related_route="/integrations",
            suggested_action="Reconnect Telegram and verify bot permissions.",
            send_critical=False,
        )

    latest_cost = db.query(DailyVarianceSnapshot).filter(
        DailyVarianceSnapshot.factory_id == factory_id,
        DailyVarianceSnapshot.variance_level.in_(("WARNING", "CRITICAL")),
    ).order_by(DailyVarianceSnapshot.snapshot_date.desc()).first()
    if latest_cost:
        upsert_alert(
            db, factory_id=factory_id, dedupe_key=f"cost:{latest_cost.snapshot_date}",
            title="Cost spike detected", message=f"Cost variance is {latest_cost.variance_percent or 0}%.",
            severity=latest_cost.variance_level, source_module="cost",
            related_entity_type="daily_variance_snapshot", related_entity_id=latest_cost.id,
            related_route="/cost-intelligence", suggested_action="Review material, labour and power cost drivers.",
            send_critical=send_critical, sender=sender,
        )

    latest_wastage = db.query(DailyWastageSnapshot).filter(
        DailyWastageSnapshot.factory_id == factory_id,
        DailyWastageSnapshot.wastage_status.in_(("WARNING", "CRITICAL")),
    ).order_by(DailyWastageSnapshot.snapshot_date.desc()).first()
    if latest_wastage:
        upsert_alert(
            db, factory_id=factory_id, dedupe_key=f"wastage:{latest_wastage.snapshot_date}",
            title="Wastage spike detected",
            message=f"Wastage is {latest_wastage.wastage_percentage}%.",
            severity=latest_wastage.wastage_status, source_module="wastage",
            related_entity_type="daily_wastage_snapshot", related_entity_id=latest_wastage.id,
            related_route="/production", suggested_action="Review material usage and machine settings.",
            send_critical=send_critical, sender=sender,
        )

    overdue = db.query(OutstandingBill).filter(
        OutstandingBill.factory_id == factory_id,
        OutstandingBill.balance_amount > 0,
        OutstandingBill.bill_date < target_date - timedelta(days=30),
        OutstandingBill.status.in_(["active", "partial"]),
    ).all()
    for bill in overdue:
        days = (target_date - bill.bill_date).days
        upsert_alert(
            db, factory_id=factory_id, dedupe_key=f"outstanding:{bill.id}",
            title="Customer payment overdue", message=f"{bill.tracking_number} is overdue by {days} days.",
            severity="CRITICAL" if days >= 60 else "WARNING", source_module="customer_outstanding",
            related_entity_type="outstanding_bill", related_entity_id=bill.id,
            related_route="/outstanding", suggested_action="Contact the customer and record collection follow-up.",
            send_critical=send_critical, sender=sender,
        )

    delayed = db.query(PurchaseEntry).filter(
        PurchaseEntry.factory_id == factory_id,
        PurchaseEntry.expected_delivery_date < target_date,
        PurchaseEntry.received_status != "Received",
    ).all()
    for purchase in delayed:
        days = (target_date - purchase.expected_delivery_date).days
        upsert_alert(
            db, factory_id=factory_id, dedupe_key=f"supplier_delay:{purchase.id}",
            title="Supplier delivery delayed", message=f"Purchase #{purchase.id} is delayed by {days} days.",
            severity="CRITICAL" if days >= 7 else "WARNING", source_module="supplier",
            related_entity_type="purchase_entry", related_entity_id=purchase.id,
            related_route="/purchases", suggested_action="Confirm revised delivery date with supplier.",
            send_critical=send_critical, sender=sender,
        )

    breakdowns = db.query(ActivityLog).filter(
        ActivityLog.factory_id == factory_id,
        ActivityLog.event_type == "machine_telemetry",
        ActivityLog.log_date >= target_date - timedelta(days=1),
    ).all()
    for event in breakdowns:
        upsert_alert(
            db, factory_id=factory_id, dedupe_key=f"machine_downtime:{event.id}",
            title="Machine downtime reported", message=event.description,
            severity="CRITICAL", source_module="machine",
            related_entity_type="activity_log", related_entity_id=event.id,
            related_route="/operations", suggested_action="Assign maintenance and record restart time.",
            send_critical=send_critical, sender=sender,
        )

    _sync_expense_spike(db, factory_id, target_date, send_critical, sender)


def _sync_expense_spike(db: Session, factory_id: int, target_date: date, send_critical: bool, sender) -> None:
    today_log = db.query(func.coalesce(func.sum(ExpenseLog.amount), 0)).filter(
        ExpenseLog.factory_id == factory_id, ExpenseLog.date == target_date,
    ).scalar()
    start = target_date - timedelta(days=7)
    prior_log = db.query(func.coalesce(func.sum(ExpenseLog.amount), 0)).filter(
        ExpenseLog.factory_id == factory_id, ExpenseLog.date >= start, ExpenseLog.date < target_date,
    ).scalar()
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(target_date + timedelta(days=1), datetime.min.time())
    today_factory = db.query(func.coalesce(func.sum(FactoryExpense.amount), 0)).filter(
        FactoryExpense.factory_id == factory_id,
        FactoryExpense.timestamp >= datetime.combine(target_date, datetime.min.time()),
        FactoryExpense.timestamp < end_dt,
    ).scalar()
    prior_factory = db.query(func.coalesce(func.sum(FactoryExpense.amount), 0)).filter(
        FactoryExpense.factory_id == factory_id,
        FactoryExpense.timestamp >= start_dt,
        FactoryExpense.timestamp < datetime.combine(target_date, datetime.min.time()),
    ).scalar()
    today_total = Decimal(str(today_log or 0)) + Decimal(str(today_factory or 0))
    average = (Decimal(str(prior_log or 0)) + Decimal(str(prior_factory or 0))) / Decimal("7")
    if average > 0 and today_total >= average * Decimal("1.5"):
        ratio = today_total / average
        upsert_alert(
            db, factory_id=factory_id, dedupe_key=f"expense_spike:{target_date}",
            title="Expense spike detected", message=f"Today's expense is {ratio:.1f}x the 7-day daily average.",
            severity="CRITICAL" if ratio >= 2 else "WARNING", source_module="expense",
            related_route="/expenses", suggested_action="Review today's expense entries and approvals.",
            send_critical=send_critical, sender=sender,
        )


def render_briefing_alerts(rows: list[UnifiedAlert]) -> str:
    if not rows:
        return ""
    lines = ["", "Top Alerts"]
    for index, row in enumerate(rows[:3], 1):
        lines.append(f"{index}. [{row.severity}] {row.title}")
        if row.suggested_action:
            lines.append(f"   Action: {row.suggested_action}")
    return "\n".join(lines)

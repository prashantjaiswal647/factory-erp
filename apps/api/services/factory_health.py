from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import (
    AttendanceLog,
    BlankStock,
    BottomStock,
    DailyFactoryHealthSnapshot,
    DailyProduction,
    DailyVarianceSnapshot,
    Machine,
    Payment,
    SalesInvoice,
    Worker,
)
from services.briefing_aggregation import BLANK_DAILY_USAGE_KG, BOTTOM_DAILY_USAGE_KG
from services.cost_variance import compute_variance_summary


WEIGHTS = {
    "Production": Decimal("0.25"),
    "Attendance": Decimal("0.15"),
    "Collections": Decimal("0.20"),
    "Inventory": Decimal("0.20"),
    "Cost": Decimal("0.20"),
}
COMPONENT_ORDER = ["Production", "Attendance", "Collections", "Inventory", "Cost"]
COST_SCORES = {"NORMAL": Decimal("100"), "WARNING": Decimal("70"), "CRITICAL": Decimal("40")}


def _score_ratio(numerator, denominator) -> Decimal:
    top = Decimal(str(numerator or 0))
    bottom = Decimal(str(denominator or 0))
    if bottom <= 0:
        return Decimal("0")
    return min((top / bottom) * 100, Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _stock_days(total_qty, daily_usage: Decimal) -> Decimal | None:
    quantity = Decimal(str(total_qty or 0))
    if quantity <= 0 or daily_usage <= 0:
        return None
    return quantity / daily_usage


def inventory_score_for_days(days: Decimal | None) -> Decimal:
    if days is None:
        return Decimal("0")
    if days >= 14:
        return Decimal("100")
    if days >= 7:
        return Decimal("80")
    if days >= 3:
        return Decimal("60")
    return Decimal("30")


def classify_health(score: Decimal) -> str:
    if score < 50:
        return "CRITICAL"
    if score < 70:
        return "WARNING"
    if score < 85:
        return "GOOD"
    return "EXCELLENT"


def serialize_health_snapshot(row: DailyFactoryHealthSnapshot) -> dict:
    return {
        "date": row.snapshot_date.isoformat(),
        "overall_score": float(row.overall_score),
        "health_status": row.health_status,
        "production_score": float(row.production_score),
        "attendance_score": float(row.attendance_score),
        "collections_score": float(row.collections_score),
        "inventory_score": float(row.inventory_score),
        "cost_score": float(row.cost_score),
        "largest_strength": row.largest_strength,
        "largest_risk": row.largest_risk,
    }


def factory_health_history(db: Session, factory_id: int, days: int, *, end_date: date | None = None) -> dict:
    resolved_end = end_date or date.today()
    rows = (
        db.query(DailyFactoryHealthSnapshot)
        .filter(
            DailyFactoryHealthSnapshot.factory_id == factory_id,
            DailyFactoryHealthSnapshot.snapshot_date >= resolved_end - timedelta(days=days - 1),
            DailyFactoryHealthSnapshot.snapshot_date <= resolved_end,
        )
        .order_by(DailyFactoryHealthSnapshot.snapshot_date.asc())
        .all()
    )
    items = [serialize_health_snapshot(row) for row in rows]
    if not rows:
        return {
            "days": days,
            "items": [],
            "summary": {
                "current_score": None,
                "previous_score": None,
                "seven_day_average": None,
                "thirty_day_average": None,
                "best_day": None,
                "worst_day": None,
                "trend_direction": "STABLE",
            },
        }

    def average(values) -> float | None:
        return round(sum(values) / len(values), 2) if values else None

    current = rows[-1]
    previous = rows[-2] if len(rows) > 1 else None
    seven_start = current.snapshot_date - timedelta(days=6)
    thirty_start = current.snapshot_date - timedelta(days=29)
    seven_values = [float(row.overall_score) for row in rows if row.snapshot_date >= seven_start]
    thirty_values = [float(row.overall_score) for row in rows if row.snapshot_date >= thirty_start]
    seven_average = average(seven_values)
    current_score = float(current.overall_score)
    delta = current_score - seven_average if seven_average is not None else 0
    direction = "IMPROVING" if delta >= 3 else "DECLINING" if delta <= -3 else "STABLE"
    best = max(rows, key=lambda row: (Decimal(row.overall_score), -row.snapshot_date.toordinal()))
    worst = min(rows, key=lambda row: (Decimal(row.overall_score), row.snapshot_date.toordinal()))
    return {
        "days": days,
        "items": items,
        "summary": {
            "current_score": current_score,
            "previous_score": float(previous.overall_score) if previous else None,
            "seven_day_average": seven_average,
            "thirty_day_average": average(thirty_values),
            "best_day": serialize_health_snapshot(best),
            "worst_day": serialize_health_snapshot(worst),
            "trend_direction": direction,
        },
    }


def compute_factory_health(db: Session, factory_id: int, snapshot_date: date) -> dict:
    produced = (
        db.query(func.coalesce(func.sum(DailyProduction.total_boxes_made), 0))
        .filter(DailyProduction.factory_id == factory_id, DailyProduction.date == snapshot_date)
        .scalar()
    )
    target = (
        db.query(func.coalesce(func.sum(Machine.target_output_per_shift), 0))
        .filter(Machine.factory_id == factory_id, Machine.is_active.is_(True))
        .scalar()
    )
    production_score = _score_ratio(produced, target)

    present = (
        db.query(func.count(AttendanceLog.id))
        .filter(
            AttendanceLog.factory_id == factory_id,
            AttendanceLog.date == snapshot_date,
            (AttendanceLog.status == "Present") | (AttendanceLog.is_present.is_(True)),
        )
        .scalar()
        or 0
    )
    total_workers = (
        db.query(func.count(Worker.id))
        .filter(Worker.factory_id == factory_id, Worker.is_active.is_(True))
        .scalar()
        or 0
    )
    attendance_score = _score_ratio(present, total_workers)

    collections = (
        db.query(func.coalesce(func.sum(Payment.amount_paid), 0))
        .filter(Payment.factory_id == factory_id, Payment.date == snapshot_date)
        .scalar()
    )
    expected_collections = (
        db.query(func.coalesce(func.sum(SalesInvoice.total_amount), 0))
        .filter(SalesInvoice.factory_id == factory_id, SalesInvoice.date == snapshot_date)
        .scalar()
    )
    collections_score = _score_ratio(collections, expected_collections)

    blank_qty = (
        db.query(func.coalesce(func.sum(BlankStock.total_qty_kg), 0))
        .filter(BlankStock.factory_id == factory_id)
        .scalar()
    )
    bottom_qty = (
        db.query(func.coalesce(func.sum(BottomStock.total_qty_kg), 0))
        .filter(BottomStock.factory_id == factory_id)
        .scalar()
    )
    stock_days = [
        value
        for value in (
            _stock_days(blank_qty, BLANK_DAILY_USAGE_KG),
            _stock_days(bottom_qty, BOTTOM_DAILY_USAGE_KG),
        )
        if value is not None
    ]
    inventory_days = min(stock_days) if len(stock_days) == 2 else None
    inventory_score = inventory_score_for_days(inventory_days)

    variance = compute_variance_summary(db, factory_id, snapshot_date)
    cost_score = COST_SCORES[variance["variance_level"]]
    components = {
        "Production": production_score,
        "Attendance": attendance_score,
        "Collections": collections_score,
        "Inventory": inventory_score,
        "Cost": cost_score,
    }
    overall = sum((components[name] * WEIGHTS[name] for name in COMPONENT_ORDER), Decimal("0"))
    overall = overall.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    strength = max(COMPONENT_ORDER, key=lambda name: (components[name], -COMPONENT_ORDER.index(name)))
    risk = min(COMPONENT_ORDER, key=lambda name: (components[name], COMPONENT_ORDER.index(name)))
    status = classify_health(overall)

    row = (
        db.query(DailyFactoryHealthSnapshot)
        .filter(
            DailyFactoryHealthSnapshot.factory_id == factory_id,
            DailyFactoryHealthSnapshot.snapshot_date == snapshot_date,
        )
        .first()
    )
    row = row or DailyFactoryHealthSnapshot(factory_id=factory_id, snapshot_date=snapshot_date)
    row.production_score = production_score
    row.attendance_score = attendance_score
    row.collections_score = collections_score
    row.inventory_score = inventory_score
    row.cost_score = cost_score
    row.overall_score = overall
    row.health_status = status
    row.largest_strength = strength
    row.largest_risk = risk
    if row.id is None:
        db.add(row)
    db.flush()

    previous = (
        db.query(DailyFactoryHealthSnapshot)
        .filter(
            DailyFactoryHealthSnapshot.factory_id == factory_id,
            DailyFactoryHealthSnapshot.snapshot_date < snapshot_date,
        )
        .order_by(DailyFactoryHealthSnapshot.snapshot_date.desc())
        .first()
    )
    trend = (
        (overall - Decimal(previous.overall_score)).quantize(Decimal("0.01"))
        if previous is not None
        else None
    )
    return {
        "id": row.id,
        "factory_id": factory_id,
        "snapshot_date": snapshot_date.isoformat(),
        "production_score": float(production_score),
        "attendance_score": float(attendance_score),
        "collections_score": float(collections_score),
        "inventory_score": float(inventory_score),
        "cost_score": float(cost_score),
        "overall_score": float(overall),
        "health_status": status,
        "largest_strength": strength,
        "largest_risk": risk,
        "trend": float(trend) if trend is not None else None,
        "inventory_days_remaining": float(inventory_days) if inventory_days is not None else None,
    }

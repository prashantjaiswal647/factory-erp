from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from models import (
    CostingMaster,
    DailyProduction,
    DailyWastageSnapshot,
    WastageAlertLog,
)
from services.cost_engine import _cups_produced


ONBOARDING_EXPECTED_WASTAGE_PERCENT = Decimal("2.00")
MIN_BASELINE_DAYS = 3
WARNING_DELTA_PERCENT = Decimal("1.00")
CRITICAL_DELTA_PERCENT = Decimal("3.00")


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _quantize(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _historical_baseline(db: Session, factory_id: int, snapshot_date: date) -> dict:
    start_date = snapshot_date - timedelta(days=30)
    rows = (
        db.query(DailyProduction)
        .filter(
            DailyProduction.factory_id == factory_id,
            DailyProduction.date >= start_date,
            DailyProduction.date < snapshot_date,
        )
        .order_by(DailyProduction.date.asc())
        .all()
    )
    grouped: dict[date, list[DailyProduction]] = {}
    for row in rows:
        grouped.setdefault(row.date, []).append(row)

    total_material = Decimal("0")
    total_wastage = Decimal("0")
    total_blank = Decimal("0")
    total_bottom = Decimal("0")
    total_cups = 0
    usable_days = 0
    for daily_rows in grouped.values():
        material = sum((_decimal(row.blank_used_kg) + _decimal(row.bottom_used_kg) for row in daily_rows), Decimal("0"))
        wastage = sum((_decimal(row.wastage_kg) for row in daily_rows), Decimal("0"))
        cups, _ = _cups_produced(db, factory_id, daily_rows)
        if material <= 0 or cups <= 0:
            continue
        usable_days += 1
        total_material += material
        total_wastage += wastage
        total_blank += sum((_decimal(row.blank_used_kg) for row in daily_rows), Decimal("0"))
        total_bottom += sum((_decimal(row.bottom_used_kg) for row in daily_rows), Decimal("0"))
        total_cups += cups

    sufficient = usable_days >= MIN_BASELINE_DAYS and total_material > 0 and total_cups > 0
    expected_percent = (
        (total_wastage / total_material) * 100
        if sufficient
        else ONBOARDING_EXPECTED_WASTAGE_PERCENT
    )
    return {
        "days": usable_days,
        "expected_percent": expected_percent,
        "blank_per_cup": total_blank / total_cups if sufficient else None,
        "bottom_per_cup": total_bottom / total_cups if sufficient else None,
        "source": "factory_30_day" if sufficient else "onboarding_default",
    }


def _classify(actual_percent: Decimal, expected_percent: Decimal) -> str:
    delta = actual_percent - expected_percent
    if delta <= 0:
        return "NORMAL"
    if delta <= CRITICAL_DELTA_PERCENT:
        return "WARNING"
    return "CRITICAL"


def _primary_source(
    blank_used: Decimal,
    bottom_used: Decimal,
    cups: int,
    baseline: dict,
) -> tuple[str, Decimal, Decimal]:
    expected_blank = (baseline["blank_per_cup"] or Decimal("0")) * cups
    expected_bottom = (baseline["bottom_per_cup"] or Decimal("0")) * cups
    blank_excess = max(blank_used - expected_blank, Decimal("0"))
    bottom_excess = max(bottom_used - expected_bottom, Decimal("0"))
    if blank_excess <= 0 and bottom_excess <= 0:
        return "Mixed", blank_excess, bottom_excess
    if blank_excess > bottom_excess * Decimal("1.10"):
        return "Blank", blank_excess, bottom_excess
    if bottom_excess > blank_excess * Decimal("1.10"):
        return "Bottom", blank_excess, bottom_excess
    return "Mixed", blank_excess, bottom_excess


def _serialize(row: DailyWastageSnapshot, *, expected_percent: Decimal, baseline_source: str, trends: dict) -> dict:
    actual_percent = Decimal(row.wastage_percentage)
    return {
        "id": row.id,
        "factory_id": row.factory_id,
        "snapshot_date": row.snapshot_date.isoformat(),
        "cups_produced": row.cups_produced,
        "blank_used_kg": float(row.blank_used_kg),
        "bottom_used_kg": float(row.bottom_used_kg),
        "actual_wastage_kg": float(row.actual_wastage_kg),
        "expected_wastage_kg": float(row.expected_wastage_kg),
        "wastage_percentage": float(actual_percent),
        "expected_wastage_percentage": float(_quantize(expected_percent, "0.0001")),
        "extra_wastage_percentage": float(_quantize(actual_percent - expected_percent, "0.0001")),
        "estimated_loss_paise": row.estimated_loss_paise,
        "estimated_loss": float(Decimal(row.estimated_loss_paise) / 100),
        "wastage_status": row.wastage_status,
        "primary_wastage_source": row.primary_wastage_source,
        "baseline_source": baseline_source,
        "seven_day_trend": trends["seven_day"],
        "thirty_day_trend": trends["thirty_day"],
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _weighted_trend(db: Session, factory_id: int, snapshot_date: date, days: int) -> float | None:
    rows = (
        db.query(DailyWastageSnapshot)
        .filter(
            DailyWastageSnapshot.factory_id == factory_id,
            DailyWastageSnapshot.snapshot_date >= snapshot_date - timedelta(days=days - 1),
            DailyWastageSnapshot.snapshot_date <= snapshot_date,
        )
        .all()
    )
    material = sum((_decimal(row.blank_used_kg) + _decimal(row.bottom_used_kg) for row in rows), Decimal("0"))
    if material <= 0:
        return None
    wastage = sum((_decimal(row.actual_wastage_kg) for row in rows), Decimal("0"))
    return float(_quantize((wastage / material) * 100, "0.0001"))


def compute_wastage_snapshot(db: Session, factory_id: int, snapshot_date: date) -> dict:
    rows = (
        db.query(DailyProduction)
        .filter(DailyProduction.factory_id == factory_id, DailyProduction.date == snapshot_date)
        .all()
    )
    cups, _ = _cups_produced(db, factory_id, rows)
    blank_used = sum((_decimal(row.blank_used_kg) for row in rows), Decimal("0"))
    bottom_used = sum((_decimal(row.bottom_used_kg) for row in rows), Decimal("0"))
    material_used = blank_used + bottom_used
    explicit_wastage = sum((_decimal(row.wastage_kg) for row in rows), Decimal("0"))
    baseline = _historical_baseline(db, factory_id, snapshot_date)
    source, blank_excess, bottom_excess = _primary_source(blank_used, bottom_used, cups, baseline)
    inferred_wastage = blank_excess + bottom_excess
    actual_wastage = explicit_wastage if explicit_wastage > 0 else inferred_wastage
    expected_wastage = material_used * baseline["expected_percent"] / 100
    percentage = (actual_wastage / material_used) * 100 if material_used > 0 else Decimal("0")
    status = _classify(percentage, baseline["expected_percent"])

    costing = db.query(CostingMaster).filter(CostingMaster.factory_id == factory_id).first()
    paper_rate = _decimal(costing.paper_price_per_kg) if costing else Decimal("0")
    bottom_rate = _decimal(costing.bottom_roll_price_per_kg) if costing else Decimal("0")
    if source == "Blank":
        loss_rupees = actual_wastage * paper_rate
    elif source == "Bottom":
        loss_rupees = actual_wastage * bottom_rate
    else:
        total = blank_used + bottom_used
        blended_rate = ((blank_used * paper_rate) + (bottom_used * bottom_rate)) / total if total > 0 else Decimal("0")
        loss_rupees = actual_wastage * blended_rate
    loss_paise = int((loss_rupees * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    existing = (
        db.query(DailyWastageSnapshot)
        .filter(
            DailyWastageSnapshot.factory_id == factory_id,
            DailyWastageSnapshot.snapshot_date == snapshot_date,
        )
        .first()
    )
    row = existing or DailyWastageSnapshot(factory_id=factory_id, snapshot_date=snapshot_date)
    row.cups_produced = cups
    row.blank_used_kg = _quantize(blank_used, "0.001")
    row.bottom_used_kg = _quantize(bottom_used, "0.001")
    row.actual_wastage_kg = _quantize(actual_wastage, "0.001")
    row.expected_wastage_kg = _quantize(expected_wastage, "0.001")
    row.wastage_percentage = _quantize(percentage, "0.0001")
    row.estimated_loss_paise = loss_paise
    row.wastage_status = status
    row.primary_wastage_source = source
    if existing is None:
        db.add(row)
    db.flush()

    alert = (
        db.query(WastageAlertLog)
        .filter(WastageAlertLog.factory_id == factory_id, WastageAlertLog.snapshot_date == snapshot_date)
        .first()
    )
    if alert is None:
        db.add(WastageAlertLog(factory_id=factory_id, snapshot_date=snapshot_date, status=status))
    else:
        alert.status = status
    db.flush()

    trends = {
        "seven_day": _weighted_trend(db, factory_id, snapshot_date, 7),
        "thirty_day": _weighted_trend(db, factory_id, snapshot_date, 30),
    }
    return _serialize(
        row,
        expected_percent=baseline["expected_percent"],
        baseline_source=baseline["source"],
        trends=trends,
    )

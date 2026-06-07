from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from models import (
    AttendanceLog,
    CostingMaster,
    CostPerCupDaily,
    DailyProduction,
    ExpenseLog,
    FinalProductStock,
    Worker,
)
from services.timezone_utils import get_kolkata_now


MISSING = "Data not available"
RAW_MATERIAL_EXPENSE_TERMS = ("raw material", "material purchase", "blank purchase", "bottom purchase")


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _paise(value: Decimal) -> int:
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _rupees_from_paise(value: int) -> str:
    return f"{Decimal(value) / Decimal(100):.2f}"


def _ratio(cost_paise: int, cups: int) -> str:
    if cups <= 0:
        return MISSING
    return f"{Decimal(cost_paise) / Decimal(100) / Decimal(cups):.4f}"


def _cups_produced(db: Session, factory_id: int, rows: list[DailyProduction]) -> tuple[int, bool]:
    stocks = (
        db.query(FinalProductStock)
        .filter(FinalProductStock.factory_id == factory_id)
        .all()
    )
    pieces_by_key = {
        (
            stock.product_size_ml,
            (stock.variety or "").strip().lower(),
            (stock.packaging_size_name or "").strip().lower(),
        ): int(stock.pieces_per_packet or 0)
        for stock in stocks
    }
    total = 0
    missing_packaging = False
    for row in rows:
        key = (
            row.product_size_ml,
            (row.variety or "").strip().lower(),
            (row.packaging_size_name or "").strip().lower(),
        )
        pieces_per_packet = pieces_by_key.get(key, 0)
        if pieces_per_packet <= 0:
            missing_packaging = True
            continue
        packets = int(row.total_boxes_made or 0) * int(row.packets_per_box_limit or 0)
        packets += int(row.loose_packets_made or 0)
        total += packets * pieces_per_packet
    return total, missing_packaging


def _material_cost(db: Session, factory_id: int, rows: list[DailyProduction]) -> tuple[Decimal, bool]:
    direct = sum((_decimal(row.raw_material_cost) for row in rows), Decimal("0"))
    if direct > 0:
        return direct, False
    blank_kg = sum((_decimal(row.blank_used_kg) for row in rows), Decimal("0"))
    bottom_kg = sum((_decimal(row.bottom_used_kg) for row in rows), Decimal("0"))
    costing = db.query(CostingMaster).filter(CostingMaster.factory_id == factory_id).first()
    if costing and (blank_kg > 0 or bottom_kg > 0):
        paper_rate = _decimal(costing.paper_price_per_kg)
        bottom_rate = _decimal(costing.bottom_roll_price_per_kg)
        if (blank_kg <= 0 or paper_rate > 0) and (bottom_kg <= 0 or bottom_rate > 0):
            return blank_kg * paper_rate + bottom_kg * bottom_rate, False
    return Decimal("0"), True


def _labour_cost(
    db: Session,
    factory_id: int,
    production_date: date,
    rows: list[DailyProduction],
) -> tuple[Decimal, bool]:
    direct = sum((_decimal(row.labor_cost) for row in rows), Decimal("0"))
    if direct > 0:
        return direct, False
    attendance = (
        db.query(AttendanceLog, Worker)
        .join(Worker, AttendanceLog.worker_id == Worker.id)
        .filter(
            AttendanceLog.factory_id == factory_id,
            Worker.factory_id == factory_id,
            AttendanceLog.date == production_date,
            AttendanceLog.status.in_(["Present", "Half-day"]),
        )
        .all()
    )
    if not attendance:
        return Decimal("0"), True
    total = Decimal("0")
    for log, worker in attendance:
        rate = _decimal(worker.daily_wage_rate)
        if rate <= 0:
            return Decimal("0"), True
        total += rate / 2 if log.status == "Half-day" else rate
    return total, False


def _overhead_cost(db: Session, factory_id: int, production_date: date) -> tuple[Decimal, bool]:
    expenses = (
        db.query(ExpenseLog)
        .filter(ExpenseLog.factory_id == factory_id, ExpenseLog.date == production_date)
        .all()
    )
    if not expenses:
        return Decimal("0"), True
    total = Decimal("0")
    for expense in expenses:
        searchable = f"{expense.category or ''} {expense.description or ''}".lower()
        if any(term in searchable for term in RAW_MATERIAL_EXPENSE_TERMS):
            continue
        total += _decimal(expense.amount)
    return total, False


def _serialize(row: CostPerCupDaily) -> dict:
    loaded_paise = row.total_production_cost_paise + row.total_overhead_cost_paise
    return {
        "id": row.id,
        "factory_id": row.factory_id,
        "production_date": row.production_date.isoformat(),
        "size_ml": row.size_ml,
        "cups_produced_total": row.cups_produced_total,
        "total_material_cost_paise": row.total_material_cost_paise,
        "total_labour_cost_paise": row.total_labour_cost_paise,
        "total_electricity_cost_paise": row.total_electricity_cost_paise,
        "total_overhead_cost_paise": row.total_overhead_cost_paise,
        "total_production_cost_paise": row.total_production_cost_paise,
        "total_loaded_cost_paise": loaded_paise,
        "total_production_cost": _rupees_from_paise(row.total_production_cost_paise),
        "total_loaded_cost": _rupees_from_paise(loaded_paise),
        "cost_per_cup": _ratio(row.total_production_cost_paise, row.cups_produced_total),
        "loaded_cost_per_cup": _ratio(loaded_paise, row.cups_produced_total),
        "has_cost_data": row.total_production_cost_paise > 0,
        "source_quality": row.source_quality,
        "missing_fields": list(row.missing_fields_json or []),
        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
    }


def compute_daily_cost(db: Session, factory_id: int, date: date) -> dict:
    rows = (
        db.query(DailyProduction)
        .filter(DailyProduction.factory_id == factory_id, DailyProduction.date == date)
        .all()
    )
    missing: list[str] = []
    cups, packaging_missing = _cups_produced(db, factory_id, rows)
    if not rows:
        missing.append("production")
    if packaging_missing or cups <= 0:
        missing.append("cups_produced_total")

    material, material_missing = _material_cost(db, factory_id, rows)
    labour, labour_missing = _labour_cost(db, factory_id, date, rows)
    electricity = sum((_decimal(row.electricity_cost) for row in rows), Decimal("0"))
    electricity_missing = electricity <= 0
    overhead, overhead_missing = _overhead_cost(db, factory_id, date)
    for field, is_missing in (
        ("material_cost", material_missing),
        ("labour_cost", labour_missing),
        ("electricity_cost", electricity_missing),
        ("overhead_cost", overhead_missing),
    ):
        if is_missing:
            missing.append(field)

    material_paise = _paise(material)
    labour_paise = _paise(labour)
    electricity_paise = _paise(electricity)
    overhead_paise = _paise(overhead)
    production_paise = material_paise + labour_paise + electricity_paise
    existing = (
        db.query(CostPerCupDaily)
        .filter(
            CostPerCupDaily.factory_id == factory_id,
            CostPerCupDaily.production_date == date,
            CostPerCupDaily.size_ml.is_(None),
        )
        .first()
    )
    row = existing or CostPerCupDaily(factory_id=factory_id, production_date=date, size_ml=None)
    row.cups_produced_total = cups
    row.total_material_cost_paise = material_paise
    row.total_labour_cost_paise = labour_paise
    row.total_electricity_cost_paise = electricity_paise
    row.total_overhead_cost_paise = overhead_paise
    row.total_production_cost_paise = production_paise
    row.source_quality = "complete" if not missing else "partial"
    row.missing_fields_json = sorted(set(missing))
    if existing is None:
        db.add(row)
    db.flush()
    return _serialize(row)


def compute_cost_window(db: Session, factory_id: int, days: int, *, end_date: date | None = None) -> dict:
    if days not in (7, 30):
        raise ValueError("days must be 7 or 30")
    resolved_end_date = end_date or get_kolkata_now().date()
    start_date = resolved_end_date - timedelta(days=days - 1)
    for offset in range(days):
        compute_daily_cost(db, factory_id, start_date + timedelta(days=offset))
    rows = (
        db.query(CostPerCupDaily)
        .filter(
            CostPerCupDaily.factory_id == factory_id,
            CostPerCupDaily.production_date >= start_date,
            CostPerCupDaily.production_date <= resolved_end_date,
            CostPerCupDaily.size_ml.is_(None),
        )
        .all()
    )
    cups = sum(row.cups_produced_total for row in rows)
    production_paise = sum(row.total_production_cost_paise for row in rows)
    overhead_paise = sum(row.total_overhead_cost_paise for row in rows)
    material_paise = sum(row.total_material_cost_paise for row in rows)
    labour_paise = sum(row.total_labour_cost_paise for row in rows)
    electricity_paise = sum(row.total_electricity_cost_paise for row in rows)
    missing = sorted({field for row in rows for field in (row.missing_fields_json or [])})
    loaded_paise = production_paise + overhead_paise
    return {
        "days": days,
        "start_date": start_date.isoformat(),
        "end_date": resolved_end_date.isoformat(),
        "cups_produced_total": cups,
        "total_production_cost_paise": production_paise,
        "total_overhead_cost_paise": overhead_paise,
        "total_material_cost_paise": material_paise,
        "total_labour_cost_paise": labour_paise,
        "total_electricity_cost_paise": electricity_paise,
        "total_loaded_cost_paise": loaded_paise,
        "total_production_cost": _rupees_from_paise(production_paise),
        "weighted_cost_per_cup": _ratio(production_paise, cups),
        "weighted_loaded_cost_per_cup": _ratio(loaded_paise, cups),
        "material_cost_per_cup": _ratio(material_paise, cups),
        "labour_cost_per_cup": _ratio(labour_paise, cups),
        "electricity_cost_per_cup": _ratio(electricity_paise, cups),
        "overhead_cost_per_cup": _ratio(overhead_paise, cups),
        "source_quality": "complete" if rows and not missing else "partial",
        "missing_fields": missing if rows else ["production"],
    }


def compute_cost_for_briefing(db: Session, factory_id: int, date: date) -> dict:
    return compute_daily_cost(db, factory_id, date)

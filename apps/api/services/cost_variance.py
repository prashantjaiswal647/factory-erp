from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from models import DailyVarianceSnapshot
from services.cost_engine import MISSING, compute_cost_window, compute_daily_cost


NORMAL_THRESHOLD_PERCENT = Decimal("3")
CRITICAL_THRESHOLD_PERCENT = Decimal("8")
SPIKE_ALERT_THRESHOLD_PERCENT = Decimal("5")
DRIVER_LABELS = {
    "material": "Material Cost",
    "labour": "Labour Cost",
    "electricity": "Electricity Cost",
    "overhead": "Overhead Cost",
}


def _decimal_or_none(value) -> Decimal | None:
    if value in (None, "", MISSING):
        return None
    return Decimal(str(value))


def _percent(current: Decimal | None, baseline: Decimal | None) -> Decimal | None:
    if current is None or baseline is None or baseline <= 0:
        return None
    return ((current - baseline) / baseline * 100).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def classify_variance(variance_percent: Decimal | None) -> str:
    if variance_percent is None:
        return "NORMAL"
    magnitude = abs(variance_percent)
    if magnitude <= NORMAL_THRESHOLD_PERCENT:
        return "NORMAL"
    if magnitude <= CRITICAL_THRESHOLD_PERCENT:
        return "WARNING"
    return "CRITICAL"


def _component_values(today: dict, seven_day: dict) -> tuple[dict[str, Decimal | None], dict[str, Decimal | None]]:
    today_cups = int(today["cups_produced_total"])
    today_values = {}
    baseline_values = {}
    mappings = {
        "material": "total_material_cost_paise",
        "labour": "total_labour_cost_paise",
        "electricity": "total_electricity_cost_paise",
        "overhead": "total_overhead_cost_paise",
    }
    for key, total_key in mappings.items():
        today_values[key] = (
            Decimal(today[total_key]) / Decimal(100) / Decimal(today_cups)
            if today_cups > 0
            else None
        )
        baseline_values[key] = _decimal_or_none(seven_day[f"{key}_cost_per_cup"])
    return today_values, baseline_values


def compute_variance_summary(db: Session, factory_id: int, snapshot_date: date) -> dict:
    today = compute_daily_cost(db, factory_id, snapshot_date)
    baseline_end = snapshot_date - timedelta(days=1)
    seven_day = compute_cost_window(db, factory_id, 7, end_date=baseline_end)
    thirty_day = compute_cost_window(db, factory_id, 30, end_date=baseline_end)

    today_cpc = _decimal_or_none(today["cost_per_cup"])
    seven_cpc = _decimal_or_none(seven_day["weighted_cost_per_cup"])
    thirty_cpc = _decimal_or_none(thirty_day["weighted_cost_per_cup"])
    today_loaded = _decimal_or_none(today["loaded_cost_per_cup"])
    seven_loaded = _decimal_or_none(seven_day["weighted_loaded_cost_per_cup"])
    thirty_loaded = _decimal_or_none(thirty_day["weighted_loaded_cost_per_cup"])
    variance = _percent(today_cpc, seven_cpc)

    today_components, baseline_components = _component_values(today, seven_day)
    component_changes = {
        key: _percent(today_components[key], baseline_components[key])
        for key in DRIVER_LABELS
    }
    component_deltas = {
        key: abs(today_components[key] - baseline_components[key])
        for key in DRIVER_LABELS
        if today_components[key] is not None and baseline_components[key] is not None
    }
    primary_driver = DRIVER_LABELS[max(component_deltas, key=component_deltas.get)] if component_deltas else MISSING
    level = classify_variance(variance)

    existing = (
        db.query(DailyVarianceSnapshot)
        .filter(
            DailyVarianceSnapshot.factory_id == factory_id,
            DailyVarianceSnapshot.snapshot_date == snapshot_date,
        )
        .first()
    )
    row = existing or DailyVarianceSnapshot(factory_id=factory_id, snapshot_date=snapshot_date)
    row.today_cost = today_cpc
    row.seven_day_cost = seven_cpc
    row.thirty_day_cost = thirty_cpc
    row.variance_percent = variance
    row.variance_level = level
    row.primary_driver = None if primary_driver == MISSING else primary_driver
    row.material_change_percent = component_changes["material"]
    row.labour_change_percent = component_changes["labour"]
    row.electricity_change_percent = component_changes["electricity"]
    row.overhead_change_percent = component_changes["overhead"]
    if existing is None:
        db.add(row)
    db.flush()

    def display(value: Decimal | None) -> str:
        return MISSING if value is None else f"{value:.4f}"

    def display_percent(value: Decimal | None) -> str:
        return MISSING if value is None else f"{value:+.4f}"

    return {
        "snapshot_id": row.id,
        "factory_id": factory_id,
        "snapshot_date": snapshot_date.isoformat(),
        "today_cpc": display(today_cpc),
        "today_loaded_cpc": display(today_loaded),
        "seven_day_cpc": display(seven_cpc),
        "seven_day_loaded_cpc": display(seven_loaded),
        "thirty_day_cpc": display(thirty_cpc),
        "thirty_day_loaded_cpc": display(thirty_loaded),
        "variance_percent": display_percent(variance),
        "variance_level": level,
        "primary_driver": primary_driver,
        "material_change_percent": display_percent(component_changes["material"]),
        "labour_change_percent": display_percent(component_changes["labour"]),
        "electricity_change_percent": display_percent(component_changes["electricity"]),
        "overhead_change_percent": display_percent(component_changes["overhead"]),
        "today": today,
        "seven_day": seven_day,
        "thirty_day": thirty_day,
    }


def should_send_spike_alert(summary: dict) -> bool:
    variance = _decimal_or_none(summary.get("variance_percent"))
    return variance is not None and variance > SPIKE_ALERT_THRESHOLD_PERCENT

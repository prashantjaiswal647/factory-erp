from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import CostPerCupDaily, DailyProduction, DailyProfitSnapshot, DailySale, DailyWastageSnapshot, FinalProductStock, PackagingProfile, PerSizeDaily, SalesInvoice
from services.cost_engine import _cups_produced, compute_daily_cost


MISSING = "Data not available"
RISK_LABELS = {
    "Material": "Material Cost",
    "Labour": "Labour Cost",
    "Electricity": "Electricity Cost",
    "Overhead": "Overhead Cost",
    "Wastage": "Wastage",
    "Collections": "Collections",
}


def classify_profit_margin(margin: Decimal | None) -> str:
    if margin is None:
        return "DATA_NOT_AVAILABLE"
    if margin > 25:
        return "EXCELLENT"
    if margin >= 15:
        return "GOOD"
    if margin >= 5:
        return "WARNING"
    return "CRITICAL"


def _paise_from_rupees(value) -> int:
    return int((Decimal(str(value or 0)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _sales_by_size(db: Session, factory_id: int, snapshot_date: date) -> dict[int, dict]:
    profiles = {
        row.id: int(row.box_capacity or (row.cups_per_poly or 0) * (row.polys_per_box or 0))
        for row in db.query(PackagingProfile).filter(PackagingProfile.factory_id == factory_id).all()
    }
    sales: dict[int, dict] = {}
    invoice_sizes: set[int] = set()
    for invoice in db.query(SalesInvoice).filter(
        SalesInvoice.factory_id == factory_id, SalesInvoice.date == snapshot_date
    ).all():
        size = int(invoice.cup_size_ml)
        invoice_sizes.add(size)
        item = sales.setdefault(size, {"revenue_paise": 0, "units_sold": 0})
        item["revenue_paise"] += _paise_from_rupees(invoice.total_amount)
        item["units_sold"] += int(invoice.boxes_sold or 0) * profiles.get(invoice.packaging_profile_id, 0)

    packaging = {
        (int(row.product_size_ml), (row.variety or "").strip().lower(), (row.packaging_size_name or "").strip().lower()):
        (int(row.pieces_per_packet or 0), int(row.packets_per_box_limit or 0))
        for row in db.query(FinalProductStock).filter(FinalProductStock.factory_id == factory_id).all()
    }
    for sale in db.query(DailySale).filter(
        DailySale.factory_id == factory_id, DailySale.date == snapshot_date
    ).all():
        size = int(sale.product_size_ml)
        if size in invoice_sizes:
            continue
        item = sales.setdefault(size, {"revenue_paise": 0, "units_sold": 0})
        item["revenue_paise"] += _paise_from_rupees(sale.total_amount or sale.total_bill)
        pieces, packets_per_box = packaging.get(
            (size, (sale.variety or "").strip().lower(), (sale.packaging_size_name or "").strip().lower()),
            (0, 0),
        )
        item["units_sold"] += (
            int(sale.boxes_sold or 0) * packets_per_box + int(sale.loose_packets_sold or 0)
        ) * pieces
    return sales


def compute_per_size_profit(db: Session, factory_id: int, snapshot_date: date) -> dict:
    sales = _sales_by_size(db, factory_id, snapshot_date)
    production_by_size: dict[int, list[DailyProduction]] = {}
    for row in db.query(DailyProduction).filter(
        DailyProduction.factory_id == factory_id, DailyProduction.date == snapshot_date
    ).all():
        production_by_size.setdefault(int(row.product_size_ml), []).append(row)
    sized_costs = {
        int(row.size_ml): row
        for row in db.query(CostPerCupDaily).filter(
            CostPerCupDaily.factory_id == factory_id,
            CostPerCupDaily.production_date == snapshot_date,
            CostPerCupDaily.size_ml.is_not(None),
        ).all()
    }

    items = []
    for size in sorted(set(sales) | set(production_by_size) | set(sized_costs)):
        revenue = int(sales.get(size, {}).get("revenue_paise", 0))
        units_sold = int(sales.get(size, {}).get("units_sold", 0))
        rows = production_by_size.get(size, [])
        units_produced, _ = _cups_produced(db, factory_id, rows) if rows else (0, False)
        cost_paise = None
        cost_source = MISSING
        sized_cost = sized_costs.get(size)
        if sized_cost is not None:
            cost_paise = int(sized_cost.total_production_cost_paise) + int(sized_cost.total_overhead_cost_paise)
            cost_source = "CostPerCupDaily"
            units_produced = int(sized_cost.cups_produced_total or units_produced)
        elif rows:
            direct = sum((Decimal(str(row.production_cost or 0)) for row in rows), Decimal("0"))
            if direct <= 0:
                direct = sum(
                    (Decimal(str(row.raw_material_cost or 0)) + Decimal(str(row.labor_cost or 0)) + Decimal(str(row.electricity_cost or 0)) for row in rows),
                    Decimal("0"),
                )
            if direct > 0:
                cost_paise = _paise_from_rupees(direct)
                cost_source = "DailyProduction"

        available = revenue > 0 and cost_paise is not None
        profit = revenue - cost_paise if available else None
        margin = (
            (Decimal(profit) / Decimal(revenue) * 100).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            if available else None
        )
        items.append({
            "size_ml": size,
            "revenue_paise": revenue,
            "cost_paise": cost_paise if cost_paise is not None else MISSING,
            "gross_profit_paise": profit if profit is not None else MISSING,
            "margin_percent": float(margin) if margin is not None else MISSING,
            "units_sold": units_sold,
            "units_produced": units_produced,
            "status": classify_profit_margin(margin),
            "data_available": available,
            "cost_source": cost_source,
        })

    complete = [item for item in items if item["data_available"]]
    best = max(complete, key=lambda item: (item["gross_profit_paise"], item["revenue_paise"], -item["size_ml"]), default=None)
    worst = min(complete, key=lambda item: (item["margin_percent"], item["gross_profit_paise"], item["size_ml"]), default=None)
    total_revenue = sum(item["revenue_paise"] for item in items)
    all_revenue_costed = total_revenue > 0 and all(item["data_available"] for item in items if item["revenue_paise"] > 0)
    total_profit = sum(item["gross_profit_paise"] for item in complete) if all_revenue_costed else MISSING
    weighted_margin = (
        float((Decimal(total_profit) / Decimal(total_revenue) * 100).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
        if all_revenue_costed else MISSING
    )
    return {
        "date": snapshot_date.isoformat(), "sizes": items, "best_size": best, "worst_size": worst,
        "total_revenue": total_revenue, "total_profit": total_profit,
        "weighted_margin": weighted_margin, "data_available": bool(complete),
    }


def persist_per_size_profit(db: Session, factory_id: int, snapshot_date: date) -> dict:
    result = compute_per_size_profit(db, factory_id, snapshot_date)
    existing = {
        row.size_ml: row
        for row in db.query(PerSizeDaily).filter(
            PerSizeDaily.factory_id == factory_id,
            PerSizeDaily.snapshot_date == snapshot_date,
        ).all()
    }
    seen = set()
    for item in result["sizes"]:
        size = int(item["size_ml"])
        seen.add(size)
        row = existing.get(size) or PerSizeDaily(
            factory_id=factory_id,
            snapshot_date=snapshot_date,
            size_ml=size,
        )
        row.revenue_paise = int(item["revenue_paise"])
        row.cost_paise = item["cost_paise"] if isinstance(item["cost_paise"], int) else None
        row.gross_profit_paise = item["gross_profit_paise"] if isinstance(item["gross_profit_paise"], int) else None
        row.margin_percent = item["margin_percent"] if isinstance(item["margin_percent"], (int, float)) else None
        row.units_sold = int(item["units_sold"])
        row.units_produced = int(item["units_produced"])
        row.status = item["status"]
        row.cost_source = item["cost_source"] if item["cost_source"] != MISSING else None
        if row.id is None:
            db.add(row)
    for size, row in existing.items():
        if size not in seen:
            db.delete(row)
    db.flush()
    return result


def serialize_per_size_history(rows: list[PerSizeDaily]) -> list[dict]:
    grouped: dict[date, list[dict]] = {}
    for row in rows:
        available = row.cost_paise is not None and row.gross_profit_paise is not None and row.margin_percent is not None
        grouped.setdefault(row.snapshot_date, []).append({
            "size_ml": row.size_ml,
            "revenue_paise": row.revenue_paise,
            "cost_paise": row.cost_paise if row.cost_paise is not None else MISSING,
            "gross_profit_paise": row.gross_profit_paise if row.gross_profit_paise is not None else MISSING,
            "margin_percent": float(row.margin_percent) if row.margin_percent is not None else MISSING,
            "units_sold": row.units_sold,
            "units_produced": row.units_produced,
            "status": row.status,
            "data_available": available,
            "cost_source": row.cost_source or MISSING,
        })
    results = []
    for snapshot_date, items in sorted(grouped.items()):
        items.sort(key=lambda item: item["size_ml"])
        complete = [item for item in items if item["data_available"]]
        best = max(complete, key=lambda item: (item["gross_profit_paise"], item["revenue_paise"], -item["size_ml"]), default=None)
        worst = min(complete, key=lambda item: (item["margin_percent"], item["gross_profit_paise"], item["size_ml"]), default=None)
        total_revenue = sum(item["revenue_paise"] for item in items)
        all_revenue_costed = total_revenue > 0 and all(item["data_available"] for item in items if item["revenue_paise"] > 0)
        total_profit = sum(item["gross_profit_paise"] for item in complete) if all_revenue_costed else MISSING
        weighted_margin = (
            float((Decimal(total_profit) / Decimal(total_revenue) * 100).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
            if all_revenue_costed else MISSING
        )
        results.append({
            "date": snapshot_date.isoformat(),
            "sizes": items,
            "best_size": best,
            "worst_size": worst,
            "total_revenue": total_revenue,
            "total_profit": total_profit,
            "weighted_margin": weighted_margin,
            "data_available": bool(complete),
        })
    return results


def _window_margin(db: Session, factory_id: int, snapshot_date: date, days: int) -> float | None:
    rows = (
        db.query(DailyProfitSnapshot)
        .filter(
            DailyProfitSnapshot.factory_id == factory_id,
            DailyProfitSnapshot.snapshot_date >= snapshot_date - timedelta(days=days - 1),
            DailyProfitSnapshot.snapshot_date <= snapshot_date,
            DailyProfitSnapshot.revenue_paise > 0,
        )
        .all()
    )
    revenue = sum(row.revenue_paise for row in rows)
    if revenue <= 0:
        return None
    profit = sum(row.gross_profit_paise for row in rows)
    return float((Decimal(profit) / Decimal(revenue) * 100).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def _serialize(row: DailyProfitSnapshot, trends: dict) -> dict:
    available = row.revenue_paise > 0 and row.profit_margin_percent is not None
    return {
        "id": row.id,
        "factory_id": row.factory_id,
        "snapshot_date": row.snapshot_date.isoformat(),
        "revenue_paise": row.revenue_paise,
        "material_cost_paise": row.material_cost_paise,
        "labour_cost_paise": row.labour_cost_paise,
        "electricity_cost_paise": row.electricity_cost_paise,
        "overhead_cost_paise": row.overhead_cost_paise,
        "total_cost_paise": row.total_cost_paise,
        "gross_profit_paise": row.gross_profit_paise,
        "revenue": float(Decimal(row.revenue_paise) / 100) if available else MISSING,
        "total_cost": float(Decimal(row.total_cost_paise) / 100) if available else MISSING,
        "gross_profit": float(Decimal(row.gross_profit_paise) / 100) if available else MISSING,
        "profit_margin_percent": float(row.profit_margin_percent) if available else MISSING,
        "profit_status": row.profit_status,
        "largest_profit_risk": row.largest_profit_risk,
        "seven_day_margin": trends["seven_day"],
        "thirty_day_margin": trends["thirty_day"],
        "data_available": available,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def compute_profit_snapshot(db: Session, factory_id: int, snapshot_date: date) -> dict:
    invoice_totals = (
        db.query(
            func.coalesce(func.sum(SalesInvoice.total_amount), 0),
            func.coalesce(func.sum(SalesInvoice.amount_paid), 0),
        )
        .filter(SalesInvoice.factory_id == factory_id, SalesInvoice.date == snapshot_date)
        .one()
    )
    revenue_paise = _paise_from_rupees(invoice_totals[0])
    collected_paise = _paise_from_rupees(invoice_totals[1])
    cost = compute_daily_cost(db, factory_id, snapshot_date)
    material = int(cost["total_material_cost_paise"])
    labour = int(cost["total_labour_cost_paise"])
    electricity = int(cost["total_electricity_cost_paise"])
    overhead = int(cost["total_overhead_cost_paise"])
    total_cost = material + labour + electricity + overhead
    gross_profit = revenue_paise - total_cost
    margin = (
        (Decimal(gross_profit) / Decimal(revenue_paise) * 100).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        if revenue_paise > 0
        else None
    )

    wastage = (
        db.query(DailyWastageSnapshot)
        .filter(
            DailyWastageSnapshot.factory_id == factory_id,
            DailyWastageSnapshot.snapshot_date == snapshot_date,
        )
        .first()
    )
    risks = {
        "Material": material,
        "Labour": labour,
        "Electricity": electricity,
        "Overhead": overhead,
        "Wastage": wastage.estimated_loss_paise if wastage else 0,
        "Collections": max(revenue_paise - collected_paise, 0),
    }
    risk_key = max(risks, key=lambda key: (risks[key], -list(risks).index(key)))
    risk = RISK_LABELS[risk_key]
    status = classify_profit_margin(margin)

    existing = (
        db.query(DailyProfitSnapshot)
        .filter(
            DailyProfitSnapshot.factory_id == factory_id,
            DailyProfitSnapshot.snapshot_date == snapshot_date,
        )
        .first()
    )
    row = existing or DailyProfitSnapshot(factory_id=factory_id, snapshot_date=snapshot_date)
    row.revenue_paise = revenue_paise
    row.material_cost_paise = material
    row.labour_cost_paise = labour
    row.electricity_cost_paise = electricity
    row.overhead_cost_paise = overhead
    row.total_cost_paise = total_cost
    row.gross_profit_paise = gross_profit
    row.profit_margin_percent = margin
    row.profit_status = status
    row.largest_profit_risk = risk
    if existing is None:
        db.add(row)
    db.flush()
    return _serialize(
        row,
        {
            "seven_day": _window_margin(db, factory_id, snapshot_date, 7),
            "thirty_day": _window_margin(db, factory_id, snapshot_date, 30),
        },
    )


def should_send_profit_alert(snapshot: dict) -> bool:
    return snapshot["data_available"] and snapshot["profit_status"] == "CRITICAL"


def render_profit_alert(snapshot: dict) -> str:
    return "\n".join(
        [
            "⚠ Profit Alert",
            "",
            f"Margin: {snapshot['profit_margin_percent']:.1f}%",
            f"Status: {snapshot['profit_status']}",
            f"Primary Risk: {snapshot['largest_profit_risk']}",
        ]
    )

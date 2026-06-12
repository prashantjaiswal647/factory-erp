from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import DailyFactoryHealthSnapshot, DailyProduction, DailyProfitSnapshot, Worker
from services.briefing_translations import translations_for
from services.timezone_utils import KOLKATA_ZONE


RISK_ORDER = ["Material Cost", "Labour Cost", "Electricity Cost", "Overhead Cost", "Collections", "Wastage"]


def week_range(report_date: date) -> tuple[date, date]:
    week_end = report_date + timedelta(days=6 - report_date.weekday())
    return week_end - timedelta(days=6), week_end


def latest_report_sunday(today: date) -> date:
    return today - timedelta(days=(today.weekday() - 6) % 7)


def compute_weekly_digest(db: Session, factory_id: int, week_start: date, week_end: date) -> dict:
    profit_rows = (
        db.query(DailyProfitSnapshot)
        .filter(
            DailyProfitSnapshot.factory_id == factory_id,
            DailyProfitSnapshot.snapshot_date >= week_start,
            DailyProfitSnapshot.snapshot_date <= week_end,
            DailyProfitSnapshot.revenue_paise > 0,
        )
        .order_by(DailyProfitSnapshot.snapshot_date.asc())
        .all()
    )
    health_rows = (
        db.query(DailyFactoryHealthSnapshot)
        .filter(
            DailyFactoryHealthSnapshot.factory_id == factory_id,
            DailyFactoryHealthSnapshot.snapshot_date >= week_start,
            DailyFactoryHealthSnapshot.snapshot_date <= week_end,
        )
        .all()
    )
    revenue = sum(row.revenue_paise for row in profit_rows)
    profit = sum(row.gross_profit_paise for row in profit_rows)
    margin = (
        (Decimal(profit) / Decimal(revenue) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if revenue > 0
        else None
    )
    health = (
        (sum(Decimal(row.overall_score) for row in health_rows) / len(health_rows)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        if health_rows
        else None
    )
    best = max(profit_rows, key=lambda row: (row.gross_profit_paise, -row.snapshot_date.toordinal())) if profit_rows else None
    worst = min(profit_rows, key=lambda row: (row.gross_profit_paise, row.snapshot_date.toordinal())) if profit_rows else None
    counts = Counter(row.largest_profit_risk for row in profit_rows if row.largest_profit_risk)
    largest_risk = (
        max(RISK_ORDER, key=lambda risk: (counts.get(risk, 0), -RISK_ORDER.index(risk)))
        if counts
        else "Data not available"
    )
    production_rows = (
        db.query(DailyProduction)
        .filter(
            DailyProduction.factory_id == factory_id,
            DailyProduction.date >= week_start,
            DailyProduction.date <= week_end,
            DailyProduction.status == "ACTIVE",
        )
        .all()
    )
    worker_totals = (
        db.query(
            DailyProduction.worker_id,
            Worker.name,
            func.sum(DailyProduction.total_boxes_made + DailyProduction.boxes_from_loose),
        )
        .outerjoin(Worker, Worker.id == DailyProduction.worker_id)
        .filter(
            DailyProduction.factory_id == factory_id,
            DailyProduction.date >= week_start,
            DailyProduction.date <= week_end,
            DailyProduction.status == "ACTIVE",
        )
        .group_by(DailyProduction.worker_id, Worker.name)
        .all()
    )
    product_totals: dict[str, int] = {}
    for row in production_rows:
        product = f"{row.product_size_ml}ml {row.variety}"
        product_totals[product] = product_totals.get(product, 0) + int(row.total_boxes_made or 0) + int(row.boxes_from_loose or 0)
    top_worker = max(worker_totals, key=lambda item: int(item[2] or 0), default=None)
    return {
        "factory_id": factory_id,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "revenue_paise": revenue,
        "profit_paise": profit,
        "revenue": float(Decimal(revenue) / 100),
        "profit": float(Decimal(profit) / 100),
        "margin": float(margin) if margin is not None else None,
        "health_score": int(health) if health is not None else None,
        "best_day": best.snapshot_date.strftime("%A") if best else "Data not available",
        "worst_day": worst.snapshot_date.strftime("%A") if worst else "Data not available",
        "largest_risk": largest_risk,
        "generated_at": datetime.now(KOLKATA_ZONE).isoformat(),
        "days_available": len(profit_rows),
        "blank_bora_used": float(sum(Decimal(row.blank_used_bora or 0) for row in production_rows)),
        "blank_kg_used": float(sum(Decimal(row.blank_used_kg or 0) for row in production_rows)),
        "bottom_rolls_used": sum(int(row.bottom_used_rolls or 0) for row in production_rows),
        "boxes_produced": sum(int(row.total_boxes_made or 0) + int(row.boxes_from_loose or 0) for row in production_rows),
        "loose_packets_produced": sum(int(row.loose_packets_made or 0) for row in production_rows),
        "worker_production": [
            {"worker_id": worker_id, "worker_name": worker_name or "Worker removed", "boxes": int(boxes or 0)}
            for worker_id, worker_name, boxes in worker_totals
        ],
        "product_production": [
            {"product": product, "boxes": boxes} for product, boxes in sorted(product_totals.items())
        ],
        "top_worker": (
            {"worker_name": top_worker[1] or "Worker removed", "boxes": int(top_worker[2] or 0)}
            if top_worker else None
        ),
    }


def render_weekly_digest(digest: dict, language: str = "hinglish") -> str:
    _, labels = translations_for(language)
    missing = labels["missing"]
    margin = missing if digest["margin"] is None else f"{digest['margin']:.1f}%"
    health = missing if digest["health_score"] is None else f"{digest['health_score']}/100"
    recommendation = labels["weekly_recommendations"].get(
        digest["largest_risk"],
        labels["weekly_recommendations"]["default"],
    )
    return "\n".join(
        [
            labels["weekly_title"],
            "",
            f"{labels['revenue']}:",
            f"₹{digest['revenue']:,.0f}",
            "",
            f"{labels['profit']}:",
            f"₹{digest['profit']:,.0f}",
            "",
            f"{labels['margin']}:",
            margin,
            "",
            f"{labels['weekly_health']}:",
            health,
            "",
            "Weekly Factory Consumption Summary:",
            f"Blank Used: {digest['blank_bora_used']:g} bora / {digest['blank_kg_used']:g} KG",
            f"Bottom Used: {digest['bottom_rolls_used']} rolls",
            f"Finished Goods Produced: {digest['boxes_produced']} boxes",
            f"Loose Packets Produced: {digest['loose_packets_produced']}",
            (
                f"Top Worker: {digest['top_worker']['worker_name']} - {digest['top_worker']['boxes']} boxes"
                if digest["top_worker"] else "Top Worker: Data not available"
            ),
            "",
            f"{labels['best_day']}:",
            digest["best_day"],
            "",
            f"{labels['worst_day']}:",
            digest["worst_day"],
            "",
            f"{labels['biggest_risk']}:",
            digest["largest_risk"],
            "",
            f"{labels['recommendation']}:",
            recommendation,
            "",
            "- Munshi AI",
        ]
    )


def build_weekly_digest(db: Session, factory_id: int, report_date: date, language: str = "hinglish") -> dict:
    start, end = week_range(report_date)
    digest = compute_weekly_digest(db, factory_id, start, end)
    return {**digest, "message_text": render_weekly_digest(digest, language), "language": language}

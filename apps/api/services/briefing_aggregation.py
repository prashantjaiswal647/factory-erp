from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from math import ceil

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import (
    AttendanceLog,
    BlankStock,
    BottomStock,
    Customer,
    DailyProduction,
    FactoryExpense,
    Machine,
    OutstandingBill,
    Payment,
    SalesInvoice,
)


CRITICAL_STOCK_DAYS = int(os.getenv("MORNING_BRIEFING_CRITICAL_STOCK_DAYS", "2"))
LOW_STOCK_DAYS = int(os.getenv("MORNING_BRIEFING_LOW_STOCK_DAYS", "7"))
BOTTOM_DAILY_USAGE_KG = Decimal(os.getenv("MORNING_BRIEFING_BOTTOM_DAILY_USAGE_KG", "100"))
BLANK_DAILY_USAGE_KG = Decimal(os.getenv("MORNING_BRIEFING_BLANK_DAILY_USAGE_KG", "100"))
OUTSTANDING_ALERT_AMOUNT = Decimal(os.getenv("MORNING_BRIEFING_OUTSTANDING_ALERT_AMOUNT", "100000"))
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _positive_or_none(value):
    if value is None:
        return None
    numeric = Decimal(str(value))
    return numeric if numeric > 0 else None


def _stock_days_left(total_qty, daily_usage: Decimal) -> int | None:
    quantity = _positive_or_none(total_qty)
    if quantity is None or daily_usage <= 0:
        return None
    return ceil(quantity / daily_usage)


def _stock_risk(label: str, days_left: int | None) -> dict | None:
    if days_left is None or days_left > LOW_STOCK_DAYS:
        return None
    severity = "critical" if days_left <= CRITICAL_STOCK_DAYS else "info"
    return {
        "severity": severity,
        "type": "low_stock",
        "label": label,
        "days_left": days_left,
        "message": f"{label} {days_left} day{'s' if days_left != 1 else ''} left",
    }


def collect_yesterday_factory_snapshot(db: Session, factory_id: int, briefing_date: date) -> dict:
    production_rows = (
        db.query(DailyProduction)
        .filter(DailyProduction.factory_id == factory_id, DailyProduction.date == briefing_date)
        .all()
    )
    produced = _positive_or_none(sum((row.total_boxes_made or 0) for row in production_rows)) if production_rows else None

    target = _positive_or_none(
        db.query(func.sum(Machine.target_output_per_shift))
        .filter(Machine.factory_id == factory_id, Machine.is_active.is_(True))
        .scalar()
    )
    gap = max(target - produced, Decimal("0")) if target is not None and produced is not None else None

    attendance_rows = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.factory_id == factory_id, AttendanceLog.date == briefing_date)
        .all()
    )
    present = sum(1 for row in attendance_rows if row.status == "Present" or row.is_present)
    absent = sum(1 for row in attendance_rows if row.status == "Absent" and not row.is_present)

    collections = _positive_or_none(
        db.query(func.sum(Payment.amount_paid))
        .filter(Payment.factory_id == factory_id, Payment.date == briefing_date)
        .scalar()
    )
    outstanding = _positive_or_none(
        db.query(func.sum(OutstandingBill.balance_amount))
        .filter(
            OutstandingBill.factory_id == factory_id,
            OutstandingBill.status.in_(("active", "partial")),
        )
        .scalar()
    )
    sales = _positive_or_none(
        db.query(func.sum(SalesInvoice.total_amount))
        .filter(
            SalesInvoice.factory_id == factory_id,
            SalesInvoice.date == briefing_date,
        )
        .scalar()
    )
    
    expenses = _positive_or_none(
        db.query(func.sum(FactoryExpense.amount))
        .filter(
            FactoryExpense.factory_id == factory_id,
            func.date(FactoryExpense.timestamp) == briefing_date
        )
        .scalar()
    )

    invoice_count = (
        db.query(func.count(SalesInvoice.id))
        .filter(
            SalesInvoice.factory_id == factory_id,
            SalesInvoice.date == briefing_date,
        )
        .scalar()
        or 0
    )
    bottom_days_left = _stock_days_left(
        db.query(func.sum(BottomStock.total_qty_kg))
        .filter(BottomStock.factory_id == factory_id)
        .scalar(),
        BOTTOM_DAILY_USAGE_KG,
    )
    blank_days_left = _stock_days_left(
        db.query(func.sum(BlankStock.total_qty_kg))
        .filter(BlankStock.factory_id == factory_id)
        .scalar(),
        BLANK_DAILY_USAGE_KG,
    )
    largest_outstanding = (
        db.query(
            Customer.name,
            func.sum(OutstandingBill.balance_amount).label("pending_amount"),
        )
        .join(
            OutstandingBill,
            OutstandingBill.customer_id == Customer.id,
        )
        .filter(
            Customer.factory_id == factory_id,
            OutstandingBill.factory_id == factory_id,
            OutstandingBill.status.in_(("active", "partial")),
        )
        .group_by(Customer.id, Customer.name)
        .having(func.sum(OutstandingBill.balance_amount) >= OUTSTANDING_ALERT_AMOUNT)
        .order_by(func.sum(OutstandingBill.balance_amount).desc(), Customer.name.asc())
        .first()
    )

    risk_items = [
        risk
        for risk in (
            _stock_risk("Bottom Roll", bottom_days_left),
            _stock_risk("Blank Stock", blank_days_left),
        )
        if risk is not None
    ]
    if largest_outstanding is not None:
        risk_items.append(
            {
                "severity": "warning",
                "type": "outstanding",
                "label": largest_outstanding.name,
                "pending_amount": _positive_or_none(largest_outstanding.pending_amount),
                "message": f"{largest_outstanding.name} outstanding payment",
            }
        )
    risk_items.sort(key=lambda item: (SEVERITY_ORDER[item["severity"]], item["type"], item["label"]))

    return {
        "date": briefing_date.isoformat(),
        "production": {
            "produced": produced,
            "target": target,
            "gap": gap,
        },
        "workers": {
            "present": present if attendance_rows and present > 0 else None,
            "absent": absent if attendance_rows and absent > 0 else None,
        },
        "collections": {
            "received": collections,
            "outstanding": outstanding,
        },
        "sales": {
            "invoice_count": invoice_count if invoice_count > 0 else None,
            "amount": sales,
            "collections_received": collections,
            "outstanding_amount": outstanding,
        },
        "expenses": {
            "total": expenses,
        },
        "risk_summary": {
            "bottom_days_left": bottom_days_left,
            "blank_days_left": blank_days_left,
        },
        "risk_items": risk_items,
    }

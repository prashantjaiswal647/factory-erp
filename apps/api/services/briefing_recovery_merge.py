"""P4.5 Deliverable 3: Daily Briefing + Recovery merge.

Augments the existing daily briefing with a recovery block:
  - Total outstanding + overdue
  - Yesterday's collections
  - Top 1 due customer
  - High-risk customer count
  - Inventory alert line

Two variants:
  - Owner: full financial section
  - Sub-Owner: operational section (no totals, no top-customer
               financial details, no per-customer due amounts)

All templates are deterministic Hinglish. No LLM. No fabrication.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from models import (
    Customer,
    OutstandingBill,
    Payment,
    User,
)


# ---------------------------------------------------------------------------
# Recovery data collection
# ---------------------------------------------------------------------------

def collect_recovery_snapshot(
    db: Session,
    factory_id: int,
    briefing_date: date,
) -> dict[str, Any]:
    """Read yesterday's collections + outstanding state.

    Pure read. No writes. No LLM.
    """
    today = briefing_date
    yesterday_start = today - timedelta(days=1)

    total_outstanding = (
        db.query(sql_func.coalesce(sql_func.sum(OutstandingBill.balance_amount), 0))
        .filter(OutstandingBill.factory_id == factory_id)
        .filter(OutstandingBill.balance_amount > 0)
        .filter(OutstandingBill.status.in_(["active", "partial"]))
        .scalar()
    )
    overdue_outstanding = (
        db.query(sql_func.coalesce(sql_func.sum(OutstandingBill.balance_amount), 0))
        .filter(OutstandingBill.factory_id == factory_id)
        .filter(OutstandingBill.balance_amount > 0)
        .filter(OutstandingBill.status.in_(["active", "partial"]))
        .filter(OutstandingBill.bill_date <= yesterday_start - timedelta(days=15))
        .scalar()
    )

    yesterday_collections = (
        db.query(sql_func.coalesce(sql_func.sum(Payment.amount_paid), 0))
        .filter(Payment.factory_id == factory_id)
        .filter(Payment.date == yesterday_start)
        .scalar()
    )

    # Top 1 due customer
    top_due = (
        db.query(
            Customer.id,
            Customer.name,
            sql_func.coalesce(sql_func.sum(OutstandingBill.balance_amount), 0).label("due"),
            sql_func.max(OutstandingBill.bill_date).label("last_bill_date"),
        )
        .join(OutstandingBill, OutstandingBill.customer_id == Customer.id)
        .filter(OutstandingBill.factory_id == factory_id)
        .filter(OutstandingBill.balance_amount > 0)
        .filter(OutstandingBill.status.in_(["active", "partial"]))
        .group_by(Customer.id, Customer.name)
        .order_by(sql_func.coalesce(sql_func.sum(OutstandingBill.balance_amount), 0).desc())
        .first()
    )

    high_risk_count = (
        db.query(sql_func.count(sql_func.distinct(OutstandingBill.customer_id)))
        .filter(OutstandingBill.factory_id == factory_id)
        .filter(OutstandingBill.balance_amount > 0)
        .filter(OutstandingBill.status.in_(["active", "partial"]))
        .filter(OutstandingBill.bill_date <= today - timedelta(days=30))
        .scalar()
    )

    return {
        "total_outstanding_paise": int(Decimal(str(total_outstanding or 0)) * 100),
        "overdue_outstanding_paise": int(Decimal(str(overdue_outstanding or 0)) * 100),
        "yesterday_collections_paise": int(Decimal(str(yesterday_collections or 0)) * 100),
        "top_due_customer_name": top_due.name if top_due else None,
        "top_due_amount_paise": int(Decimal(str(top_due.due or 0)) * 100) if top_due else 0,
        "top_due_days_old": (
            (today - top_due.last_bill_date).days if (top_due and top_due.last_bill_date) else 0
        ),
        "high_risk_customers_count": int(high_risk_count or 0),
    }


# ---------------------------------------------------------------------------
# Money formatting
# ---------------------------------------------------------------------------

def _inr(paise: int | None) -> str:
    if paise is None:
        return "—"
    rupees = Decimal(int(paise)) / Decimal(100)
    return f"₹{rupees:,.0f}"


def _inr_short(paise: int | None) -> str:
    if paise is None:
        return "—"
    rupees = Decimal(int(paise)) / Decimal(100)
    n = float(rupees)
    if n >= 10000000:
        return f"₹{n/10000000:.1f}Cr"
    if n >= 100000:
        return f"₹{n/100000:.1f}L"
    if n >= 1000:
        return f"₹{n/1000:.1f}K"
    return f"₹{n:.0f}"


# ---------------------------------------------------------------------------
# Recovery section renderers (Owner + Sub-Owner variants)
# ---------------------------------------------------------------------------

def render_recovery_section_owner(recovery: dict[str, Any]) -> str:
    """Full financial section. Owner only."""
    lines = [
        "💰 Recovery Snapshot",
        "",
        f"Outstanding: {_inr(recovery['total_outstanding_paise'])}",
        f"Overdue (15+): {_inr(recovery['overdue_outstanding_paise'])}",
        f"Yesterday Collections: {_inr(recovery['yesterday_collections_paise'])}",
    ]
    if recovery["top_due_customer_name"]:
        lines.append(
            "Top Due Customer: "
            f"{recovery['top_due_customer_name']}  "
            f"({_inr(recovery['top_due_amount_paise'])}, "
            f"{recovery['top_due_days_old']} days)"
        )
    if recovery["high_risk_customers_count"]:
        lines.append(
            f"🚨 High Risk Customers: {recovery['high_risk_customers_count']}"
        )
    return "\n".join(lines)


def render_recovery_section_subowner(recovery: dict[str, Any]) -> str:
    """Operational section. No customer names, no per-customer amounts.

    Shows collection effort + count, not customer-level financials.
    """
    lines = [
        "📊 Recovery Overview",
        "",
        f"Yesterday Collections: {_inr(recovery['yesterday_collections_paise'])}",
        f"Outstanding (factory-wide): {_inr_short(recovery['total_outstanding_paise'])}",
        f"Overdue (15+): {_inr_short(recovery['overdue_outstanding_paise'])}",
    ]
    if recovery["high_risk_customers_count"]:
        lines.append(
            f"High Risk Customers: {recovery['high_risk_customers_count']}  "
            "(Owner view only)"
        )
    else:
        lines.append("High Risk Customers: 0")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Daily briefing composition
# ---------------------------------------------------------------------------

def compose_daily_briefing_with_recovery(
    db: Session,
    factory_id: int,
    briefing_date: date,
    recipient: User,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the daily briefing text for a given recipient.

    Owner: full financial briefing (existing flow) + recovery section.
    Sub-Owner: operational briefing (no LLM) + recovery section.

    Returns dict with: message_text, role, recovery_snapshot
    """
    role = (recipient.role or "").strip()
    recovery = collect_recovery_snapshot(db, factory_id, briefing_date)

    if role == "Owner":
        # Owner gets the existing build_briefing (with LLM) + recovery tail.
        from services.briefing_service import build_briefing

        briefing = build_briefing(
            db,
            factory_id,
            briefing_date,
            recipient.full_name or recipient.username,
            recipient.preferred_language or "hinglish",
            summary_mode=True,
        )
        owner_section = render_recovery_section_owner(recovery)
        result = {
            "message_text": f"{briefing['message_text']}\n\n{owner_section}",
            "role": "Owner",
            "recovery_snapshot": recovery,
            "snapshot": briefing.get("snapshot", {}),
        }

    elif role == "Sub-Owner":
        # Sub-Owner gets an operational briefing (no LLM, no customer
        # financial details) + recovery section.
        operational = _render_operational_briefing(
            db, factory_id, briefing_date, recipient, snapshot, recovery
        )
        sub_section = render_recovery_section_subowner(recovery)
        result = {
            "message_text": f"{operational}\n\n{sub_section}",
            "role": "Sub-Owner",
            "recovery_snapshot": recovery,
            "snapshot": snapshot or {},
        }

    else:
        # Supervisor or other: minimal "no Telegram briefings" placeholder.
        result = {
            "message_text": "Briefing is not configured for this role.",
            "role": role or "Unknown",
            "recovery_snapshot": recovery,
            "snapshot": snapshot or {},
        }

    # Save/upsert snapshot
    from models import BriefingSnapshot
    from sqlalchemy.dialects.postgresql import insert
    import json
    
    # Calculate health_score
    health_score = None
    snap = result.get("snapshot")
    if snap and "factory_health" in snap:
        health_score = snap["factory_health"].get("overall_score")

    # Clean / serialize snapshot to be JSON compatible
    def make_serializable(obj):
        from datetime import date, datetime
        if isinstance(obj, dict):
            return {k: make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [make_serializable(x) for x in obj]
        elif isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return obj

    serializable_snap = make_serializable({
        "snapshot": result.get("snapshot"),
        "recovery_snapshot": result.get("recovery_snapshot"),
    })

    # Save snapshot
    existing_snap = db.query(BriefingSnapshot).filter(
        BriefingSnapshot.factory_id == factory_id,
        BriefingSnapshot.briefing_date == briefing_date,
        BriefingSnapshot.role == result["role"],
        BriefingSnapshot.user_id == recipient.id
    ).first()

    if existing_snap:
        existing_snap.message_text = result["message_text"]
        existing_snap.snapshot_json = serializable_snap
        existing_snap.health_score = health_score
    else:
        new_snap = BriefingSnapshot(
            factory_id=factory_id,
            user_id=recipient.id,
            role=result["role"],
            briefing_date=briefing_date,
            message_text=result["message_text"],
            snapshot_json=serializable_snap,
            health_score=health_score,
            status="generated"
        )
        db.add(new_snap)
    db.commit()

    return result


def _render_operational_briefing(
    db: Session,
    factory_id: int,
    briefing_date: date,
    recipient: User,
    snapshot: dict[str, Any] | None,
    recovery: dict[str, Any],
) -> str:
    """Sub-Owner variant. No customer financial detail. Operational only."""
    from services.briefing_aggregation import collect_yesterday_factory_snapshot

    snap = snapshot or collect_yesterday_factory_snapshot(db, factory_id, briefing_date)
    greeting = "Good Morning"
    name = (recipient.full_name or recipient.username or "").strip() or "there"
    date_label = briefing_date.strftime("%d %b %Y")

    production_boxes = 0
    try:
        production_boxes = int(snap.get("production", {}).get("total_boxes", 0) or 0)
    except (AttributeError, TypeError, ValueError):
        production_boxes = 0

    sales_rupees = 0
    try:
        sales_rupees = int(snap.get("sales", {}).get("total_amount_rupees", 0) or 0)
    except (AttributeError, TypeError, ValueError):
        sales_rupees = 0

    return (
        f"{greeting} {name}\n"
        f"Yesterday ({date_label}) Operational Summary\n\n"
        f"🏭 Production: {production_boxes:,} boxes\n"
        f"📦 Sales Volume: Rs {sales_rupees:,}\n"
        f"✅ Yesterday Collections: {_inr(recovery['yesterday_collections_paise'])}\n"
    )

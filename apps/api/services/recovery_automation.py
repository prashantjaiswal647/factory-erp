"""
P4.11 Recovery Automation Service

Provides factory-scoped functions for:
- Scanning outstanding bills and generating recovery suggestions
- Rendering Hindi/English reminder text
- Performing follow-up actions (copy, skip, mark done, snooze)
"""

from __future__ import annotations

from datetime import date
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from models import Customer, OutstandingBill, RecoveryFollowup, User

import logging

logger = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────────
HIGH_RISK_DUE_DAYS = 15
HIGH_RISK_AMOUNT_PAISE = 100_00_000  # ₹1,00,000 in paise
PAISE_PER_RUPEE = Decimal("100")


def _now() -> datetime:
    """UTC-aware now."""
    return datetime.now(timezone.utc)


def _today_utc() -> date:
    """UTC today as a date object."""
    return _now().date()


# ── suggestion engine ─────────────────────────────────────────────────────

def generate_recovery_suggestions(
    db: Session,
    factory_id: int,
    current_user: User,
) -> list[dict]:
    """
    Scan active/partial OutstandingBill rows with balance > 0, group by
    customer, identify high-risk customers (due > 15 days or total amount
    > ₹1,00,000), and create RecoveryFollowup rows (status='suggested').

    Returns a list of dicts summarising the suggestions created.
    Never raises — logs a warning on error.
    """
    try:
        # 1. Fetch qualifying bills scoped to factory
        bills = (
            db.query(OutstandingBill)
            .filter(
                OutstandingBill.factory_id == factory_id,
                OutstandingBill.balance_amount > 0,
                OutstandingBill.status.in_(["active", "partial"]),
            )
            .all()
        )

        if not bills:
            return []

        # 2. Group by customer
        customer_bills: dict[int, list[OutstandingBill]] = {}
        for b in bills:
            customer_bills.setdefault(b.customer_id, []).append(b)

        today = _today_utc()
        created: list[dict] = []

        for customer_id, cust_bills in customer_bills.items():
            try:
                # Aggregate: total balance and earliest bill date
                total_balance = sum(
                    (Decimal(str(b.balance_amount)) for b in cust_bills),
                    Decimal("0"),
                )
                earliest_bill_date = min(
                    b.bill_date for b in cust_bills if b.bill_date
                )
                due_days = (today - earliest_bill_date).days if earliest_bill_date else 0
                total_balance_paise = int(total_balance * PAISE_PER_RUPEE)

                # 3. High-risk check
                is_high_risk = (
                    due_days > HIGH_RISK_DUE_DAYS
                    or total_balance_paise > HIGH_RISK_AMOUNT_PAISE
                )
                if not is_high_risk:
                    continue

                # 4. Create RecoveryFollowup row(s) per customer
                #    Create one followup row per bill for audit granularity.
                for bill in cust_bills:
                    bal_paise = int(
                        Decimal(str(bill.balance_amount)) * PAISE_PER_RUPEE
                    )
                    bill_due_days = (
                        (today - bill.bill_date).days if bill.bill_date else 0
                    )

                    followup = RecoveryFollowup(
                        factory_id=factory_id,
                        customer_id=customer_id,
                        outstanding_bill_id=bill.id,
                        suggested_amount_paise=bal_paise,
                        due_days=bill_due_days,
                        status="suggested",
                        created_by_user_id=(
                            current_user.id
                            if hasattr(current_user, "id")
                            and current_user.id is not None
                            else 0
                        ),
                        created_at=_now(),
                        updated_at=_now(),
                    )
                    db.add(followup)

                db.flush()

                # 5. Build summary
                customer = db.query(Customer).filter_by(
                    id=customer_id, factory_id=factory_id
                ).first()
                created.append(
                    {
                        "customer_id": customer_id,
                        "customer_name": customer.name if customer else "Unknown",
                        "total_balance_paise": total_balance_paise,
                        "due_days": due_days,
                        "bill_count": len(cust_bills),
                        "status": "suggested",
                    }
                )

            except Exception as inner_err:
                logger.warning(
                    "generate_recovery_suggestions: skipped customer_id=%s: %s",
                    customer_id,
                    inner_err,
                )
                continue

        db.commit()
        return created

    except Exception as exc:
        logger.warning("generate_recovery_suggestions failed: %s", exc)
        db.rollback()
        return []


# ── reminder rendering ────────────────────────────────────────────────────

def render_reminder_text(
    customer_name: str,
    amount_paise: int,
    due_days: int,
    factory_name: str,
) -> str:
    """
    Return a bilingual (Hindi/English) reminder message.

    *amount_paise* is converted to rupees for display.
    """
    try:
        amount_rupees = Decimal(str(amount_paise)) / PAISE_PER_RUPEE
        # Strip trailing zeros for a clean look
        if amount_rupees == amount_rupees.to_integral_value():
            amount_display = str(int(amount_rupees))
        else:
            amount_display = f"{amount_rupees:.2f}"

        return (
            f"Namaste {customer_name} ji,\n"
            f"Aapka ₹{amount_display} payment {due_days} din se pending hai.\n"
            f"Kripya payment update karein.\n\n"
            f"* {factory_name}"
        )
    except Exception as exc:
        logger.warning("render_reminder_text failed: %s", exc)
        return ""


# ── action helpers ─────────────────────────────────────────────────────────

def _update_recovery_followup_status(
    db: Session,
    factory_id: int,
    customer_id: int,
    user_id: int,
    new_status: str,
    snooze_days: int | None = None,
) -> bool:
    """
    Low-level helper: update the latest suggested/open RecoveryFollowup for a
    customer to *new_status*. Returns True on success, False on error/missing.
    Never raises.
    """
    try:
        now = _now()
        # Pick the most recent non-terminal followup for this customer
        followup = (
            db.query(RecoveryFollowup)
            .filter(
                RecoveryFollowup.factory_id == factory_id,
                RecoveryFollowup.customer_id == customer_id,
                RecoveryFollowup.status.in_([
                    "suggested", "copied", "snoozed",
                ]),
            )
            .order_by(RecoveryFollowup.id.desc())
            .first()
        )

        if followup is None:
            logger.warning(
                "No actionable RecoveryFollowup for factory=%s customer=%s",
                factory_id,
                customer_id,
            )
            return False

        followup.status = new_status
        followup.last_action_at = now
        followup.updated_at = now

        if new_status == "snoozed" and snooze_days is not None:
            followup.snoozed_until = now + timedelta(days=snooze_days)

        db.commit()
        return True

    except Exception as exc:
        logger.warning(
            "Failed to update RecoveryFollowup (factory=%s, customer=%s, "
            "status=%s): %s",
            factory_id,
            customer_id,
            new_status,
            exc,
        )
        db.rollback()
        return False


def action_copy_reminder(
    db: Session,
    factory_id: int,
    customer_id: int,
    user_id: int,
) -> bool:
    """Mark the latest RecoveryFollowup as 'copied'."""
    return _update_recovery_followup_status(
        db, factory_id, customer_id, user_id, "copied",
    )


def action_skip(
    db: Session,
    factory_id: int,
    customer_id: int,
    user_id: int,
) -> bool:
    """Mark the latest RecoveryFollowup as 'skipped'."""
    return _update_recovery_followup_status(
        db, factory_id, customer_id, user_id, "skipped",
    )


def action_mark_done(
    db: Session,
    factory_id: int,
    customer_id: int,
    user_id: int,
) -> bool:
    """Mark the latest RecoveryFollowup as 'followup_done'."""
    return _update_recovery_followup_status(
        db, factory_id, customer_id, user_id, "followup_done",
    )


def action_snooze(
    db: Session,
    factory_id: int,
    customer_id: int,
    user_id: int,
    days: int = 3,
) -> bool:
    """
    Mark the latest RecoveryFollowup as 'snoozed' with snoozed_until set to
    *days* from now.
    """
    return _update_recovery_followup_status(
        db, factory_id, customer_id, user_id, "snoozed", snooze_days=days,
    )
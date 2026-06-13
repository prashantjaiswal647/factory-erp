"""P4.11: Recovery Automation unit tests.

Tests the recovery_automation service directly:
- High-risk suggestion generation (due > 15 days or amount > ₹1L)
- Reminder text rendering
- Follow-up actions: copy, skip, mark done, snooze
- Cross-factory isolation
"""

from __future__ import annotations

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import (
    Customer,
    Factory,
    OutstandingBill,
    RecoveryFollowup,
    User,
)


# ---------------------------------------------------------------------------
# Fixture: in-memory sqlite DB
# ---------------------------------------------------------------------------


@pytest.fixture()
def recovery_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Factory A (main factory)
        factory_a = Factory(id=1, name="Factory A", subscription_status="active")
        # Factory B (for cross-factory test)
        factory_b = Factory(id=2, name="Factory B", subscription_status="active")

        owner_a = User(
            id=10,
            factory_id=1,
            username="owner-a",
            full_name="Owner A",
            role="Owner",
            is_active=True,
            password_hash="-",
        )
        owner_b = User(
            id=20,
            factory_id=2,
            username="owner-b",
            full_name="Owner B",
            role="Owner",
            is_active=True,
            password_hash="-",
        )

        # Customers for factory A
        customer_high_risk = Customer(
            id=1,
            factory_id=1,
            name="High Risk Co",
            phone_number="+91-1111111111",
        )
        customer_normal = Customer(
            id=2,
            factory_id=1,
            name="Normal Co",
            phone_number="+91-2222222222",
        )
        customer_snoozed = Customer(
            id=3,
            factory_id=1,
            name="Snoozed Co",
            phone_number="+91-3333333333",
        )

        # Customer for factory B
        customer_b = Customer(
            id=4,
            factory_id=2,
            name="Factory B Customer",
            phone_number="+91-4444444444",
        )

        db.add_all([
            factory_a, factory_b,
            owner_a, owner_b,
            customer_high_risk, customer_normal, customer_snoozed,
            customer_b,
        ])
        db.commit()

        yield db, factory_a, factory_b, owner_a, owner_b, customer_high_risk, customer_normal, customer_snoozed, customer_b
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from services.recovery_automation import (
    generate_recovery_suggestions,
    render_reminder_text,
    action_copy_reminder,
    action_skip,
    action_mark_done,
    action_snooze,
    _today_utc,
)


# ---------------------------------------------------------------------------
# Test 1: High-risk suggestion generation
# ---------------------------------------------------------------------------


def test_high_risk_generates_suggestions(recovery_db):
    """Seed 3 customers (high-risk, normal, snoozed). Assert suggestions
    returned for high-risk only."""
    db, factory_a, _, owner_a, _, customer_high_risk, customer_normal, customer_snoozed, _ = recovery_db

    today = _today_utc()

    # Bill 1: high-risk — ₹3,00,000 due, 18 days overdue
    bill_high = OutstandingBill(
        factory_id=1,
        customer_id=customer_high_risk.id,
        tracking_number="INV-HR-001",
        bill_date=today - timedelta(days=18),
        bill_amount=Decimal("300000.00"),
        amount_paid=Decimal("0.00"),
        balance_amount=Decimal("300000.00"),
        status="active",
    )
    # Bill 2: normal — ₹500 due, 5 days overdue
    bill_normal = OutstandingBill(
        factory_id=1,
        customer_id=customer_normal.id,
        tracking_number="INV-NR-001",
        bill_date=today - timedelta(days=5),
        bill_amount=Decimal("500.00"),
        amount_paid=Decimal("0.00"),
        balance_amount=Decimal("500.00"),
        status="active",
    )
    # Bill 3: snoozed customer — small balance, not high-risk
    bill_snoozed = OutstandingBill(
        factory_id=1,
        customer_id=customer_snoozed.id,
        tracking_number="INV-SN-001",
        bill_date=today - timedelta(days=3),
        bill_amount=Decimal("50000.00"),
        amount_paid=Decimal("0.00"),
        balance_amount=Decimal("50000.00"),
        status="active",
    )
    db.add_all([bill_high, bill_normal, bill_snoozed])
    db.commit()

    # Pre-seed a snoozed RecoveryFollowup for the snoozed customer
    snoozed_followup = RecoveryFollowup(
        factory_id=1,
        customer_id=customer_snoozed.id,
        outstanding_bill_id=bill_snoozed.id,
        suggested_amount_paise=5000000,
        due_days=3,
        status="snoozed",
        created_by_user_id=owner_a.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        snoozed_until=datetime.now(timezone.utc) + timedelta(days=3),
    )
    db.add(snoozed_followup)
    db.commit()

    suggestions = generate_recovery_suggestions(db, 1, owner_a)

    # Only the high-risk customer should generate suggestions
    customer_ids = {s["customer_id"] for s in suggestions}
    assert customer_high_risk.id in customer_ids, "High-risk customer should have suggestions"
    assert customer_normal.id not in customer_ids, "Normal customer should NOT have suggestions"
    assert customer_snoozed.id not in customer_ids, "Snoozed customer should NOT have suggestions"

    # Verify high-risk suggestion details
    hr_suggestion = [s for s in suggestions if s["customer_id"] == customer_high_risk.id][0]
    assert hr_suggestion["customer_name"] == "High Risk Co"
    assert hr_suggestion["total_balance_paise"] == 30000000  # ₹3,00,000 in paise
    assert hr_suggestion["due_days"] >= 18
    assert hr_suggestion["bill_count"] == 1
    assert hr_suggestion["status"] == "suggested"


# ---------------------------------------------------------------------------
# Test 2: Reminder text rendering
# ---------------------------------------------------------------------------


def test_reminder_text_generated_correctly(recovery_db):
    """Call render_reminder_text with known params. Assert Hindi template
    contains customer name, amount, days, factory name. Assert no raw paise
    number visible."""
    text = render_reminder_text(
        customer_name="ABC Traders",
        amount_paise=30000000,   # ₹3,00,000
        due_days=18,
        factory_name="Factory A",
    )

    # Must contain customer name
    assert "ABC Traders" in text
    # Must contain amount in rupees (not paise)
    assert "₹3,00,000" in text or "₹300000" in text
    # Must contain due days
    assert "18" in text
    # Must contain factory name
    assert "Factory A" in text
    # Must contain Hindi greeting
    assert "Namaste" in text
    assert "ji" in text
    # Must NOT contain raw paise number
    assert "30000000" not in text


# ---------------------------------------------------------------------------
# Test 3: Copy action
# ---------------------------------------------------------------------------


def test_copy_action_logs_followup(recovery_db):
    """Seed a RecoveryFollowup with status='suggested', call action_copy_reminder,
    assert status='copied' and last_action_at is set."""
    db, factory_a, _, owner_a, _, customer_high_risk, _, _, _ = recovery_db

    today = _today_utc()
    bill = OutstandingBill(
        factory_id=1,
        customer_id=customer_high_risk.id,
        tracking_number="INV-COPY-001",
        bill_date=today - timedelta(days=18),
        bill_amount=Decimal("300000.00"),
        amount_paid=Decimal("0.00"),
        balance_amount=Decimal("300000.00"),
        status="active",
    )
    db.add(bill)
    db.commit()

    followup = RecoveryFollowup(
        factory_id=1,
        customer_id=customer_high_risk.id,
        outstanding_bill_id=bill.id,
        suggested_amount_paise=30000000,
        due_days=18,
        status="suggested",
        created_by_user_id=owner_a.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(followup)
    db.commit()

    result = action_copy_reminder(db, 1, customer_high_risk.id, owner_a.id)
    assert result is True, "action_copy_reminder should return True"

    db.refresh(followup)
    assert followup.status == "copied"
    assert followup.last_action_at is not None


# ---------------------------------------------------------------------------
# Test 4: Snooze hides suggestion
# ---------------------------------------------------------------------------


def test_snooze_hides_suggestion(recovery_db):
    """Seed a RecoveryFollowup with status='suggested', call action_snooze(days=3),
    assert status='snoozed', snoozed_until within 3 days from now."""
    db, factory_a, _, owner_a, _, customer_high_risk, _, _, _ = recovery_db

    today = _today_utc()
    bill = OutstandingBill(
        factory_id=1,
        customer_id=customer_high_risk.id,
        tracking_number="INV-SNOOZE-001",
        bill_date=today - timedelta(days=18),
        bill_amount=Decimal("300000.00"),
        amount_paid=Decimal("0.00"),
        balance_amount=Decimal("300000.00"),
        status="active",
    )
    db.add(bill)
    db.commit()

    followup = RecoveryFollowup(
        factory_id=1,
        customer_id=customer_high_risk.id,
        outstanding_bill_id=bill.id,
        suggested_amount_paise=30000000,
        due_days=18,
        status="suggested",
        created_by_user_id=owner_a.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(followup)
    db.commit()

    now = datetime.now(timezone.utc)
    result = action_snooze(db, 1, customer_high_risk.id, owner_a.id, days=3)
    assert result is True, "action_snooze should return True"

    db.refresh(followup)
    assert followup.status == "snoozed"
    assert followup.snoozed_until is not None
    # snoozed_until should be within 3 days from now (with a small tolerance)
    expected_min = now + timedelta(days=3) - timedelta(seconds=5)
    expected_max = now + timedelta(days=3) + timedelta(seconds=5)
    assert expected_min <= followup.snoozed_until.replace(tzinfo=timezone.utc) <= expected_max, (
        f"snoozed_until {followup.snoozed_until} not within 3 days of {now}"
    )


# ---------------------------------------------------------------------------
# Test 5: Followup done status
# ---------------------------------------------------------------------------


def test_followup_done_status_persists(recovery_db):
    """Seed a RecoveryFollowup with status='suggested', call action_mark_done,
    assert status='followup_done'."""
    db, factory_a, _, owner_a, _, customer_high_risk, _, _, _ = recovery_db

    today = _today_utc()
    bill = OutstandingBill(
        factory_id=1,
        customer_id=customer_high_risk.id,
        tracking_number="INV-DONE-001",
        bill_date=today - timedelta(days=18),
        bill_amount=Decimal("300000.00"),
        amount_paid=Decimal("0.00"),
        balance_amount=Decimal("300000.00"),
        status="active",
    )
    db.add(bill)
    db.commit()

    followup = RecoveryFollowup(
        factory_id=1,
        customer_id=customer_high_risk.id,
        outstanding_bill_id=bill.id,
        suggested_amount_paise=30000000,
        due_days=18,
        status="suggested",
        created_by_user_id=owner_a.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(followup)
    db.commit()

    result = action_mark_done(db, 1, customer_high_risk.id, owner_a.id)
    assert result is True, "action_mark_done should return True"

    db.refresh(followup)
    assert followup.status == "followup_done"
    assert followup.last_action_at is not None


# ---------------------------------------------------------------------------
# Test 6: Cross-factory customer blocked
# ---------------------------------------------------------------------------


def test_cross_factory_customer_blocked(recovery_db):
    """Factory A has high-risk customer. Factory B user calls action_copy_reminder
    with customer_id from factory A. Assert return False, no followup row
    created for factory B."""
    (
        db, factory_a, factory_b, owner_a, owner_b,
        customer_high_risk, _, _, customer_b,
    ) = recovery_db

    today = _today_utc()
    # Bill for customer_high_risk in factory A
    bill_a = OutstandingBill(
        factory_id=1,
        customer_id=customer_high_risk.id,
        tracking_number="INV-CROSS-001",
        bill_date=today - timedelta(days=18),
        bill_amount=Decimal("300000.00"),
        amount_paid=Decimal("0.00"),
        balance_amount=Decimal("300000.00"),
        status="active",
    )
    db.add(bill_a)
    db.commit()

    # Followup for customer_high_risk in factory A
    followup_a = RecoveryFollowup(
        factory_id=1,
        customer_id=customer_high_risk.id,
        outstanding_bill_id=bill_a.id,
        suggested_amount_paise=30000000,
        due_days=18,
        status="suggested",
        created_by_user_id=owner_a.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(followup_a)
    db.commit()

    # Factory B user tries to act on factory A's customer
    result = action_copy_reminder(db, 2, customer_high_risk.id, owner_b.id)
    assert result is False, "Cross-factory action should return False"

    # No followup row should exist for factory B with this customer
    b_followups = (
        db.query(RecoveryFollowup)
        .filter(
            RecoveryFollowup.factory_id == 2,
            RecoveryFollowup.customer_id == customer_high_risk.id,
        )
        .all()
    )
    assert len(b_followups) == 0, (
        "No followup row should be created for factory B"
    )

    # Original followup should remain unchanged
    db.refresh(followup_a)
    assert followup_a.status == "suggested", (
        "Original followup should not be modified"
    )


# ---------------------------------------------------------------------------
# Test 7: Skip action
# ---------------------------------------------------------------------------


def test_skip_action(recovery_db):
    """Seed a RecoveryFollowup with status='suggested', call action_skip,
    assert status='skipped'."""
    db, factory_a, _, owner_a, _, customer_high_risk, _, _, _ = recovery_db

    today = _today_utc()
    bill = OutstandingBill(
        factory_id=1,
        customer_id=customer_high_risk.id,
        tracking_number="INV-SKIP-001",
        bill_date=today - timedelta(days=18),
        bill_amount=Decimal("300000.00"),
        amount_paid=Decimal("0.00"),
        balance_amount=Decimal("300000.00"),
        status="active",
    )
    db.add(bill)
    db.commit()

    followup = RecoveryFollowup(
        factory_id=1,
        customer_id=customer_high_risk.id,
        outstanding_bill_id=bill.id,
        suggested_amount_paise=30000000,
        due_days=18,
        status="suggested",
        created_by_user_id=owner_a.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(followup)
    db.commit()

    result = action_skip(db, 1, customer_high_risk.id, owner_a.id)
    assert result is True, "action_skip should return True"

    db.refresh(followup)
    assert followup.status == "skipped"
    assert followup.last_action_at is not None

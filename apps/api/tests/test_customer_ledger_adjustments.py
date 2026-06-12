from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import Customer, CustomerLedgerAdjustment, Factory, OutstandingBill, User
from routers.sales import (
    LedgerAdjustmentCreate,
    OpeningOutstandingCreate,
    OpeningOutstandingUpdate,
    create_customer_adjustment,
    create_opening_outstanding,
    delete_opening_outstanding,
    get_customer_ledger,
    get_sales_outstanding,
    update_opening_outstanding,
)
from services.accounting import apply_payment_to_outstanding_bills, create_outstanding_bill, sync_customer_balance_from_bills


def _db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _setup_customer(db, opening_due: Decimal = Decimal("0.00")):
    db.add(Factory(id=1, name="Test Factory"))
    db.add(User(id=1, username="owner", role="Owner", factory_id=1, password_hash="hash"))
    customer = Customer(
        factory_id=1,
        name="Ledger Customer",
        phone_number="9999999999",
        previous_due=Decimal("0.00"),
        total_due=Decimal("0.00"),
        balance_amount=Decimal("0.00"),
        pending_balance=Decimal("0.00"),
        pending_dues=0,
    )
    db.add(customer)
    db.flush()
    if opening_due:
        create_outstanding_bill(
            db,
            factory_id=1,
            customer_id=customer.id,
            source_type="invoice",
            tracking_number="INV-TEST",
            bill_date=__import__("datetime").date.today(),
            bill_amount=opening_due,
        )
        sync_customer_balance_from_bills(db, 1, customer)
    db.commit()
    return customer


def _owner():
    return SimpleNamespace(
        id=1,
        factory_id=1,
        role="Owner",
        full_name="Owner User",
        username="owner",
    )


def test_add_then_reduce_balance_preserves_invoice_total():
    db = _db()
    customer = _setup_customer(db, Decimal("42979.00"))
    original_invoice = db.query(OutstandingBill).filter(OutstandingBill.source_type == "invoice").one()

    added = create_customer_adjustment(
        customer.id,
        LedgerAdjustmentCreate(
            adjustment_type="add_balance",
            amount=Decimal("3000.00"),
            reason="Previous bill not entered",
        ),
        _owner(),
        db,
    )
    assert added.previous_outstanding == Decimal("42979.00")
    assert added.new_outstanding == Decimal("45979.00")

    reduced = create_customer_adjustment(
        customer.id,
        LedgerAdjustmentCreate(
            adjustment_type="reduce_balance",
            amount=Decimal("5000.00"),
            reason="Rate correction",
        ),
        _owner(),
        db,
    )
    assert reduced.new_outstanding == Decimal("40979.00")
    db.refresh(original_invoice)
    assert original_invoice.bill_amount == Decimal("42979.00")
    assert db.query(CustomerLedgerAdjustment).count() == 2


def test_no_active_bill_add_creates_manual_outstanding():
    db = _db()
    customer = _setup_customer(db)
    result = create_customer_adjustment(
        customer.id,
        LedgerAdjustmentCreate(
            adjustment_type="add_balance",
            amount=Decimal("2000.00"),
            reason="Opening balance correction",
        ),
        _owner(),
        db,
    )
    assert result.new_outstanding == Decimal("2000.00")
    manual_bill = db.query(OutstandingBill).filter(OutstandingBill.source_type == "manual_adjustment").one()
    assert manual_bill.balance_amount == Decimal("2000.00")


def test_reduce_cannot_exceed_outstanding():
    db = _db()
    customer = _setup_customer(db, Decimal("1000.00"))
    with pytest.raises(HTTPException) as exc:
        create_customer_adjustment(
            customer.id,
            LedgerAdjustmentCreate(
                adjustment_type="reduce_balance",
                amount=Decimal("1000.01"),
                reason="Discount",
            ),
            _owner(),
            db,
        )
    assert exc.value.status_code == 400


def test_reduce_balance_decreases_outstanding_without_payment_history():
    db = _db()
    customer = _setup_customer(db, Decimal("5000.00"))
    result = create_customer_adjustment(
        customer.id,
        LedgerAdjustmentCreate(
            adjustment_type="reduce_balance",
            amount=Decimal("1200.00"),
            reason="Discount",
        ),
        _owner(),
        db,
    )
    assert result.previous_outstanding == Decimal("5000.00")
    assert result.adjustment_amount == Decimal("1200.00")
    assert result.new_outstanding == Decimal("3800.00")
    from models import PaymentCollection
    assert db.query(PaymentCollection).filter(PaymentCollection.customer_id == customer.id).count() == 0


def test_adjustment_reason_is_required():
    with pytest.raises(ValidationError):
        LedgerAdjustmentCreate(
            adjustment_type="add_balance",
            amount=Decimal("100.00"),
            reason="   ",
        )


def test_opening_outstanding_is_source_aware_editable_and_soft_deletable():
    db = _db()
    customer = _setup_customer(db)
    owner = _owner()
    created = create_opening_outstanding(
        customer.id,
        OpeningOutstandingCreate(amount=Decimal("10000.00"), date=date.today(), reason="Old bill balance"),
        owner,
        db,
    )
    bill = db.query(OutstandingBill).filter(OutstandingBill.id == created.id).one()
    assert bill.source_type == "opening_outstanding"
    assert bill.invoice_document_id is None
    assert bill.order_id is None

    updated = update_opening_outstanding(
        customer.id,
        bill.id,
        OpeningOutstandingUpdate(new_amount=Decimal("8000.00"), reason="Onboarding correction"),
        owner,
        db,
    )
    assert updated.difference == Decimal("-2000.00")
    assert updated.stock_impact is False

    deleted = delete_opening_outstanding(customer.id, bill.id, "Duplicate old balance", owner, db)
    assert deleted.customer_total_outstanding == Decimal("0.00")
    db.refresh(bill)
    assert bill.deleted_at is not None
    assert bill.status == "cancelled"


def test_payment_allocation_prioritizes_opening_before_older_invoice():
    db = _db()
    customer = _setup_customer(db)
    invoice = create_outstanding_bill(
        db, factory_id=1, customer_id=customer.id, source_type="invoice",
        tracking_number="INV-OLD", bill_date=date.today() - timedelta(days=30),
        bill_amount=Decimal("5000.00"),
    )
    opening = create_outstanding_bill(
        db, factory_id=1, customer_id=customer.id, source_type="opening_outstanding",
        tracking_number="OPEN-NEWER", bill_date=date.today(), bill_amount=Decimal("10000.00"),
    )
    apply_payment_to_outstanding_bills(
        db, factory_id=1, customer_id=customer.id, amount=Decimal("12000.00"),
        payment_mode="Cash", collection_date=date.today(), created_by_user_id=1,
    )
    assert opening.balance_amount == Decimal("0.00")
    assert invoice.balance_amount == Decimal("3000.00")
    assert sum(payment.amount_allocated for payment in opening.payments) == Decimal("10000.00")
    assert sum(payment.amount_allocated for payment in invoice.payments) == Decimal("2000.00")


@pytest.mark.parametrize(
    ("source_type", "amount"),
    [
        ("opening_outstanding", Decimal("5000.00")),
        ("invoice", Decimal("3000.00")),
        ("manual_adjustment", Decimal("2000.00")),
    ],
)
def test_fully_paid_source_is_settled_and_absent_from_outstanding(source_type, amount):
    db = _db()
    customer = _setup_customer(db)
    bill = create_outstanding_bill(
        db,
        factory_id=1,
        customer_id=customer.id,
        source_type=source_type,
        tracking_number=f"TEST-{source_type}",
        bill_date=date.today(),
        bill_amount=amount,
    )
    sync_customer_balance_from_bills(db, 1, customer)

    unapplied = apply_payment_to_outstanding_bills(
        db,
        factory_id=1,
        customer_id=customer.id,
        amount=amount,
        payment_mode="Cash",
        collection_date=date.today(),
        created_by_user_id=1,
    )
    sync_customer_balance_from_bills(db, 1, customer)
    db.commit()

    db.refresh(bill)
    assert unapplied == Decimal("0.00")
    assert bill.balance_amount == Decimal("0.00")
    assert bill.status == "settled"
    assert get_sales_outstanding(_owner(), db).customers == []


def test_advance_only_customer_is_absent_from_outstanding():
    db = _db()
    customer = _setup_customer(db)
    customer.advance_balance = Decimal("750.00")
    db.commit()

    response = get_sales_outstanding(_owner(), db)

    assert response.grand_total_outstanding == Decimal("0.00")
    assert response.customers == []


def test_outstanding_grouping_and_customer_ledger_timeline():
    db = _db()
    customer = _setup_customer(db)
    owner = _owner()
    create_opening_outstanding(
        customer.id,
        OpeningOutstandingCreate(amount=Decimal("1000.00"), reason="Old balance"),
        owner,
        db,
    )
    create_customer_adjustment(
        customer.id,
        LedgerAdjustmentCreate(adjustment_type="add_balance", amount=Decimal("500.00"), reason="Rate correction"),
        owner,
        db,
    )
    response = get_sales_outstanding(owner, db)
    assert response.source_totals["opening_outstanding"] == Decimal("1000.00")
    assert response.source_totals["manual_adjustment"] == Decimal("500.00")
    labels = {bill.source_label for bill in response.customers[0].bills}
    assert "Opening Outstanding / Old Balance" in labels
    assert "Manual Adjustment" in labels

    ledger = get_customer_ledger(customer.id, owner, db)
    assert ledger["current_balance"] == Decimal("1500.00")
    assert {entry["type"] for entry in ledger["entries"]} >= {"opening_outstanding", "manual_adjustment"}

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
from routers.sales import LedgerAdjustmentCreate, create_customer_adjustment
from services.accounting import create_outstanding_bill, sync_customer_balance_from_bills


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

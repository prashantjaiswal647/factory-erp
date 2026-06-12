from datetime import date
from decimal import Decimal

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import Customer, Factory, FinalProductStock, InvoiceDocument, OutstandingBill, User
from routers.sales import add_sale_invoice
from schemas import DailySaleCreate
from services.accounting import create_outstanding_bill


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db, *, opening_due: str = "0", advance: str = "0"):
    factory = Factory(name="Invoice Factory", invoice_prefix="INV-")
    db.add(factory)
    db.flush()
    user = User(
        factory_id=factory.id,
        username="owner",
        full_name="Owner",
        role="Owner",
        password_hash="hash",
        is_verified=True,
    )
    customer = Customer(
        factory_id=factory.id,
        name="Invoice Customer",
        phone="9000000000",
        advance_balance=Decimal(advance),
    )
    stock = FinalProductStock(
        factory_id=factory.id,
        product_size_ml=210,
        variety="Plain White",
        packaging_size_name="50 Pcs x 20",
        pieces_per_packet=50,
        packets_per_box_limit=20,
        total_boxes=10,
        loose_packets=0,
        current_quantity=10,
    )
    db.add_all([user, customer, stock])
    db.flush()
    if Decimal(opening_due) > 0:
        create_outstanding_bill(
            db,
            factory_id=factory.id,
            customer_id=customer.id,
            source_type="opening_outstanding",
            tracking_number=f"OPEN-{customer.id}",
            bill_date=date(2026, 6, 1),
            bill_amount=Decimal(opening_due),
        )
    db.commit()
    return user, customer, stock


def _payload(customer_id: int, stock_id: int, *, boxes: int = 2):
    return DailySaleCreate.model_validate({
        "date": "2026-06-12",
        "customer_id": customer_id,
        "amount_paid": 0,
        "legal_invoice_type": "bill_of_supply",
        "items": [{
            "product_id": stock_id,
            "product_size_ml": 210,
            "variety": "Plain White",
            "packaging_size_name": "50 Pcs x 20",
            "boxes_sold": boxes,
            "loose_packets_sold": 0,
            "rate_per_box": 500,
            "rate_per_packet": 25,
            "packets_per_box": 20,
        }],
    })


@pytest.mark.parametrize(
    ("opening_due", "advance", "expected_customer_due", "expected_invoice_due"),
    [
        ("0", "0", Decimal("1000.00"), Decimal("1000.00")),
        ("300", "0", Decimal("1300.00"), Decimal("1000.00")),
        ("0", "400", Decimal("600.00"), Decimal("600.00")),
    ],
)
def test_sales_invoice_creation_updates_stock_and_source_ledger(
    opening_due, advance, expected_customer_due, expected_invoice_due,
):
    db = _session()
    user, customer, stock = _seed(db, opening_due=opening_due, advance=advance)

    response = add_sale_invoice(_payload(customer.id, stock.id), BackgroundTasks(), current_user=user, db=db)

    db.refresh(stock)
    db.refresh(customer)
    invoice = db.query(InvoiceDocument).filter_by(id=response.invoice_document_id).one()
    invoice_bill = db.query(OutstandingBill).filter_by(invoice_document_id=invoice.id).one()
    assert stock.current_quantity == 8
    assert invoice_bill.source_type == "invoice"
    assert invoice_bill.bill_amount == Decimal("1000.00")
    assert invoice_bill.balance_amount == expected_invoice_due
    assert customer.total_due == expected_customer_due
    assert Decimal(invoice.payload_json["invoice"]["previous_due"]) == Decimal(opening_due)


def test_sales_invoice_insufficient_stock_returns_validation_error_without_500():
    db = _session()
    user, customer, stock = _seed(db)

    with pytest.raises(HTTPException) as exc_info:
        add_sale_invoice(_payload(customer.id, stock.id, boxes=11), BackgroundTasks(), current_user=user, db=db)

    assert exc_info.value.status_code == 400
    assert "Insufficient stock" in exc_info.value.detail
    assert db.query(InvoiceDocument).count() == 0
    assert db.query(OutstandingBill).filter(OutstandingBill.source_type == "invoice").count() == 0

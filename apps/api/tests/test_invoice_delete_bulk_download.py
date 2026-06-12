from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import ActivityLog, Customer, Factory, InvoiceDocument, OutstandingBill
from routers.sales import (
    InvoiceDeleteRequest,
    allocate_invoice_number,
    bulk_download_invoices,
    delete_invoice_document,
)


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _owner(factory_id: int, role: str = "Owner"):
    return SimpleNamespace(
        id=1,
        factory_id=factory_id,
        role=role,
        full_name="Factory Owner",
        username="owner",
    )


def _invoice(db, factory, customer, number, invoice_type, invoice_date=date(2026, 6, 12)):
    invoice = InvoiceDocument(
        factory_id=factory.id,
        customer_id=customer.id,
        invoice_number=number,
        invoice_date=invoice_date,
        customer_name=customer.name,
        payment_method="Cash",
        bill_total=Decimal("1000.00"),
        amount_paid=Decimal("0.00"),
        customer_total_due=Decimal("1000.00"),
        payload_json={
            "invoice": {
                "invoice_id": number,
                "invoice_type": invoice_type,
                "invoice_date": invoice_date.isoformat(),
                "customer_name": customer.name,
                "bill_total": 1000,
                "sale_ids": [],
            },
            "items": [{"description": "Paper Cups", "quantity": 1, "rate": 1000}],
        },
    )
    db.add(invoice)
    db.flush()
    db.add(OutstandingBill(
        factory_id=factory.id,
        customer_id=customer.id,
        invoice_document_id=invoice.id,
        source_type="invoice",
        tracking_number=number,
        bill_date=invoice_date,
        bill_amount=Decimal("1000.00"),
        amount_paid=Decimal("0.00"),
        balance_amount=Decimal("1000.00"),
        status="active",
    ))
    db.commit()
    return invoice


def test_owner_can_delete_own_invoice_and_number_is_reused():
    db = _session()
    factory = Factory(name="Delete Factory", invoice_prefix="INV-", next_bill_of_supply_number=2)
    db.add(factory)
    db.flush()
    customer = Customer(factory_id=factory.id, name="Buyer", phone="9000000000")
    db.add(customer)
    db.flush()
    invoice = _invoice(db, factory, customer, "INV-1", "bill_of_supply")

    response = delete_invoice_document(
        invoice.id,
        InvoiceDeleteRequest(confirmation="DELETE INVOICE"),
        current_user=_owner(factory.id),
        db=db,
    )

    assert response["status"] == "deleted"
    assert db.query(InvoiceDocument).filter_by(id=invoice.id).first() is None
    assert db.query(ActivityLog).filter_by(entity_id=invoice.id, action_type="DELETE").count() == 1
    assert allocate_invoice_number(db, factory, "bill_of_supply") == "INV-1"


def test_supervisor_cannot_delete_invoice():
    db = _session()
    factory = Factory(name="Role Factory")
    db.add(factory)
    db.flush()
    customer = Customer(factory_id=factory.id, name="Buyer", phone="9000000000")
    db.add(customer)
    db.flush()
    invoice = _invoice(db, factory, customer, "INV-1", "bill_of_supply")

    with pytest.raises(HTTPException) as denied:
        delete_invoice_document(
            invoice.id,
            InvoiceDeleteRequest(confirmation="DELETE INVOICE"),
            current_user=_owner(factory.id, "Supervisor"),
            db=db,
        )
    assert denied.value.status_code == 403


def test_owner_cannot_delete_another_factory_invoice():
    db = _session()
    first = Factory(name="Factory A")
    second = Factory(name="Factory B")
    db.add_all([first, second])
    db.flush()
    customer = Customer(factory_id=first.id, name="Buyer", phone="9000000000")
    db.add(customer)
    db.flush()
    invoice = _invoice(db, first, customer, "A-1", "bill_of_supply")

    with pytest.raises(HTTPException) as missing:
        delete_invoice_document(
            invoice.id,
            InvoiceDeleteRequest(confirmation="DELETE INVOICE"),
            current_user=_owner(second.id),
            db=db,
        )
    assert missing.value.status_code == 404


def test_paid_invoice_delete_is_rejected_safely():
    db = _session()
    factory = Factory(name="Paid Factory")
    db.add(factory)
    db.flush()
    customer = Customer(factory_id=factory.id, name="Buyer", phone="9000000000")
    db.add(customer)
    db.flush()
    invoice = _invoice(db, factory, customer, "INV-1", "bill_of_supply")
    bill = db.query(OutstandingBill).filter_by(invoice_document_id=invoice.id).one()
    bill.amount_paid = Decimal("100.00")
    bill.balance_amount = Decimal("900.00")
    bill.status = "partial"
    db.commit()

    with pytest.raises(HTTPException) as unsafe:
        delete_invoice_document(
            invoice.id,
            InvoiceDeleteRequest(confirmation="DELETE INVOICE"),
            current_user=_owner(factory.id),
            db=db,
        )
    assert unsafe.value.status_code == 409


def test_monthly_bulk_download_separates_invoice_categories():
    db = _session()
    factory = Factory(name="ZIP Factory")
    db.add(factory)
    db.flush()
    customer = Customer(factory_id=factory.id, name="Buyer", phone="9000000000")
    db.add(customer)
    db.flush()
    _invoice(db, factory, customer, "TAX-1", "tax_invoice")
    _invoice(db, factory, customer, "BOS-1", "bill_of_supply")
    _invoice(db, factory, customer, "SIMPLE-1", "bill_of_supply_simple")

    response = bulk_download_invoices(
        month=6,
        year=2026,
        type="all",
        current_user=_owner(factory.id),
        db=db,
    )

    with ZipFile(BytesIO(response.body)) as archive:
        names = archive.namelist()
    assert any(name.startswith("2026-06/Tax-Invoice/") for name in names)
    assert any(name.startswith("2026-06/Bill-of-Supply/") for name in names)
    assert any(name.startswith("2026-06/Simple-Bill-of-Supply/") for name in names)
    assert all(name.endswith(".pdf") for name in names)


def test_monthly_bulk_download_empty_month_returns_404():
    db = _session()
    factory = Factory(name="Empty Factory")
    db.add(factory)
    db.commit()

    with pytest.raises(HTTPException) as empty:
        bulk_download_invoices(
            month=5,
            year=2026,
            type="all",
            current_user=_owner(factory.id),
            db=db,
        )
    assert empty.value.status_code == 404

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import Factory, InvoiceDeliveryLog, InvoiceDocument
from routers.sales import (
    allocate_invoice_number,
    invoice_delivery_history,
    reprint_invoice,
    validate_gst_invoice,
)


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_invoice_number_sequence_is_factory_scoped_and_unique():
    db = _session()
    first = Factory(name="Invoice Factory A", invoice_prefix="A-", next_tax_invoice_number=1)
    second = Factory(name="Invoice Factory B", invoice_prefix="B-", next_tax_invoice_number=1)
    db.add_all([first, second])
    db.flush()

    assert allocate_invoice_number(db, first, "tax_invoice") == "A-1"
    assert allocate_invoice_number(db, first, "tax_invoice") == "A-2"
    assert allocate_invoice_number(db, second, "tax_invoice") == "B-1"


def test_gst_validation_rejects_bad_gstin_and_unsupported_rate():
    with pytest.raises(HTTPException) as bad_gstin:
        validate_gst_invoice("tax_invoice", "INVALID", [18])
    assert bad_gstin.value.status_code == 422

    with pytest.raises(HTTPException) as bad_rate:
        validate_gst_invoice("tax_invoice", "07ABCDE1234F1Z5", [17])
    assert bad_rate.value.status_code == 422

    validate_gst_invoice("tax_invoice", "07ABCDE1234F1Z5", [18])
    validate_gst_invoice("bill_of_supply", None, [0])


def test_reprint_history_is_tenant_scoped():
    db = _session()
    first = Factory(name="History Factory A")
    second = Factory(name="History Factory B")
    db.add_all([first, second])
    db.flush()
    invoice = InvoiceDocument(
        factory_id=first.id,
        invoice_number="INV-1",
        invoice_date=date.today(),
        customer_name="Buyer",
        payment_method="Cash",
        bill_total=100,
        amount_paid=0,
        customer_total_due=100,
        payload_json={},
    )
    db.add(invoice)
    db.commit()
    owner = SimpleNamespace(id=None, factory_id=first.id)

    response = reprint_invoice(invoice.id, current_user=owner, db=db)
    rows = invoice_delivery_history(invoice.id, current_user=owner, db=db)

    assert response.channel == "REPRINT"
    assert len(rows) == 1
    assert db.query(InvoiceDeliveryLog).filter(InvoiceDeliveryLog.factory_id == first.id).count() == 1

    with pytest.raises(HTTPException) as denied:
        invoice_delivery_history(
            invoice.id,
            current_user=SimpleNamespace(id=None, factory_id=second.id),
            db=db,
        )
    assert denied.value.status_code == 404

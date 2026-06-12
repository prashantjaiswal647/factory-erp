from datetime import date
from decimal import Decimal
from io import BytesIO

from pypdf import PdfReader
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import Customer, Factory, InvoiceDocument, OutstandingBill, PaymentCollection, User
from routers.sales import _invoice_pdf_snapshot


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _pdf_text(pdf_bytes: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf_bytes)).pages)


def _seed_invoice(db, *, total: str, paid: str):
    factory = Factory(name="PDF Factory")
    db.add(factory)
    db.flush()
    receiver = User(
        factory_id=factory.id,
        username="rahul",
        full_name="Rahul",
        email="rahul@example.com",
        role="Supervisor",
        password_hash="hash",
        is_verified=True,
    )
    customer = Customer(factory_id=factory.id, name="PDF Buyer", phone="9000000000")
    db.add_all([receiver, customer])
    db.flush()
    total_amount = Decimal(total)
    paid_amount = Decimal(paid)
    invoice = InvoiceDocument(
        factory_id=factory.id,
        customer_id=customer.id,
        invoice_number="INV-PDF-1",
        invoice_date=date(2026, 6, 11),
        customer_name=customer.name,
        customer_phone=customer.phone,
        payment_method="Cash",
        bill_total=total_amount,
        amount_paid=Decimal("0"),
        customer_total_due=total_amount,
        payload_json={
            "factory_id": factory.id,
            "invoice": {
                "invoice_id": "INV-PDF-1",
                "invoice_date": "2026-06-11",
                "customer_name": customer.name,
                "bill_total": float(total_amount),
            },
            "items": [{"description": "Paper Cups", "quantity": 1, "rate": float(total_amount)}],
        },
    )
    db.add(invoice)
    db.flush()
    bill = OutstandingBill(
        factory_id=factory.id,
        customer_id=customer.id,
        invoice_document_id=invoice.id,
        source_type="invoice",
        tracking_number="INV-PDF-1",
        bill_date=invoice.invoice_date,
        bill_amount=total_amount,
        amount_paid=paid_amount,
        balance_amount=total_amount - paid_amount,
        status="settled" if paid_amount == total_amount else ("partial" if paid_amount else "active"),
    )
    db.add(bill)
    db.flush()
    return invoice, bill, receiver


def _add_collection(db, bill, receiver, amount: str, payment_date: date, reference: str):
    db.add(PaymentCollection(
        factory_id=bill.factory_id,
        customer_id=bill.customer_id,
        outstanding_bill_id=bill.id,
        amount_collected=Decimal(amount),
        payment_mode="UPI",
        collection_date=payment_date,
        reference_number=reference,
        created_by_user_id=receiver.id,
    ))
    db.flush()


def test_invoice_pdf_shows_no_payment_message():
    db = _session()
    invoice, _, _ = _seed_invoice(db, total="14926.40", paid="0")

    text = _pdf_text(_invoice_pdf_snapshot(db, invoice))

    assert "Payment History / Receipts" in text
    assert "No payment received against this invoice yet." in text
    assert "Unpaid" in text


def test_invoice_pdf_includes_partial_payment_history():
    db = _session()
    invoice, bill, receiver = _seed_invoice(db, total="14926.40", paid="1000")
    _add_collection(db, bill, receiver, "1000", date(2026, 6, 11), "UPI Ref 123")

    text = _pdf_text(_invoice_pdf_snapshot(db, invoice))

    assert "UPI Ref 123" in text
    assert "Supervisor Rahul" in text
    assert "13,926.40" in text
    assert "Partial Paid" in text


def test_invoice_pdf_includes_full_payment_and_remains_renderable():
    db = _session()
    invoice, bill, receiver = _seed_invoice(db, total="6000", paid="6000")
    _add_collection(db, bill, receiver, "1000", date(2026, 6, 11), "First receipt")
    _add_collection(db, bill, receiver, "5000", date(2026, 6, 12), "Final receipt")

    pdf_bytes = _invoice_pdf_snapshot(db, invoice)
    text = _pdf_text(pdf_bytes)

    assert pdf_bytes.startswith(b"%PDF")
    assert "First receipt" in text
    assert "Final receipt" in text
    assert "Paid" in text
    assert "Rs 0.00" in text


def test_invoice_pdf_split_payment_shows_only_invoice_allocation():
    db = _session()
    invoice, bill, receiver = _seed_invoice(db, total="8000", paid="3000")
    _add_collection(db, bill, receiver, "3000", date(2026, 6, 12), "Split payment")

    text = _pdf_text(_invoice_pdf_snapshot(db, invoice))

    assert "Rs 3,000.00" in text
    assert "Rs 5,000.00" in text
    assert "Rs 10,000.00" not in text

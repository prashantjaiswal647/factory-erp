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
    InvoiceHardDeleteRequest,
    allocate_invoice_number,
    bulk_download_invoices,
    delete_invoice_document,
    hard_delete_invoice_document,
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
    assert unsafe.value.detail == "Invoice has payment entries. Delete payment first or use cancel invoice."


def test_cancel_invoice_number_preserves_invoice_and_ledger():
    db = _session()
    factory = Factory(name="Cancel Factory", invoice_prefix="INV-")
    db.add(factory)
    db.flush()
    customer = Customer(factory_id=factory.id, name="Buyer", phone="9000000000")
    db.add(customer)
    db.flush()
    invoice = _invoice(db, factory, customer, "INV-1", "bill_of_supply")

    response = delete_invoice_document(
        invoice.id,
        InvoiceDeleteRequest(confirmation="DELETE INVOICE", action="cancel"),
        current_user=_owner(factory.id),
        db=db,
    )

    db.refresh(invoice)
    bill = db.query(OutstandingBill).filter_by(invoice_document_id=invoice.id).one()
    assert response["status"] == "cancelled"
    assert invoice.status == "cancelled"
    assert bill.status == "cancelled"
    assert bill.balance_amount == Decimal("0.00")


def test_hard_delete_invoice_reverses_stock_and_outstanding():
    from models import DailySale, FinalProductStock
    db = _session()
    factory = Factory(name="Stock Factory", invoice_prefix="INV-", next_bill_of_supply_number=2)
    db.add(factory)
    db.flush()
    customer = Customer(factory_id=factory.id, name="Buyer", phone="9000000000")
    db.add(customer)
    db.flush()

    # Create SKU stocks
    sku_stock = FinalProductStock(
        factory_id=str(factory.id),
        product_size_ml=250,
        variety="Plain White",
        packaging_size_name="50Pcs",
        total_boxes=100,
        loose_packets=0,
        packets_per_box_limit=1000,
        current_quantity=100,
    )
    db.add(sku_stock)
    db.flush()

    # 1. Create a sale row (selling 5 boxes)
    sale = DailySale(
        factory_id=factory.id,
        date=date(2026, 6, 12),
        customer_id=customer.id,
        customer_phone="9000000000",
        product_size_ml=250,
        variety="Plain White",
        packaging_size_name="50Pcs",
        boxes_sold=5,
        loose_packets_sold=0,
        rate_per_box=Decimal("200.00"),
        rate_per_packet=Decimal("0.20"),
        total_amount=Decimal("1000.00"),
        total_bill=Decimal("1000.00"),
        amount_paid=Decimal("0.00"),
    )
    db.add(sale)
    db.flush()

    # Verify stock is reduced
    from routers.inventory import recalculate_and_sync_sku_stock
    recalculate_and_sync_sku_stock(db, str(factory.id), 250, "Plain White", "50Pcs")
    assert sku_stock.current_quantity == 95

    # Create Invoice and Outstanding bill
    invoice = InvoiceDocument(
        factory_id=factory.id,
        customer_id=customer.id,
        invoice_number="INV-1",
        invoice_date=date(2026, 6, 12),
        customer_name=customer.name,
        payment_method="Cash",
        bill_total=Decimal("1000.00"),
        amount_paid=Decimal("0.00"),
        customer_total_due=Decimal("1000.00"),
        payload_json={
            "invoice": {
                "invoice_id": "INV-1",
                "invoice_type": "bill_of_supply",
                "invoice_date": "2026-06-12",
                "customer_name": customer.name,
                "bill_total": 1000,
                "sale_ids": [sale.id],
            },
            "items": [
                {
                    "product_size_ml": 250,
                    "variety": "Plain White",
                    "packaging_size_name": "50Pcs",
                    "boxes_sold": 5,
                    "loose_packets_sold": 0,
                    "rate_per_box": 200,
                }
            ],
        },
    )
    db.add(invoice)
    db.flush()

    bill = OutstandingBill(
        factory_id=factory.id,
        customer_id=customer.id,
        invoice_document_id=invoice.id,
        source_type="invoice",
        tracking_number="INV-1",
        bill_date=date(2026, 6, 12),
        bill_amount=Decimal("1000.00"),
        amount_paid=Decimal("0.00"),
        balance_amount=Decimal("1000.00"),
        status="active",
    )
    db.add(bill)
    db.flush()

    from services.accounting import sync_customer_balance_from_bills
    sync_customer_balance_from_bills(db, factory.id, customer)
    assert customer.balance_amount == Decimal("1000.00")

    # Cache IDs before deletion
    sale_id = sale.id
    invoice_id = invoice.id
    bill_id = bill.id

    # Now hard-delete the invoice
    response = delete_invoice_document(
        invoice.id,
        InvoiceDeleteRequest(confirmation="DELETE INVOICE"),
        current_user=_owner(factory.id),
        db=db,
    )
    assert response["status"] == "deleted"

    # Assert stock is restored back to 100
    assert sku_stock.current_quantity == 100

    # Assert customer balance is reduced back to 0
    assert customer.balance_amount == Decimal("0.00")

    # Assert daily sale, invoice document and outstanding bill are completely gone
    assert db.query(DailySale).filter_by(id=sale_id).first() is None
    assert db.query(InvoiceDocument).filter_by(id=invoice_id).first() is None
    assert db.query(OutstandingBill).filter_by(id=bill_id).first() is None



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


def test_paid_invoice_archive_and_reverse_behaviors():
    from models import DailySale, FinalProductStock, PaymentCollection, Payment
    db = _session()
    factory = Factory(name="Hard Factory", invoice_prefix="INV-", next_bill_of_supply_number=2)
    db.add(factory)
    db.flush()
    customer = Customer(factory_id=factory.id, name="Buyer", phone="9000000000")
    db.add(customer)
    db.flush()

    sku_stock = FinalProductStock(
        factory_id=str(factory.id),
        product_size_ml=250,
        variety="Plain White",
        packaging_size_name="50Pcs",
        total_boxes=100,
        loose_packets=0,
        packets_per_box_limit=1000,
        current_quantity=100,
    )
    db.add(sku_stock)
    db.flush()

    # Create sale
    sale = DailySale(
        factory_id=factory.id,
        date=date(2026, 6, 12),
        customer_id=customer.id,
        customer_phone="9000000000",
        product_size_ml=250,
        variety="Plain White",
        packaging_size_name="50Pcs",
        boxes_sold=5,
        loose_packets_sold=0,
        rate_per_box=Decimal("200.00"),
        rate_per_packet=Decimal("0.20"),
        total_amount=Decimal("1000.00"),
        total_bill=Decimal("1000.00"),
        amount_paid=Decimal("0.00"),
    )
    db.add(sale)
    db.flush()

    invoice = InvoiceDocument(
        factory_id=factory.id,
        customer_id=customer.id,
        invoice_number="INV-22",
        invoice_date=date(2026, 6, 12),
        customer_name=customer.name,
        payment_method="Cash",
        bill_total=Decimal("1000.00"),
        amount_paid=Decimal("1000.00"),
        customer_total_due=Decimal("0.00"),
        payload_json={
            "invoice": {
                "invoice_id": "INV-22",
                "invoice_type": "bill_of_supply",
                "invoice_date": "2026-06-12",
                "customer_name": customer.name,
                "bill_total": 1000,
                "sale_ids": [sale.id],
            },
            "items": [
                {
                    "product_size_ml": 250,
                    "variety": "Plain White",
                    "packaging_size_name": "50Pcs",
                    "boxes_sold": 5,
                    "loose_packets_sold": 0,
                    "rate_per_box": 200,
                }
            ],
        },
    )
    db.add(invoice)
    db.flush()

    bill = OutstandingBill(
        factory_id=factory.id,
        customer_id=customer.id,
        invoice_document_id=invoice.id,
        source_type="invoice",
        tracking_number="INV-22",
        bill_date=date(2026, 6, 12),
        bill_amount=Decimal("1000.00"),
        amount_paid=Decimal("1000.00"),
        balance_amount=Decimal("0.00"),
        status="closed",
    )
    db.add(bill)
    db.flush()

    # Link a payment collection/payment
    payment = Payment(
        factory_id=factory.id,
        customer_phone="9000000000",
        amount_paid=Decimal("1000.00"),
        payment_mode="Cash",
        date=date(2026, 6, 12),
    )
    db.add(payment)
    db.flush()

    collection = PaymentCollection(
        factory_id=factory.id,
        customer_id=customer.id,
        payment_id=payment.id,
        outstanding_bill_id=bill.id,
        amount_collected=Decimal("1000.00"),
        payment_mode="Cash",
        collection_date=date(2026, 6, 12),
    )
    db.add(collection)
    db.flush()

    from routers.inventory import recalculate_and_sync_sku_stock
    recalculate_and_sync_sku_stock(db, str(factory.id), 250, "Plain White", "50Pcs")
    assert sku_stock.current_quantity == 95

    # 1. Paid invoice cannot be hard deleted (reverse flow fails with 409)
    with pytest.raises(HTTPException) as err:
        delete_invoice_document(
            invoice.id,
            InvoiceDeleteRequest(confirmation="DELETE INVOICE", action="reverse"),
            current_user=_owner(factory.id),
            db=db,
        )
    assert err.value.status_code == 409
    assert err.value.detail == "Invoice has payment entries. Delete payment first or use cancel invoice."

    # 2. Paid invoice can be archived
    response = delete_invoice_document(
        invoice.id,
        InvoiceDeleteRequest(confirmation="DELETE INVOICE", action="archive"),
        current_user=_owner(factory.id),
        db=db,
    )
    assert response["status"] == "archived"
    assert invoice.status == "archived"
    assert bill.status == "archived"

    # 3. Archive keeps payment history (payment & collection & bill exist)
    assert db.query(Payment).filter_by(id=payment.id).first() is not None
    assert db.query(PaymentCollection).filter_by(id=collection.id).first() is not None
    assert db.query(OutstandingBill).filter_by(id=bill.id).first() is not None

    # 4. Archive has no stock change (stock is still 95, not restored to 100)
    recalculate_and_sync_sku_stock(db, str(factory.id), 250, "Plain White", "50Pcs")
    assert sku_stock.current_quantity == 95


def test_invoice_hard_delete_flows():
    db = _session()
    
    # 0. Setup Factory, Customer, and FinishedGoodsStock
    factory = Factory(name="Hard Delete Factory", invoice_prefix="INV-", next_bill_of_supply_number=3)
    db.add(factory)
    db.flush()
    
    customer = Customer(factory_id=factory.id, name="Hard Delete Buyer", phone="9999999999")
    db.add(customer)
    db.flush()

    from models import FinalProductStock
    sku_stock = FinalProductStock(
        factory_id=str(factory.id),
        product_size_ml=250,
        variety="Plain White",
        packaging_size_name="50Pcs",
        total_boxes=100,
        loose_packets=0,
        packets_per_box_limit=1000,
        current_quantity=100,
    )
    db.add(sku_stock)
    db.flush()

    # 1. Latest unpaid invoice hard delete reuses number
    invoice1 = _invoice(db, factory, customer, "INV-1", "bill_of_supply")
    invoice2 = _invoice(db, factory, customer, "INV-2", "bill_of_supply")

    # Manually simulate sequence progress
    from routers.sales import get_or_create_factory_settings
    settings = get_or_create_factory_settings(db, factory.id)
    settings.bill_of_supply_start_seq = 3
    factory.next_bill_of_supply_number = 3
    db.commit()

    assert settings.bill_of_supply_start_seq == 3

    # hard delete latest invoice (INV-2)
    response = hard_delete_invoice_document(
        invoice2.id,
        InvoiceHardDeleteRequest(
            reason="Test deletion of latest invoice",
            confirm_invoice_number="INV-2",
            confirm_test_invoice=True,
            reverse_payments=True
        ),
        current_user=_owner(factory.id),
        db=db,
    )
    assert response["status"] == "deleted"
    
    # verify sequence is reset to 2
    settings = get_or_create_factory_settings(db, factory.id)
    assert settings.bill_of_supply_start_seq == 2

    # 2. Latest paid test invoice hard delete removes allocations after confirmation
    # Re-create INV-2
    invoice2_new = _invoice(db, factory, customer, "INV-2", "bill_of_supply")
    
    # Add payment and allocation
    from models import Payment, PaymentCollection, BillPayment
    bill2 = db.query(OutstandingBill).filter_by(invoice_document_id=invoice2_new.id).first()
    payment = Payment(
        factory_id=factory.id,
        customer_phone=customer.phone,
        amount_paid=Decimal("500.00"),
        payment_mode="Cash",
        date=date(2026, 6, 12),
    )
    db.add(payment)
    db.flush()

    collection = PaymentCollection(
        factory_id=factory.id,
        customer_id=customer.id,
        payment_id=payment.id,
        outstanding_bill_id=bill2.id,
        amount_collected=Decimal("500.00"),
        payment_mode="Cash",
        collection_date=date(2026, 6, 12),
    )
    db.add(collection)
    db.flush()

    # Delete with reverse_payments=True
    response = hard_delete_invoice_document(
        invoice2_new.id,
        InvoiceHardDeleteRequest(
            reason="Test delete paid invoice",
            confirm_invoice_number="INV-2",
            confirm_test_invoice=True,
            reverse_payments=True
        ),
        current_user=_owner(factory.id),
        db=db,
    )
    assert response["status"] == "deleted"
    # Allocations are deleted
    assert db.query(PaymentCollection).filter_by(outstanding_bill_id=bill2.id).first() is None
    assert db.query(OutstandingBill).filter_by(id=bill2.id).first() is None

    # 3. Non-latest invoice hard delete blocked
    invoice2_three = _invoice(db, factory, customer, "INV-2", "bill_of_supply")
    invoice3 = _invoice(db, factory, customer, "INV-3", "bill_of_supply")

    with pytest.raises(HTTPException) as err:
        hard_delete_invoice_document(
            invoice2_three.id,
            InvoiceHardDeleteRequest(
                reason="Attempt deleting middle invoice",
                confirm_invoice_number="INV-2",
                confirm_test_invoice=True,
                reverse_payments=True
            ),
            current_user=_owner(factory.id),
            db=db,
        )
    assert err.value.status_code == 400
    assert "Later invoices exist. Use Cancel Invoice Number instead." in err.value.detail

    # 4. Archived/locked invoice cannot hard delete
    invoice3.accounting_locked = True
    db.commit()

    with pytest.raises(HTTPException) as err:
        hard_delete_invoice_document(
            invoice3.id,
            InvoiceHardDeleteRequest(
                reason="Attempt deleting locked invoice",
                confirm_invoice_number="INV-3",
                confirm_test_invoice=True,
                reverse_payments=True
            ),
            current_user=_owner(factory.id),
            db=db,
        )
    assert err.value.status_code == 409
    assert "locked for accounting" in err.value.detail

    # Revert lock for further tests
    invoice3.accounting_locked = False
    db.commit()

    # 5. Stock restored on hard delete
    # Let's set some payload_json showing it had line items
    invoice3.payload_json = {
        "invoice": {"sale_ids": [], "legal_invoice_type": "bill_of_supply"},
        "items": [
            {"product_size_ml": 250, "variety": "Plain White", "packaging_size_name": "50Pcs", "boxes_sold": 5}
        ]
    }
    db.commit()
    # decrease stock artificially to simulate creation impact
    sku_stock.current_quantity = 95
    db.commit()

    response = hard_delete_invoice_document(
        invoice3.id,
        InvoiceHardDeleteRequest(
            reason="Test stock restoration",
            confirm_invoice_number="INV-3",
            confirm_test_invoice=True,
            reverse_payments=True
        ),
        current_user=_owner(factory.id),
        db=db,
    )
    assert response["status"] == "deleted"
    # verify stock is restored to 100
    assert sku_stock.current_quantity == 100

    # 6. Outstanding removed on hard delete
    bill3 = db.query(OutstandingBill).filter_by(invoice_document_id=invoice3.id).first()
    assert bill3 is None

    # 7. Delete requires reason + invoice number typed
    # Delete the invoice2_three first which is currently the latest (INV-2) in DB
    hard_delete_invoice_document(
        invoice2_three.id,
        InvoiceHardDeleteRequest(
            reason="Cleanup prior test invoice",
            confirm_invoice_number="INV-2",
            confirm_test_invoice=True,
            reverse_payments=True
        ),
        current_user=_owner(factory.id),
        db=db,
    )

    invoice2_four = _invoice(db, factory, customer, "INV-2", "bill_of_supply")
    
    with pytest.raises(HTTPException) as err:
        hard_delete_invoice_document(
            invoice2_four.id,
            InvoiceHardDeleteRequest(
                reason="",
                confirm_invoice_number="INV-2",
                confirm_test_invoice=True,
                reverse_payments=True
            ),
            current_user=_owner(factory.id),
            db=db,
        )
    assert err.value.status_code == 422

    with pytest.raises(HTTPException) as err:
        hard_delete_invoice_document(
            invoice2_four.id,
            InvoiceHardDeleteRequest(
                reason="Correct reason",
                confirm_invoice_number="WRONG-NO",
                confirm_test_invoice=True,
                reverse_payments=True
            ),
            current_user=_owner(factory.id),
            db=db,
        )
    assert err.value.status_code == 422

    with pytest.raises(HTTPException) as err:
        hard_delete_invoice_document(
            invoice2_four.id,
            InvoiceHardDeleteRequest(
                reason="Correct reason",
                confirm_invoice_number="INV-2",
                confirm_test_invoice=True,
                reverse_payments=True
            ),
            current_user=_owner(factory.id, role="Supervisor"),
            db=db,
        )
    assert err.value.status_code == 403


def test_cancel_invoice_with_payments_exclusive_and_shared():
    from models import Payment, PaymentCollection, CustomerLedgerAdjustment, BillPayment
    db = _session()
    factory = Factory(name="Cancel Paid Factory", invoice_prefix="INV-")
    db.add(factory)
    db.flush()
    customer = Customer(factory_id=factory.id, name="Buyer", phone="9000000000")
    db.add(customer)
    db.flush()
    
    # Create Invoice 1 and Invoice 2
    inv1 = _invoice(db, factory, customer, "INV-1", "bill_of_supply")
    inv2 = _invoice(db, factory, customer, "INV-2", "bill_of_supply")
    bill1 = db.query(OutstandingBill).filter_by(invoice_document_id=inv1.id).one()
    bill2 = db.query(OutstandingBill).filter_by(invoice_document_id=inv2.id).one()

    # Create exclusive payment for Invoice 1
    p_excl = Payment(
        factory_id=factory.id,
        customer_phone=customer.phone,
        amount_paid=Decimal("1000.00"),
        payment_mode="Cash",
        date=date(2026, 6, 12),
    )
    db.add(p_excl)
    db.flush()
    col_excl = PaymentCollection(
        factory_id=factory.id,
        customer_id=customer.id,
        payment_id=p_excl.id,
        outstanding_bill_id=bill1.id,
        amount_collected=Decimal("1000.00"),
        payment_mode="Cash",
        collection_date=date(2026, 6, 12),
    )
    db.add(col_excl)
    db.flush()

    # Create shared payment for Invoice 1 and Invoice 2
    p_shared = Payment(
        factory_id=factory.id,
        customer_phone=customer.phone,
        amount_paid=Decimal("1500.00"),
        payment_mode="Cash",
        date=date(2026, 6, 12),
    )
    db.add(p_shared)
    db.flush()
    col_shared1 = PaymentCollection(
        factory_id=factory.id,
        customer_id=customer.id,
        payment_id=p_shared.id,
        outstanding_bill_id=bill1.id,
        amount_collected=Decimal("500.00"),
        payment_mode="Cash",
        collection_date=date(2026, 6, 12),
    )
    col_shared2 = PaymentCollection(
        factory_id=factory.id,
        customer_id=customer.id,
        payment_id=p_shared.id,
        outstanding_bill_id=bill2.id,
        amount_collected=Decimal("1000.00"),
        payment_mode="Cash",
        collection_date=date(2026, 6, 12),
    )
    db.add_all([col_shared1, col_shared2])
    db.flush()
    
    # Add a ledger adjustment linked to bill1
    adj = CustomerLedgerAdjustment(
        factory_id=factory.id,
        customer_id=customer.id,
        adjustment_type="add_balance",
        amount=Decimal("50.00"),
        reason="Adjustment for bill1",
        linked_bill_id=bill1.id,
    )
    db.add(adj)
    db.commit()

    # Cache IDs before deletion
    p_excl_id = p_excl.id
    col_excl_id = col_excl.id
    col_shared1_id = col_shared1.id
    col_shared2_id = col_shared2.id
    adj_id = adj.id

    # Cancel Invoice 1
    response = delete_invoice_document(
        inv1.id,
        InvoiceDeleteRequest(confirmation="DELETE INVOICE", action="cancel"),
        current_user=_owner(factory.id),
        db=db,
    )
    
    db.refresh(inv1)
    db.refresh(bill1)
    assert response["status"] == "cancelled"
    assert inv1.status == "cancelled"
    assert bill1.status == "cancelled"
    assert bill1.balance_amount == Decimal("0.00")

    # Assert exclusive payment was deleted
    assert db.query(Payment).filter_by(id=p_excl_id).first() is None
    assert db.query(PaymentCollection).filter_by(id=col_excl_id).first() is None

    # Assert shared payment was NOT deleted but adjusted down to 1000 (1500 - 500)
    db.refresh(p_shared)
    assert p_shared.amount_paid == Decimal("1000.00")
    assert db.query(PaymentCollection).filter_by(id=col_shared1_id).first() is None
    assert db.query(PaymentCollection).filter_by(id=col_shared2_id).first() is not None

    # Assert ledger adjustment was deleted
    assert db.query(CustomerLedgerAdjustment).filter_by(id=adj_id).first() is None


def test_hard_delete_not_latest_sequence_error_message():
    db = _session()
    factory = Factory(name="Seq Factory", invoice_prefix="INV-", next_bill_of_supply_number=3)
    db.add(factory)
    db.flush()
    customer = Customer(factory_id=factory.id, name="Buyer", phone="9000000000")
    db.add(customer)
    db.flush()

    inv1 = _invoice(db, factory, customer, "INV-1", "bill_of_supply")
    inv2 = _invoice(db, factory, customer, "INV-2", "bill_of_supply")

    # Attempt to hard delete middle invoice (inv1)
    with pytest.raises(HTTPException) as err:
        hard_delete_invoice_document(
            inv1.id,
            InvoiceHardDeleteRequest(
                reason="Attempt deleting middle invoice",
                confirm_invoice_number="INV-1",
                confirm_test_invoice=True,
                reverse_payments=True
            ),
            current_user=_owner(factory.id),
            db=db,
        )
    assert err.value.status_code == 400
    assert err.value.detail == "Later invoices exist. Use Cancel Invoice Number instead."

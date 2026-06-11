from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import Factory, Customer, OutstandingBill, Payment, PaymentCollection, DailySale, User, Order, PackagingProfile
from routers.sales import create_sales_customer, update_sales_customer, create_invoice_from_sale
from routers.payments import record_payment, build_outstanding_response
from routers.onboarding import apply_bulk_rows, CustomerBulkRow
from schemas import CustomerCreate
from services.accounting import active_customer_outstanding, create_outstanding_bill

def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()

def test_customer_creation_balances():
    db = _session()
    f1 = Factory(name="Test Factory 1")
    db.add(f1)
    db.flush()

    user = SimpleNamespace(id=1, username="owner", role="Owner", factory_id=f1.id, full_name="Owner F1")

    # 1. Customer create with previous_due
    payload = CustomerCreate(
        name="Cust A", phone_number="123", place="Delhi", previous_due=Decimal("1000.00")
    )
    c1 = create_sales_customer(payload=payload, current_user=user, db=db)
    assert c1.previous_due == Decimal("1000.00")
    assert c1.advance_balance == Decimal("0.00")

    # Check outstanding bill is created
    bill = db.query(OutstandingBill).filter(OutstandingBill.customer_id == c1.id).first()
    assert bill is not None
    assert bill.bill_amount == Decimal("1000.00")
    assert bill.source_type == "opening_balance"

    # 2. Customer create with advance_balance
    payload = CustomerCreate(
        name="Cust B", phone_number="456", place="Noida", advance_balance=Decimal("500.00")
    )
    c2 = create_sales_customer(payload=payload, current_user=user, db=db)
    assert c2.previous_due == Decimal("0.00")
    assert c2.advance_balance == Decimal("500.00")

    # 3. Customer create without both defaults to 0
    payload = CustomerCreate(
        name="Cust C", phone_number="789", place="Gurgaon"
    )
    c3 = create_sales_customer(payload=payload, current_user=user, db=db)
    assert c3.previous_due == Decimal("0.00")
    assert c3.advance_balance == Decimal("0.00")

    # 4. Negative previous_due rejected
    with pytest.raises(ValueError, match="Opening outstanding cannot be negative."):
        CustomerCreate(
            name="Cust D", phone_number="111", place="Delhi", previous_due=Decimal("-50.00")
        )

    # 5. Negative advance_balance rejected
    with pytest.raises(ValueError, match="Advance balance cannot be negative."):
        CustomerCreate(
            name="Cust E", phone_number="222", place="Delhi", advance_balance=Decimal("-50.00")
        )

    # Both positive rejected
    with pytest.raises(ValueError, match="A customer cannot have both opening outstanding and advance balance positive."):
        CustomerCreate(
            name="Cust F", phone_number="333", place="Delhi", previous_due=Decimal("100.00"), advance_balance=Decimal("100.00")
        )

def test_customer_create_accepts_blank_balance_dates():
    payload = CustomerCreate.model_validate(
        {
            "name": "Cust A",
            "phone_number": "123",
            "place": "Delhi",
            "opening_outstanding_date": "",
            "advance_balance_date": "   ",
        }
    )
    assert payload.opening_outstanding_date is None
    assert payload.advance_balance_date is None


def test_customer_update_accepts_blank_balance_dates():
    from routers.sales import CustomerUpdatePayload

    payload = CustomerUpdatePayload.model_validate(
        {
            "opening_outstanding_date": "",
            "advance_balance_date": "   ",
        }
    )
    assert payload.opening_outstanding_date is None
    assert payload.advance_balance_date is None


def test_customer_edit_updates_balances():
    db = _session()
    f1 = Factory(name="Test Factory 1")
    db.add(f1)
    db.flush()

    user = SimpleNamespace(id=1, username="owner", role="Owner", factory_id=f1.id, full_name="Owner F1")
    
    payload = CustomerCreate(name="Cust A", phone_number="123", place="Delhi")
    c1 = create_sales_customer(payload=payload, current_user=user, db=db)

    # 6. Customer edit updates previous_due
    from routers.sales import CustomerUpdatePayload
    update_payload = CustomerUpdatePayload(previous_due=Decimal("1500.00"))
    res = update_sales_customer(customer_id=c1.id, payload=update_payload, current_user=user, db=db)
    assert res.previous_due == Decimal("1500.00")
    assert res.advance_balance == Decimal("0.00")
    
    # 7. Customer edit updates advance_balance
    update_payload2 = CustomerUpdatePayload(previous_due=Decimal("0.00"), advance_balance=Decimal("800.00"))
    res2 = update_sales_customer(customer_id=c1.id, payload=update_payload2, current_user=user, db=db)
    assert res2.previous_due == Decimal("0.00")
    assert res2.advance_balance == Decimal("800.00")

def test_customer_edit_allows_unchanged_identity_and_profile_updates():
    db = _session()
    f1 = Factory(name="Test Factory 1")
    db.add(f1)
    db.flush()
    user = SimpleNamespace(id=1, username="owner", role="Owner", factory_id=f1.id, full_name="Owner F1")

    customer = create_sales_customer(
        payload=CustomerCreate(
            name="Cust A",
            phone_number="123",
            place="Delhi",
            gst_number="07ABCDE1234F1Z5",
            company_name="Alpha Cups",
        ),
        current_user=user,
        db=db,
    )

    from routers.sales import CustomerUpdatePayload
    unchanged = update_sales_customer(
        customer_id=customer.id,
        payload=CustomerUpdatePayload(
            name="Cust A",
            phone_number="123",
            gst_number="07ABCDE1234F1Z5",
            company_name="Alpha Cups",
        ),
        current_user=user,
        db=db,
    )
    assert unchanged.phone_number == "123"

    profile_update = update_sales_customer(
        customer_id=customer.id,
        payload=CustomerUpdatePayload(place="Noida", company_name="Alpha Packaging"),
        current_user=user,
        db=db,
    )
    assert profile_update.place == "Noida"
    assert profile_update.company_name == "Alpha Packaging"

    balance_update = update_sales_customer(
        customer_id=customer.id,
        payload=CustomerUpdatePayload(opening_outstanding=Decimal("250.00")),
        current_user=user,
        db=db,
    )
    assert balance_update.opening_outstanding == Decimal("250.00")


def test_customer_edit_duplicate_checks_are_factory_scoped_and_exclude_self():
    db = _session()
    f1 = Factory(name="Factory 1")
    f2 = Factory(name="Factory 2")
    db.add_all([f1, f2])
    db.flush()
    user1 = SimpleNamespace(id=1, username="owner1", role="Owner", factory_id=f1.id, full_name="Owner F1")
    user2 = SimpleNamespace(id=2, username="owner2", role="Owner", factory_id=f2.id, full_name="Owner F2")

    customer = create_sales_customer(
        payload=CustomerCreate(
            name="Cust A",
            phone_number="123",
            place="Delhi",
            gst_number="07AAAAA1111A1Z1",
            company_name="Alpha Cups",
        ),
        current_user=user1,
        db=db,
    )
    create_sales_customer(
        payload=CustomerCreate(
            name="Cust B",
            phone_number="456",
            place="Noida",
            gst_number="07BBBBB2222B2Z2",
            company_name="Beta Cups",
        ),
        current_user=user1,
        db=db,
    )
    other_factory_customer = create_sales_customer(
        payload=CustomerCreate(name="Cust C", phone_number="789", place="Pune"),
        current_user=user2,
        db=db,
    )

    from routers.sales import CustomerUpdatePayload
    with pytest.raises(HTTPException) as excinfo:
        update_sales_customer(
            customer_id=customer.id,
            payload=CustomerUpdatePayload(phone_number="456"),
            current_user=user1,
            db=db,
        )
    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == "Phone number already in use by another customer"

    duplicate_cases = [
        (CustomerUpdatePayload(name="Cust B"), "Customer name already in use by another customer"),
        (CustomerUpdatePayload(gst_number="07BBBBB2222B2Z2"), "GST number already in use by another customer"),
        (CustomerUpdatePayload(company_name="Beta Cups"), "Company name already in use by another customer"),
    ]
    for update_payload, expected_detail in duplicate_cases:
        with pytest.raises(HTTPException) as duplicate_exc:
            update_sales_customer(
                customer_id=customer.id,
                payload=update_payload,
                current_user=user1,
                db=db,
            )
        assert duplicate_exc.value.status_code == 409
        assert duplicate_exc.value.detail == expected_detail

    cross_factory_update = update_sales_customer(
        customer_id=other_factory_customer.id,
        payload=CustomerUpdatePayload(phone_number="123"),
        current_user=user2,
        db=db,
    )
    assert cross_factory_update.phone_number == "123"

def test_invoice_and_advance_deductions():
    db = _session()
    f1 = Factory(name="Test Factory 1", invoice_prefix="T-", next_tax_invoice_number=1)
    db.add(f1)
    db.flush()

    user = SimpleNamespace(id=1, username="owner", role="Owner", factory_id=f1.id, full_name="Owner F1")
    db_user = User(id=1, username="owner", role="Owner", factory_id=f1.id, full_name="Owner F1", password_hash="test-hash")
    db.add(db_user)
    db.flush()


    # Create customer with opening due = 2000, and advance = 3000
    # Wait, can't create with both positive, so create with advance 3000 first, then let's create customer and edit
    payload = CustomerCreate(name="Cust A", phone_number="123", place="Delhi", advance_balance=Decimal("3000.00"))
    customer = create_sales_customer(payload=payload, current_user=user, db=db)
    
    # Manually simulate outstanding bill for previous due = 2000
    # (since API doesn't let us create both positive simultaneously, we can manually add previous due to the ledger)
    create_outstanding_bill(
        db,
        factory_id=f1.id,
        customer_id=customer.id,
        source_type="opening_balance",
        tracking_number=f"OPEN-{customer.id}",
        bill_date=date.today(),
        bill_amount=Decimal("2000.00"),
        amount_paid=Decimal("0.00"),
    )
    
    # Verify ledger outstanding before bill: should be 2000
    assert active_customer_outstanding(db, f1.id, customer.id) == Decimal("2000.00")

    # Create a Sale for current bill = 10,000
    sale = DailySale(
        factory_id=f1.id,
        customer_id=customer.id,
        product_size_ml=250,
        variety="Standard",
        packaging_size_name="50Pcs/20Pkt",
        boxes_sold=1,
        total_amount=Decimal("10000.00"),
        amount_paid=Decimal("0.00"),
        date=date.today(),
    )
    db.add(sale)
    db.flush()

    # 8. & 9. Invoice total calculation and advance deduction
    # Total before advance = current bill (10000) + previous due (2000) = 12000.
    # Advance adjusted = min(3000, 12000) = 3000.
    # Remaining payable = 12000 - 3000 = 9000.
    from routers.sales import InvoiceFromSaleRequest
    req = InvoiceFromSaleRequest(invoice_type="tax_invoice", tax_rate=0.0)
    res = create_invoice_from_sale(sale_id=sale.id, payload=req, current_user=db_user, db=db)
    
    db.refresh(customer)
    # 10. Remaining advance should be 0
    assert customer.advance_balance == Decimal("0.00")
    
    # Total outstanding remaining in ledger should be 9000
    assert active_customer_outstanding(db, f1.id, customer.id) == Decimal("9000.00")

def test_advance_greater_than_invoice():
    db = _session()
    f1 = Factory(name="Test Factory 1", invoice_prefix="T-", next_tax_invoice_number=1)
    db.add(f1)
    db.flush()

    user = SimpleNamespace(id=1, username="owner", role="Owner", factory_id=f1.id, full_name="Owner F1")
    db_user = User(id=1, username="owner", role="Owner", factory_id=f1.id, full_name="Owner F1", password_hash="test-hash")
    db.add(db_user)
    db.flush()


    payload = CustomerCreate(name="Cust A", phone_number="123", place="Delhi", advance_balance=Decimal("15000.00"))
    customer = create_sales_customer(payload=payload, current_user=user, db=db)

    sale = DailySale(
        factory_id=f1.id,
        customer_id=customer.id,
        product_size_ml=250,
        variety="Standard",
        packaging_size_name="50Pcs/20Pkt",
        boxes_sold=1,
        total_amount=Decimal("10000.00"),
        amount_paid=Decimal("0.00"),
        date=date.today(),
    )
    db.add(sale)
    db.flush()

    from routers.sales import InvoiceFromSaleRequest
    req = InvoiceFromSaleRequest(invoice_type="tax_invoice", tax_rate=0.0)
    create_invoice_from_sale(sale_id=sale.id, payload=req, current_user=db_user, db=db)

    db.refresh(customer)
    # Remaining advance should be 15000 - 10000 = 5000
    assert customer.advance_balance == Decimal("5000.00")
    assert active_customer_outstanding(db, f1.id, customer.id) == Decimal("0.00")

def test_payment_and_overpayment():
    db = _session()
    f1 = Factory(name="Test Factory 1")
    db.add(f1)
    db.flush()

    user = SimpleNamespace(id=1, username="owner", role="Owner", factory_id=f1.id, full_name="Owner F1")
    db_user = User(id=1, username="owner", role="Owner", factory_id=f1.id, full_name="Owner F1", password_hash="test-hash")
    db.add(db_user)
    db.flush()

    payload = CustomerCreate(name="Cust A", phone_number="123", place="Delhi", previous_due=Decimal("1000.00"))
    customer = create_sales_customer(payload=payload, current_user=user, db=db)

    # 13. Payment reduces outstanding
    from routers.payments import PaymentCreate
    pay_req = PaymentCreate(customer_id=customer.id, amount_paid=600.00, payment_mode="UPI", save_extra_as_advance=True)
    record_payment(payload=pay_req, background_tasks=BackgroundTasksMock(), current_user=db_user, db=db)

    db.refresh(customer)
    assert active_customer_outstanding(db, f1.id, customer.id) == Decimal("400.00")
    assert customer.advance_balance == Decimal("0.00")

    # 14. Overpayment saved as advance
    pay_req_over = PaymentCreate(customer_id=customer.id, amount_paid=900.00, payment_mode="UPI", save_extra_as_advance=True)
    record_payment(payload=pay_req_over, background_tasks=BackgroundTasksMock(), current_user=db_user, db=db)

    db.refresh(customer)
    assert active_customer_outstanding(db, f1.id, customer.id) == Decimal("0.00")
    assert customer.advance_balance == Decimal("500.00")

def test_onboarding_bulk_upload_no_columns():
    db = _session()
    # 15. Verify that onboarding parser works with/without missing columns
    rows = [
        {"row_type": "customer", "name": "Cust A", "phone_number": "123", "place": "Delhi", "previous_due": "500", "advance_balance": "200"}
    ]
    stats = {}
    user = SimpleNamespace(id=1, username="owner", role="Owner", factory_id=1, full_name="Owner F1")
    apply_bulk_rows(db, user, "customer", rows, stats)
    
    cust = db.query(Customer).filter(Customer.factory_id == 1).first()
    assert cust is not None
    assert cust.previous_due == Decimal("500")
    assert cust.advance_balance == Decimal("200")

def test_tenant_isolation():
    db = _session()
    f1 = Factory(id=1, name="Factory 1")
    f2 = Factory(id=2, name="Factory 2")
    db.add_all([f1, f2])
    db.flush()

    user1 = SimpleNamespace(id=1, username="owner1", role="Owner", factory_id=1, full_name="Owner F1")
    db = _session()
    f1 = Factory(name="Test Factory 1", invoice_prefix="T-", next_tax_invoice_number=1)
    db.add(f1)
    db.flush()

    user = SimpleNamespace(id=1, username="owner", role="Owner", factory_id=f1.id, full_name="Owner F1")
    db_user = User(id=1, username="owner", role="Owner", factory_id=f1.id, full_name="Owner F1", password_hash="test-hash")
    db.add(db_user)
    db.flush()


    # Create customer with opening due = 2000, and advance = 3000
    # Wait, can't create with both positive, so create with advance 3000 first, then let's create customer and edit
    payload = CustomerCreate(name="Cust A", phone_number="123", place="Delhi", advance_balance=Decimal("3000.00"))
    customer = create_sales_customer(payload=payload, current_user=user, db=db)
    
    # Manually simulate outstanding bill for previous due = 2000
    # (since API doesn't let us create both positive simultaneously, we can manually add previous due to the ledger)
    create_outstanding_bill(
        db,
        factory_id=f1.id,
        customer_id=customer.id,
        source_type="opening_balance",
        tracking_number=f"OPEN-{customer.id}",
        bill_date=date.today(),
        bill_amount=Decimal("2000.00"),
        amount_paid=Decimal("0.00"),
    )
    
    # Verify ledger outstanding before bill: should be 2000
    assert active_customer_outstanding(db, f1.id, customer.id) == Decimal("2000.00")

    # Create a Sale for current bill = 10,000
    sale = DailySale(
        factory_id=f1.id,
        customer_id=customer.id,
        product_size_ml=250,
        variety="Standard",
        packaging_size_name="50Pcs/20Pkt",
        boxes_sold=1,
        total_amount=Decimal("10000.00"),
        amount_paid=Decimal("0.00"),
        date=date.today(),
    )
    db.add(sale)
    db.flush()

    # 8. & 9. Invoice total calculation and advance deduction
    # Total before advance = current bill (10000) + previous due (2000) = 12000.
    # Advance adjusted = min(3000, 12000) = 3000.
    # Remaining payable = 12000 - 3000 = 9000.
    from routers.sales import InvoiceFromSaleRequest
    req = InvoiceFromSaleRequest(invoice_type="tax_invoice", tax_rate=0.0)
    res = create_invoice_from_sale(sale_id=sale.id, payload=req, current_user=db_user, db=db)
    
    db.refresh(customer)
    # 10. Remaining advance should be 0
    assert customer.advance_balance == Decimal("0.00")
    
    # Total outstanding remaining in ledger should be 9000
    assert active_customer_outstanding(db, f1.id, customer.id) == Decimal("9000.00")

def test_advance_greater_than_invoice():
    db = _session()
    f1 = Factory(name="Test Factory 1", invoice_prefix="T-", next_tax_invoice_number=1)
    db.add(f1)
    db.flush()

    user = SimpleNamespace(id=1, username="owner", role="Owner", factory_id=f1.id, full_name="Owner F1")
    db_user = User(id=1, username="owner", role="Owner", factory_id=f1.id, full_name="Owner F1", password_hash="test-hash")
    db.add(db_user)
    db.flush()


    payload = CustomerCreate(name="Cust A", phone_number="123", place="Delhi", advance_balance=Decimal("15000.00"))
    customer = create_sales_customer(payload=payload, current_user=user, db=db)

    sale = DailySale(
        factory_id=f1.id,
        customer_id=customer.id,
        product_size_ml=250,
        variety="Standard",
        packaging_size_name="50Pcs/20Pkt",
        boxes_sold=1,
        total_amount=Decimal("10000.00"),
        amount_paid=Decimal("0.00"),
        date=date.today(),
    )
    db.add(sale)
    db.flush()

    from routers.sales import InvoiceFromSaleRequest
    req = InvoiceFromSaleRequest(invoice_type="tax_invoice", tax_rate=0.0)
    create_invoice_from_sale(sale_id=sale.id, payload=req, current_user=db_user, db=db)

    db.refresh(customer)
    # Remaining advance should be 15000 - 10000 = 5000
    assert customer.advance_balance == Decimal("5000.00")
    assert active_customer_outstanding(db, f1.id, customer.id) == Decimal("0.00")

def test_payment_and_overpayment():
    db = _session()
    f1 = Factory(name="Test Factory 1")
    db.add(f1)
    db.flush()

    user = SimpleNamespace(id=1, username="owner", role="Owner", factory_id=f1.id, full_name="Owner F1")
    db_user = User(id=1, username="owner", role="Owner", factory_id=f1.id, full_name="Owner F1", password_hash="test-hash")
    db.add(db_user)
    db.flush()

    payload = CustomerCreate(name="Cust A", phone_number="123", place="Delhi", previous_due=Decimal("1000.00"))
    customer = create_sales_customer(payload=payload, current_user=user, db=db)

    # 13. Payment reduces outstanding
    from routers.payments import PaymentCreate
    pay_req = PaymentCreate(customer_id=customer.id, amount_paid=600.00, payment_mode="UPI", save_extra_as_advance=True)
    record_payment(payload=pay_req, background_tasks=BackgroundTasksMock(), current_user=db_user, db=db)

    db.refresh(customer)
    assert active_customer_outstanding(db, f1.id, customer.id) == Decimal("400.00")
    assert customer.advance_balance == Decimal("0.00")

    # 14. Overpayment saved as advance
    pay_req_over = PaymentCreate(customer_id=customer.id, amount_paid=900.00, payment_mode="UPI", save_extra_as_advance=True)
    record_payment(payload=pay_req_over, background_tasks=BackgroundTasksMock(), current_user=db_user, db=db)

    db.refresh(customer)
    assert active_customer_outstanding(db, f1.id, customer.id) == Decimal("0.00")
    assert customer.advance_balance == Decimal("500.00")

def test_onboarding_bulk_upload_no_columns():
    db = _session()
    # 15. Verify that onboarding parser works with/without missing columns
    rows = [
        {"row_type": "customer", "name": "Cust A", "phone_number": "123", "place": "Delhi", "previous_due": "500", "advance_balance": "200"}
    ]
    stats = {}
    user = SimpleNamespace(id=1, username="owner", role="Owner", factory_id=1, full_name="Owner F1")
    apply_bulk_rows(db, user, "customer", rows, stats)
    
    cust = db.query(Customer).filter(Customer.factory_id == 1).first()
    assert cust is not None
    assert cust.previous_due == Decimal("500")
    assert cust.advance_balance == Decimal("200")

def test_tenant_isolation():
    db = _session()
    f1 = Factory(id=1, name="Factory 1")
    f2 = Factory(id=2, name="Factory 2")
    db.add_all([f1, f2])
    db.flush()

    user1 = SimpleNamespace(id=1, username="owner1", role="Owner", factory_id=1, full_name="Owner F1")
    user2 = SimpleNamespace(id=2, username="owner2", role="Owner", factory_id=2, full_name="Owner F2")

    payload = CustomerCreate(name="Cust A", phone_number="123", place="Delhi", previous_due=Decimal("1000.00"))
    c1 = create_sales_customer(payload=payload, current_user=user1, db=db)

    # 16. Factory 2 cannot view/update Factory 1 customer
    with pytest.raises(HTTPException) as excinfo:
        from routers.sales import CustomerUpdatePayload
        update_sales_customer(customer_id=c1.id, payload=CustomerUpdatePayload(previous_due=Decimal("500")), current_user=user2, db=db)
    assert excinfo.value.status_code == 404


def test_get_sales_outstanding_endpoint():
    db = _session()
    f1 = Factory(id=1, name="Factory 1")
    db.add(f1)
    db.flush()

    user1 = SimpleNamespace(id=1, username="owner1", role="Owner", factory_id=1, full_name="Owner F1")

    # 1. No opening balance
    c1 = create_sales_customer(
        payload=CustomerCreate(name="Cust A", phone_number="111", place="Delhi"),
        current_user=user1,
        db=db,
    )
    # 2. Previous due (opening balance)
    c2 = create_sales_customer(
        payload=CustomerCreate(name="Cust B", phone_number="222", place="Delhi", previous_due=Decimal("1500.00")),
        current_user=user1,
        db=db,
    )
    # 3. Advance balance
    c3 = create_sales_customer(
        payload=CustomerCreate(name="Cust C", phone_number="333", place="Delhi", advance_balance=Decimal("500.00")),
        current_user=user1,
        db=db,
    )

    from routers.sales import get_sales_outstanding
    response = get_sales_outstanding(current_user=user1, db=db)
    assert response is not None

    cust_map = {c.customer_id: c for c in response.customers}
    assert c2.id in cust_map
    assert c3.id in cust_map
    assert c1.id not in cust_map

    assert cust_map[c2.id].opening_outstanding == Decimal("1500.00")
    assert cust_map[c2.id].advance_balance == Decimal("0.00")
    assert cust_map[c3.id].opening_outstanding == Decimal("0.00")
    assert cust_map[c3.id].advance_balance == Decimal("500.00")


class BackgroundTasksMock:
    def add_task(self, func, *args, **kwargs):
        pass

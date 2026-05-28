from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from models import Customer, OutstandingBill, PaymentCollection, BillPayment, User


MONEY_QUANT = Decimal("0.01")
ACTIVE_BILL_STATUSES = ("active", "partial")


def to_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def create_outstanding_bill(
    db: Session,
    *,
    factory_id: int | str,
    customer_id: int,
    bill_amount,
    amount_paid=0,
    tracking_number: str,
    bill_date: date,
    source_type: str = "invoice",
    order_id: int | None = None,
    invoice_document_id: int | None = None,
) -> OutstandingBill | None:
    bill_total = to_money(bill_amount)
    paid = min(to_money(amount_paid), bill_total)
    balance = max(to_money(bill_total - paid), Decimal("0.00"))
    if bill_total <= 0 and balance <= 0:
        return None

    bill = OutstandingBill(
        factory_id=int(factory_id),
        customer_id=customer_id,
        order_id=order_id,
        invoice_document_id=invoice_document_id,
        source_type=source_type,
        tracking_number=tracking_number,
        bill_date=bill_date,
        bill_amount=bill_total,
        amount_paid=paid,
        balance_amount=balance,
        status="closed" if balance <= 0 else "active",
    )
    db.add(bill)
    db.flush()
    return bill


def active_customer_outstanding(db: Session, factory_id: int | str, customer_id: int) -> Decimal:
    return to_money(
        db.query(sql_func.coalesce(sql_func.sum(OutstandingBill.balance_amount), 0))
        .filter(OutstandingBill.factory_id == int(factory_id))
        .filter(OutstandingBill.customer_id == customer_id)
        .filter(OutstandingBill.balance_amount > 0)
        .filter(OutstandingBill.status.in_(ACTIVE_BILL_STATUSES))
        .scalar()
    )


def sync_customer_balance_from_bills(db: Session, factory_id: int | str, customer: Customer) -> Decimal:
    balance = active_customer_outstanding(db, factory_id, customer.id)
    customer.total_due = balance
    customer.balance_amount = balance
    customer.pending_balance = balance
    customer.pending_dues = float(balance)
    return balance


def apply_payment_to_outstanding_bills(
    db: Session,
    *,
    factory_id: int | str,
    customer_id: int,
    amount,
    payment_mode: str,
    collection_date: date,
    payment_id: int | None = None,
    selected_order_id: int | None = None,
    created_by_user_id: int | None = None,
) -> Decimal:
    remaining = to_money(amount)
    query = (
        db.query(OutstandingBill)
        .filter(OutstandingBill.factory_id == int(factory_id))
        .filter(OutstandingBill.customer_id == customer_id)
        .filter(OutstandingBill.balance_amount > 0)
        .filter(OutstandingBill.status.in_(ACTIVE_BILL_STATUSES))
        .with_for_update()
    )
    if selected_order_id is not None:
        query = query.filter(OutstandingBill.order_id == selected_order_id)

    bills = query.order_by(OutstandingBill.bill_date.asc(), OutstandingBill.id.asc()).all()
    if selected_order_id is not None and not bills:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outstanding bill not found")
    if selected_order_id is not None and bills and remaining > to_money(bills[0].balance_amount):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment amount exceeds selected bill balance")

    # Wrap operations inside an isolated database transactional block
    if not db.in_transaction():
        db.begin()

    try:
        # Retrieve received by auditor staff context details
        staff_name = "System"
        staff_role = "System"
        if created_by_user_id is not None:
            user_rec = db.query(User).filter(User.id == created_by_user_id).first()
            if user_rec is not None:
                staff_name = user_rec.username
                staff_role = user_rec.role

        for bill in bills:
            if remaining <= 0:
                break
            
            remaining_amount = to_money(bill.balance_amount)
            if remaining >= remaining_amount:
                # Deduct the remaining amount to change bill status to "Paid", subtract portion from remaining
                bill.amount_paid = to_money(bill.amount_paid) + remaining_amount
                bill.balance_amount = Decimal("0.00")
                bill.status = "Paid"  # changed bill status to "Paid"
                
                # Add child log audit record
                db.add(
                    BillPayment(
                        factory_id=int(factory_id),
                        bill_id=bill.id,
                        amount_allocated=remaining_amount,
                        payment_date=collection_date,
                        received_by_name=staff_name,
                        received_by_role=staff_role,
                    )
                )

                # payment_collections compatibility record
                db.add(
                    PaymentCollection(
                        factory_id=int(factory_id),
                        customer_id=customer_id,
                        payment_id=payment_id,
                        outstanding_bill_id=bill.id,
                        amount_collected=remaining_amount,
                        payment_mode=payment_mode,
                        collection_date=collection_date,
                        created_by_user_id=created_by_user_id,
                    )
                )
                
                remaining = to_money(remaining - remaining_amount)
            else:
                # Deduct entire remaining amount from this bill's outstanding balance, and set remaining = 0 to break
                bill.amount_paid = to_money(bill.amount_paid) + remaining
                bill.balance_amount = max(to_money(bill.balance_amount) - remaining, Decimal("0.00"))
                bill.status = "partial"

                # Add child log audit record
                db.add(
                    BillPayment(
                        factory_id=int(factory_id),
                        bill_id=bill.id,
                        amount_allocated=remaining,
                        payment_date=collection_date,
                        received_by_name=staff_name,
                        received_by_role=staff_role,
                    )
                )

                # payment_collections compatibility record
                db.add(
                    PaymentCollection(
                        factory_id=int(factory_id),
                        customer_id=customer_id,
                        payment_id=payment_id,
                        outstanding_bill_id=bill.id,
                        amount_collected=remaining,
                        payment_mode=payment_mode,
                        collection_date=collection_date,
                        created_by_user_id=created_by_user_id,
                    )
                )
                
                remaining = Decimal("0.00")
                break
        db.flush()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Isolated payment transaction collection failed: {exc}"
        ) from exc

    return remaining

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
import logging
import os
from typing import List, Optional, Union
from urllib import request as urlrequest

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func as sql_func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from dependencies import PAYMENT_ROLES, check_permissions
from db import get_db
from models import Customer, DailySale, Order, OutstandingBill, Payment, PaymentCollection, User
from services.accounting import apply_payment_to_outstanding_bills, sync_customer_balance_from_bills
from services.activity_logger import log_activity
from services.telegram_action_alerts import notify_payment_received


router = APIRouter(tags=["payments"])
MONEY_QUANT = Decimal("0.01")
logger = logging.getLogger(__name__)


def to_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def customer_phone(customer: Customer) -> str:
    phone = customer.phone_number or customer.phone or customer.contact_number
    if not phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customer phone number missing")
    return phone.strip()


def webhook_url_for_event(event: str) -> str | None:
    event_key = event.upper()
    if event_key in {"NEW_SALE", "NEW_INVOICE"}:
        return os.getenv("N8N_SALE_WEBHOOK_URL") or os.getenv("N8N_WEBHOOK_URL") or os.getenv("WHATSAPP_N8N_WEBHOOK_URL")
    if event_key == "PAYMENT_COLLECTED":
        return os.getenv("N8N_PAYMENT_WEBHOOK_URL") or os.getenv("N8N_WEBHOOK_URL") or os.getenv("WHATSAPP_N8N_WEBHOOK_URL")
    if event_key == "OUTSTANDING_REMINDER":
        return os.getenv("N8N_REMINDER_WEBHOOK_URL") or os.getenv("N8N_WEBHOOK_URL") or os.getenv("WHATSAPP_N8N_WEBHOOK_URL")
    return os.getenv("N8N_WEBHOOK_URL") or os.getenv("WHATSAPP_N8N_WEBHOOK_URL")


def send_n8n_whatsapp_event(payload: dict) -> None:
    webhook_url = webhook_url_for_event(str(payload.get("event") or payload.get("type") or ""))
    if not webhook_url:
        return

    try:
        body = json.dumps(payload, default=str).encode("utf-8")
        req = urlrequest.Request(
            webhook_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=5) as response:
            response.read()
    except Exception as exc:
        logger.warning("N8N WhatsApp webhook dispatch failed", exc_info=True)


def calculate_customer_outstanding(db: Session, factory_id: int, customer: Customer) -> tuple[Decimal, Decimal, Decimal]:
    ledger_total = to_money(
        db.query(sql_func.coalesce(sql_func.sum(OutstandingBill.bill_amount), 0))
        .filter(OutstandingBill.factory_id == factory_id)
        .filter(OutstandingBill.customer_id == customer.id)
        .scalar()
    )
    if ledger_total > 0:
        ledger_paid = to_money(
            db.query(sql_func.coalesce(sql_func.sum(OutstandingBill.amount_paid), 0))
            .filter(OutstandingBill.factory_id == factory_id)
            .filter(OutstandingBill.customer_id == customer.id)
            .scalar()
        )
        ledger_balance = to_money(
            db.query(sql_func.coalesce(sql_func.sum(OutstandingBill.balance_amount), 0))
            .filter(OutstandingBill.factory_id == factory_id)
            .filter(OutstandingBill.customer_id == customer.id)
            .filter(OutstandingBill.balance_amount > 0)
            .filter(OutstandingBill.status.in_(["active", "partial"]))
            .scalar()
        )
        return ledger_total, ledger_paid, ledger_balance

    total_bill = to_money(
        db.query(sql_func.coalesce(sql_func.sum(Order.total_amount), 0))
        .filter(Order.factory_id == factory_id)
        .filter(Order.customer_id == customer.id)
        .filter(Order.status.notin_(["cancelled", "adjusted_closed", "Rejected"]))
        .scalar()
    )
    total_paid = to_money(
        db.query(sql_func.coalesce(sql_func.sum(Order.amount_paid), 0))
        .filter(Order.factory_id == factory_id)
        .filter(Order.customer_id == customer.id)
        .filter(Order.status.notin_(["cancelled", "adjusted_closed", "Rejected"]))
        .scalar()
    )
    balance = to_money(
        db.query(sql_func.coalesce(sql_func.sum(Order.balance_amount), 0))
        .filter(Order.factory_id == factory_id)
        .filter(Order.customer_id == customer.id)
        .filter(Order.balance_amount > 0)
        .filter(Order.status.notin_(["cancelled", "adjusted_closed", "Rejected"]))
        .scalar()
    )
    return total_bill, total_paid, balance


class PaymentCreate(BaseModel):
    customer_phone: Optional[str] = None
    customer_id: Optional[int] = None
    amount_paid: float = Field(..., gt=0)
    payment_mode: str = Field("Cash", pattern="^(Cash|UPI|Bank Transfer)$")
    date: Optional[Union[date, str]] = None
    order_id: Optional[int] = None
    sale_id: Optional[int] = None
    save_extra_as_advance: bool = True


class PaymentResponse(BaseModel):
    id: int
    customer_phone: str
    amount_paid: Decimal
    payment_mode: str
    date: date
    total_remaining_balance: Decimal


class OutstandingBillRow(BaseModel):
    order_id: Optional[int] = None
    order_date: str
    bill_amount: Decimal
    amount_paid: Decimal
    remaining_balance: Decimal
    status: str


class OutstandingRow(BaseModel):
    customer_id: int
    customer_name: str
    customer_phone: str
    place: str = ""
    total_bill_amount: Decimal
    total_paid: Decimal
    current_pending_balance: Decimal
    advance_balance: Decimal = Decimal("0.00")
    net_balance: Decimal = Decimal("0.00")
    last_reminded_at: Optional[datetime] = None
    bills: List[OutstandingBillRow] = Field(default_factory=list)


class OutstandingResponse(BaseModel):
    grand_total_outstanding: Decimal
    grand_total_advance: Decimal = Decimal("0.00")
    grand_total_net: Decimal = Decimal("0.00")
    customers: List[OutstandingRow]


def apply_payment_to_orders(db: Session, factory_id: int, customer: Customer, amount: Decimal, specific_order_id: Optional[int] = None) -> Decimal:
    ledger_total = to_money(
        db.query(sql_func.coalesce(sql_func.sum(OutstandingBill.balance_amount), 0))
        .filter(OutstandingBill.factory_id == factory_id)
        .filter(OutstandingBill.customer_id == customer.id)
        .filter(OutstandingBill.balance_amount > 0)
        .filter(OutstandingBill.status.in_(["active", "partial"]))
        .scalar()
    )
    if ledger_total > 0:
        return apply_payment_to_outstanding_bills(
            db,
            factory_id=factory_id,
            customer_id=customer.id,
            amount=amount,
            payment_mode="Cash",
            collection_date=date.today(),
            selected_order_id=specific_order_id,
        )

    remaining = to_money(amount)
    query = (
        db.query(Order)
        .filter(Order.factory_id == factory_id)
        .filter(Order.customer_id == customer.id)
        .filter(Order.balance_amount > 0)
        .filter(Order.status.notin_(["cancelled", "adjusted_closed", "Rejected"]))
        .with_for_update()
    )
    if specific_order_id is not None:
        query = query.filter(Order.id == specific_order_id)
    orders = query.order_by(Order.order_date.asc(), Order.id.asc()).all()
    if specific_order_id is not None and not orders:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outstanding bill not found")
    if specific_order_id is not None and orders and remaining > to_money(orders[0].balance_amount):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment amount exceeds selected bill balance")

    for order in orders:
        if remaining <= 0:
            break
        applied = min(remaining, to_money(order.balance_amount))
        order.amount_paid = to_money(order.amount_paid) + applied
        order.balance_amount = max(to_money(order.balance_amount) - applied, Decimal("0.00"))
        remaining = to_money(remaining - applied)

    return remaining


def build_outstanding_response(db: Session, factory_id: int) -> OutstandingResponse:
    rows: list[OutstandingRow] = []
    grand_total = Decimal("0.00")
    grand_advance = Decimal("0.00")

    customers = db.query(Customer).filter(Customer.factory_id == factory_id).order_by(Customer.name.asc()).all()
    for customer in customers:
        try:
            phone = customer_phone(customer)
        except HTTPException:
            continue

        total_bill, total_paid, balance = calculate_customer_outstanding(db, factory_id, customer)
        adv = to_money(customer.advance_balance)
        if balance <= 0 and adv <= 0:
            continue
            
        ledger_bills = (
            db.query(OutstandingBill)
            .filter(OutstandingBill.factory_id == factory_id)
            .filter(OutstandingBill.customer_id == customer.id)
            .filter(OutstandingBill.balance_amount > 0)
            .filter(OutstandingBill.status.in_(["active", "partial"]))
            .order_by(OutstandingBill.bill_date.asc(), OutstandingBill.id.asc())
            .all()
        )
        order_bills = []
        if not ledger_bills:
            order_bills = (
                db.query(Order)
                .filter(Order.factory_id == factory_id)
                .filter(Order.customer_id == customer.id)
                .filter(Order.balance_amount > 0)
                .filter(Order.status.notin_(["cancelled", "adjusted_closed", "Rejected"]))
                .order_by(Order.order_date.asc(), Order.id.asc())
                .all()
            )

        rows.append(
            OutstandingRow(
                customer_id=customer.id,
                customer_name=customer.name,
                customer_phone=phone,
                place=customer.place or customer.address or "",
                total_bill_amount=total_bill,
                total_paid=total_paid,
                current_pending_balance=balance,
                advance_balance=adv,
                net_balance=to_money(balance - adv),
                last_reminded_at=customer.last_whatsapp_reminder_at,
                bills=[
                    OutstandingBillRow(
                        order_id=bill.order_id,
                        order_date=bill.bill_date.isoformat() if bill.bill_date else "",
                        bill_amount=to_money(bill.bill_amount),
                        amount_paid=to_money(bill.amount_paid),
                        remaining_balance=to_money(bill.balance_amount),
                        status=bill.status,
                    )
                    for bill in ledger_bills
                ] or [
                    OutstandingBillRow(
                        order_id=bill.id,
                        order_date=bill.order_date.isoformat() if bill.order_date else "",
                        bill_amount=to_money(bill.total_amount),
                        amount_paid=to_money(bill.amount_paid),
                        remaining_balance=to_money(bill.balance_amount),
                        status=bill.status,
                    )
                    for bill in order_bills
                ],
            )
        )
        grand_total = to_money(grand_total + balance)
        grand_advance = to_money(grand_advance + adv)

    grand_net = to_money(grand_total - grand_advance)
    return OutstandingResponse(
        grand_total_outstanding=grand_total,
        grand_total_advance=grand_advance,
        grand_total_net=grand_net,
        customers=rows,
    )


@router.get("/api/accounts/outstanding", response_model=OutstandingResponse)
@router.get("/api/payments/dues", response_model=OutstandingResponse)
def get_outstanding_dues(
    current_user: User = Depends(check_permissions(PAYMENT_ROLES)),
    db: Session = Depends(get_db),
):
    return build_outstanding_response(db, current_user.factory_id)


@router.post("/api/accounts/payments", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
@router.post("/api/payments", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
@router.post("/api/payments/add", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
def record_payment(
    payload: PaymentCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(PAYMENT_ROLES)),
    db: Session = Depends(get_db),
):
    try:
        if not db.in_transaction():
            db.begin()
        factory_id = current_user.factory_id
        selected_order_id = payload.order_id or payload.sale_id
        if payload.customer_id is not None:
            customer = (
                db.query(Customer)
                .filter(Customer.factory_id == factory_id)
                .filter(Customer.id == payload.customer_id)
                .with_for_update()
                .first()
            )
        elif payload.customer_phone:
            phone = payload.customer_phone.strip()
            customer = (
                db.query(Customer)
                .filter(Customer.factory_id == factory_id)
                .filter(or_(Customer.phone_number == phone, Customer.phone == phone, Customer.contact_number == phone))
                .with_for_update()
                .first()
            )
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Either customer_id or customer_phone must be provided")
            
        if customer is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
        _, _, current_balance = calculate_customer_outstanding(db, factory_id, customer)
        amount_to_pay = to_money(payload.amount_paid)
        extra_advance = Decimal("0.00")

        if amount_to_pay > current_balance:
            if not payload.save_extra_as_advance:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Payment amount exceeds outstanding balance"
                )
            extra_advance = amount_to_pay - current_balance
            amount_to_pay = current_balance

        daily_sale_id = None
        if payload.sale_id is not None:
            daily_sale = (
                db.query(DailySale.id)
                .filter(DailySale.factory_id == factory_id)
                .filter(DailySale.id == payload.sale_id)
                .first()
            )
            if daily_sale is not None:
                daily_sale_id = payload.sale_id

        # Convert date to timezone-safe DB date object safely
        payment_date = date.today()
        if payload.date:
            if isinstance(payload.date, date):
                payment_date = payload.date
            else:
                try:
                    date_str = str(payload.date).split("T")[0]
                    try:
                        payment_date = date.fromisoformat(date_str)
                    except ValueError:
                        payment_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    payment_date = date.today()

        payment = Payment(
            factory_id=factory_id,
            customer_phone=customer_phone(customer),
            sale_id=daily_sale_id,
            amount_paid=to_money(payload.amount_paid),
            payment_mode=payload.payment_mode,
            date=payment_date,
        )
        db.add(payment)
        db.flush()

        unapplied = Decimal("0.00")
        if amount_to_pay > 0:
            unapplied = apply_payment_to_outstanding_bills(
                db,
                factory_id=factory_id,
                customer_id=customer.id,
                amount=amount_to_pay,
                payment_mode=payload.payment_mode,
                collection_date=payment_date,
                payment_id=payment.id,
                selected_order_id=selected_order_id,
                created_by_user_id=current_user.id,
            )
            if unapplied > 0:
                order_unapplied = apply_payment_to_orders(db, factory_id, customer, unapplied, selected_order_id)
                legacy_applied = to_money(unapplied - order_unapplied)
                if legacy_applied > 0:
                    db.add(
                        PaymentCollection(
                            factory_id=factory_id,
                            customer_id=customer.id,
                            payment_id=payment.id,
                            outstanding_bill_id=None,
                            amount_collected=legacy_applied,
                            payment_mode=payload.payment_mode,
                            collection_date=payload.date or date.today(),
                            created_by_user_id=current_user.id,
                        )
                    )

        if extra_advance > 0:
            customer.advance_balance = to_money(customer.advance_balance) + extra_advance
            db.add(
                PaymentCollection(
                    factory_id=factory_id,
                    customer_id=customer.id,
                    payment_id=payment.id,
                    outstanding_bill_id=None,
                    amount_collected=extra_advance,
                    payment_mode=payload.payment_mode,
                    collection_date=payment_date,
                    created_by_user_id=current_user.id,
                    reference_number="Save extra as advance",
                )
            )

        db.flush()

        balance = sync_customer_balance_from_bills(db, factory_id, customer)
        if balance <= 0:
            _, _, balance = calculate_customer_outstanding(db, factory_id, customer)
            customer.total_due = balance
            customer.balance_amount = balance
            customer.pending_balance = balance
            customer.pending_dues = float(balance)

        db.commit()
        db.refresh(payment)
        # P4.5 D1: action alert to Owner (best-effort, never raises)
        from models import Factory as _Factory
        _factory = db.query(_Factory).filter(_Factory.id == factory_id).first()
        if _factory is not None:
            notify_payment_received(
                db,
                factory=_factory,
                actor=current_user,
                customer_name=customer.name,
                amount_paise=int(to_money(payment.amount_paid) * 100),
            )
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Payment collection failed and was rolled back") from exc

    background_tasks.add_task(
        send_n8n_whatsapp_event,
        {
            "event": "PAYMENT_COLLECTED",
            "customer_name": customer.name,
            "phone": payment.customer_phone,
            "amount_paid": str(payment.amount_paid),
            "remaining_balance": str(balance),
            "collected_by": current_user.full_name or current_user.username,
        }
    )
    background_tasks.add_task(
        log_activity,
        db,
        int(current_user.factory_id),
        current_user.id,
        current_user.full_name or current_user.username,
        current_user.role,
        "PAYMENT_COLLECTED",
        f"\u20B9{payment.amount_paid:,.2f} collected from {customer.name}",
        "payment",
        payment.id,
        {"customer_id": customer.id, "payment_mode": payment.payment_mode, "remaining_balance": str(balance)},
    )

    return PaymentResponse(
        id=payment.id,
        customer_phone=payment.customer_phone,
        amount_paid=payment.amount_paid,
        payment_mode=payment.payment_mode,
        date=payment.date,
        total_remaining_balance=balance,
    )


class PendingReminderRow(BaseModel):
    customer_id: int
    customer_name: str
    phone: str
    place: str = ""
    net_balance: Decimal
    last_payment_date: Optional[date] = None
    last_reminded_at: Optional[datetime] = None


class ReminderResponse(BaseModel):
    message: str
    customer_id: int
    last_reminded_at: datetime


@router.get("/api/accounts/pending-reminders", response_model=List[PendingReminderRow])
def pending_reminders(
    current_user: User = Depends(check_permissions(PAYMENT_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = current_user.factory_id
    cutoff = date.today() - timedelta(days=7)
    rows: list[PendingReminderRow] = []

    customers = db.query(Customer).filter(Customer.factory_id == factory_id).order_by(Customer.name.asc()).all()
    for customer in customers:
        try:
            phone = customer_phone(customer)
        except HTTPException:
            continue

        _, _, balance = calculate_customer_outstanding(db, factory_id, customer)
        if balance <= 0:
            continue

        last_payment_date = (
            db.query(sql_func.max(Payment.date))
            .filter(Payment.factory_id == factory_id)
            .filter(Payment.customer_phone == phone)
            .scalar()
        )
        if last_payment_date is not None and last_payment_date > cutoff:
            continue

        rows.append(
            PendingReminderRow(
                customer_id=customer.id,
                customer_name=customer.name,
                phone=phone,
                place=customer.place or customer.address or "",
                net_balance=balance,
                last_payment_date=last_payment_date,
                last_reminded_at=customer.last_whatsapp_reminder_at,
            )
        )

    return rows


@router.post("/api/accounts/reminders/{customer_id}", response_model=ReminderResponse)
def send_outstanding_reminder(
    customer_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(PAYMENT_ROLES)),
    db: Session = Depends(get_db),
):
    customer = (
        db.query(Customer)
        .filter(Customer.factory_id == current_user.factory_id)
        .filter(Customer.id == customer_id)
        .with_for_update()
        .first()
    )
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    phone = customer_phone(customer)
    _, _, balance = calculate_customer_outstanding(db, current_user.factory_id, customer)
    if balance <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customer has no pending balance")

    reminded_at = datetime.now(timezone.utc)
    customer.last_whatsapp_reminder_at = reminded_at
    db.commit()

    background_tasks.add_task(
        send_n8n_whatsapp_event,
        {
            "event": "OUTSTANDING_REMINDER",
            "customer_name": customer.name,
            "phone": phone,
            "net_balance": str(balance),
            "last_reminded_at": reminded_at.isoformat(),
            "triggered_by": current_user.full_name or current_user.username,
        },
    )

    return ReminderResponse(
        message="Reminder webhook triggered",
        customer_id=customer.id,
        last_reminded_at=reminded_at,
    )

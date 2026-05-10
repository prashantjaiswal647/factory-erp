from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
import os
from typing import List, Optional
from urllib import request as urlrequest

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func as sql_func, or_
from sqlalchemy.orm import Session

from dependencies import PAYMENT_ROLES, check_permissions
from db import get_db
from models import Customer, DailySale, Payment, User


router = APIRouter(tags=["payments"])
MONEY_QUANT = Decimal("0.01")


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
        print(f"N8N WEBHOOK ERROR: {exc}")


def calculate_customer_outstanding(db: Session, factory_id: int, customer: Customer) -> tuple[Decimal, Decimal, Decimal]:
    phone = customer_phone(customer)
    total_bill = to_money(
        db.query(sql_func.coalesce(sql_func.sum(DailySale.total_bill), 0))
        .filter(DailySale.factory_id == factory_id)
        .filter(DailySale.customer_id == customer.id)
        .scalar()
    )
    total_paid = to_money(
        db.query(sql_func.coalesce(sql_func.sum(Payment.amount_paid), 0))
        .filter(Payment.factory_id == factory_id)
        .filter(Payment.customer_phone == phone)
        .scalar()
    )
    balance = to_money(total_bill - total_paid)
    if balance < 0:
        balance = Decimal("0.00")
    return total_bill, total_paid, balance


class PaymentCreate(BaseModel):
    customer_phone: str = Field(..., min_length=1)
    amount_paid: float = Field(..., gt=0)
    payment_mode: str = Field("Cash", pattern="^(Cash|UPI|Bank Transfer)$")
    date: Optional[date] = None
    sale_id: Optional[int] = None


class PaymentResponse(BaseModel):
    id: int
    customer_phone: str
    amount_paid: Decimal
    payment_mode: str
    date: date
    total_remaining_balance: Decimal


class OutstandingRow(BaseModel):
    customer_id: int
    customer_name: str
    customer_phone: str
    place: str = ""
    total_bill_amount: Decimal
    total_paid: Decimal
    current_pending_balance: Decimal
    last_reminded_at: Optional[datetime] = None


class OutstandingResponse(BaseModel):
    grand_total_outstanding: Decimal
    customers: List[OutstandingRow]


def build_outstanding_response(db: Session, factory_id: int) -> OutstandingResponse:
    rows: list[OutstandingRow] = []
    grand_total = Decimal("0.00")

    customers = db.query(Customer).filter(Customer.factory_id == factory_id).order_by(Customer.name.asc()).all()
    for customer in customers:
        try:
            phone = customer_phone(customer)
        except HTTPException:
            continue

        total_bill, total_paid, balance = calculate_customer_outstanding(db, factory_id, customer)
        if balance <= 0:
            continue

        rows.append(
            OutstandingRow(
                customer_id=customer.id,
                customer_name=customer.name,
                customer_phone=phone,
                place=customer.place or customer.address or "",
                total_bill_amount=total_bill,
                total_paid=total_paid,
                current_pending_balance=balance,
                last_reminded_at=customer.last_whatsapp_reminder_at,
            )
        )
        grand_total = to_money(grand_total + balance)

    return OutstandingResponse(grand_total_outstanding=grand_total, customers=rows)


@router.get("/api/accounts/outstanding", response_model=OutstandingResponse)
@router.get("/api/payments/dues", response_model=OutstandingResponse)
def get_outstanding_dues(
    current_user: User = Depends(check_permissions(PAYMENT_ROLES)),
    db: Session = Depends(get_db),
):
    return build_outstanding_response(db, current_user.factory_id)


@router.post("/api/accounts/payments", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
@router.post("/api/payments/add", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
def record_payment(
    payload: PaymentCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(PAYMENT_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = current_user.factory_id
    phone = payload.customer_phone.strip()
    customer = (
        db.query(Customer)
        .filter(Customer.factory_id == factory_id)
        .filter(or_(Customer.phone_number == phone, Customer.phone == phone, Customer.contact_number == phone))
        .with_for_update()
        .first()
    )
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    payment = Payment(
        factory_id=factory_id,
        customer_phone=customer_phone(customer),
        sale_id=payload.sale_id,
        amount_paid=to_money(payload.amount_paid),
        payment_mode=payload.payment_mode,
        date=payload.date or date.today(),
    )
    db.add(payment)
    db.flush()

    _, _, balance = calculate_customer_outstanding(db, factory_id, customer)
    customer.total_due = balance
    customer.balance_amount = balance
    customer.pending_balance = balance
    customer.pending_dues = float(balance)

    db.commit()
    db.refresh(payment)

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

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from auth import require_owner
from db import get_db
from models import Customer, Order, SalesInvoice, User
from routers.sales import pending_payment_dues


router = APIRouter(prefix="/api", tags=["automation"])


class PortalLinkResponse(BaseModel):
    customer_id: int
    portal_access_token: str
    storefront_url: str
    is_portal_approved: bool


class CustomerWeeklyReport(BaseModel):
    customer_id: int
    total_orders_this_week: int
    cash_paid: Decimal
    current_outstanding_balance: Decimal


class PaymentReminderTriggerResponse(BaseModel):
    message: str
    reminders_pushed: int
    webhook_url: str


def generate_customer_portal_token() -> str:
    return uuid4().hex + uuid4().hex


@router.post("/automation/customers/{customer_id}/portal-link", response_model=PortalLinkResponse)
def generate_customer_portal_link(
    customer_id: int,
    request: Request,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    customer = (
        db.query(Customer)
        .filter(Customer.factory_id == current_user.factory_id)
        .filter(Customer.id == customer_id)
        .first()
    )
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    if not customer.portal_access_token:
        customer.portal_access_token = generate_customer_portal_token()
    customer.store_token = customer.portal_access_token
    customer.is_portal_approved = True
    db.commit()
    db.refresh(customer)

    frontend_origin = (os.getenv("FRONTEND_BASE_URL") or str(request.base_url)).rstrip("/")
    return PortalLinkResponse(
        customer_id=customer.id,
        portal_access_token=customer.portal_access_token,
        storefront_url=f"{frontend_origin}/storefront/{customer.portal_access_token}",
        is_portal_approved=customer.is_portal_approved,
    )


@router.get("/reports/customer-weekly/{customer_id}", response_model=CustomerWeeklyReport)
def customer_weekly_report(
    customer_id: int,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    customer = (
        db.query(Customer)
        .filter(Customer.factory_id == current_user.factory_id)
        .filter(Customer.id == customer_id)
        .first()
    )
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)
    total_orders = int(
        db.query(sql_func.count(Order.id))
        .filter(Order.factory_id == current_user.factory_id)
        .filter(Order.customer_id == customer.id)
        .filter(Order.order_date >= week_start)
        .scalar()
        or 0
    )
    cash_paid = Decimal(
        db.query(sql_func.coalesce(sql_func.sum(SalesInvoice.amount_paid), 0))
        .filter(SalesInvoice.factory_id == current_user.factory_id)
        .filter(SalesInvoice.customer_id == customer.id)
        .filter(SalesInvoice.date >= week_start.date())
        .scalar()
        or 0
    )

    return CustomerWeeklyReport(
        customer_id=customer.id,
        total_orders_this_week=total_orders,
        cash_paid=cash_paid,
        current_outstanding_balance=Decimal(customer.balance_amount or 0),
    )


@router.post("/automation/trigger-payment-reminders", response_model=PaymentReminderTriggerResponse)
async def trigger_payment_reminders(
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    webhook_url = (os.getenv("N8N_PAYMENT_REMINDER_WEBHOOK") or "http://localhost:5678/webhook/payment-reminder").strip()
    fallback_webhook_url = "http://n8n:5678/webhook/payment-reminder"
    try:
        dues = pending_payment_dues(db, current_user.factory_id)
        sent_count = 0
        async with httpx.AsyncClient(timeout=10) as client:
            for due in dues:
                payload = {
                    "factory_id": current_user.factory_id,
                    "customer_name": due.customer_name,
                    "customer_phone": due.customer_phone,
                    "invoice_id": due.invoice_id,
                    "pending_amount": str(due.pending_amount),
                    "total_amount": str(due.total_amount),
                }
                try:
                    await client.post(webhook_url, json=payload)
                except httpx.RequestError:
                    await client.post(fallback_webhook_url, json=payload)
                sent_count += 1
        return PaymentReminderTriggerResponse(
            message="Automated follow-up cues pushed to n8n successfully!",
            reminders_pushed=sent_count,
            webhook_url=webhook_url,
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Payment reminder trigger failed: {exc}") from exc

import os
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db
from models import Factory, User
from payments.cashfree_client import CashfreeAPIError, CashfreeClient
from routers.super_admin import require_super_admin
from billing_schemas import CashfreeCreateSubscriptionRequest, CashfreeCreateSubscriptionResponse


router = APIRouter(
    prefix="/api/super-admin/billing",
    tags=["super-admin-billing"],
    dependencies=[Depends(require_super_admin)],
)


def _client() -> CashfreeClient:
    required = {
        "client_id": os.getenv("CASHFREE_CLIENT_ID", ""),
        "client_secret": os.getenv("CASHFREE_CLIENT_SECRET", ""),
        "api_base": os.getenv("CASHFREE_API_BASE", "https://sandbox.cashfree.com/pg"),
        "env": os.getenv("CASHFREE_ENV", "sandbox"),
    }
    if not required["client_id"] or not required["client_secret"]:
        raise HTTPException(status_code=503, detail="Cashfree credentials are not configured")
    return CashfreeClient(**required)


@router.post("/cashfree/create-subscription", response_model=CashfreeCreateSubscriptionResponse)
def create_cashfree_subscription(
    payload: CashfreeCreateSubscriptionRequest,
    db: Session = Depends(get_db),
):
    factory_id = payload.model_dump()["factory_id"]
    factory = db.query(Factory).filter(Factory.id == factory_id).first()
    if factory is None:
        raise HTTPException(status_code=404, detail="Factory not found")
    if factory.cashfree_subscription_id:
        return CashfreeCreateSubscriptionResponse(
            cashfree_customer_id=factory.cashfree_customer_id or f"factory_{factory.id}",
            cashfree_subscription_id=factory.cashfree_subscription_id,
            hosted_payment_url=f"https://payments.cashfree.com/subscription/{factory.cashfree_subscription_id}",
            subscription_status=factory.subscription_status,
        )
    plan_id = os.getenv(f"CASHFREE_PLAN_ID_{payload.plan_code.upper()}", "")
    if not plan_id:
        raise HTTPException(status_code=503, detail=f"Cashfree {payload.plan_code} plan is not configured")
    owner = db.query(User).filter(User.factory_id == factory.id, User.role == "Owner").first()
    if owner is None or not owner.phone_number:
        raise HTTPException(status_code=422, detail="Factory owner phone is required")
    client = _client()
    local_customer_id = f"factory_{factory.id}"
    try:
        customer = client.create_customer(
            local_customer_id,
            owner.email or owner.username,
            owner.phone_number,
            owner.full_name or factory.factory_name or factory.name,
        )
        subscription_id = f"factory_{factory.id}_{uuid4().hex[:12]}"
        result = client.create_subscription(
            str(customer.get("customer_uid") or local_customer_id),
            plan_id,
            subscription_id,
            f"Munshi AI {payload.plan_code} subscription",
            customer_details={
                "customer_name": owner.full_name or factory.name,
                "customer_email": owner.email or owner.username,
                "customer_phone": owner.phone_number[-10:],
                "customer_id": local_customer_id,
            },
        )
    except CashfreeAPIError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail="Cashfree subscription creation failed") from exc
    hosted_url = (
        result.get("subscription_session_id")
        or result.get("authorization_details", {}).get("authorization_link")
        or result.get("auth_link")
    )
    if not hosted_url:
        db.rollback()
        raise HTTPException(status_code=502, detail="Cashfree response did not include an authorization URL")
    factory.cashfree_customer_id = str(customer.get("customer_uid") or local_customer_id)
    factory.cashfree_subscription_id = str(result.get("subscription_id") or subscription_id)
    factory.cashfree_plan_code = payload.plan_code
    factory.subscription_status = "pending"
    db.commit()
    return CashfreeCreateSubscriptionResponse(
        cashfree_customer_id=factory.cashfree_customer_id,
        cashfree_subscription_id=factory.cashfree_subscription_id,
        hosted_payment_url=hosted_url,
        subscription_status=factory.subscription_status,
    )

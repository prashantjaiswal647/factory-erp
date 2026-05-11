from datetime import datetime, timedelta, timezone
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import check_permissions, get_current_active_user
from db import get_db
from models import Factory, User

try:
    import razorpay
except ImportError:  # pragma: no cover - optional SaaS dependency
    razorpay = None


router = APIRouter(prefix="/api/billing", tags=["billing"])


SUBSCRIPTION_AMOUNT_PAISE = int(os.getenv("RAZORPAY_PLAN_AMOUNT_PAISE") or "99900")
SUBSCRIPTION_CURRENCY = "INR"


class BillingStatusResponse(BaseModel):
    subscription_status: str
    trial_end_date: Optional[datetime] = None
    trial_days_remaining: int
    is_access_allowed: bool
    is_owner: bool


class CreateOrderResponse(BaseModel):
    key_id: str
    order_id: str
    amount: int
    currency: str


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class VerifyPaymentResponse(BillingStatusResponse):
    razorpay_payment_id: str


def _remaining_days(factory: Factory) -> int:
    if factory.trial_end_date is None:
        return 0
    trial_end = factory.trial_end_date
    if trial_end.tzinfo is None:
        trial_end = trial_end.replace(tzinfo=timezone.utc)
    seconds = (trial_end - datetime.now(timezone.utc)).total_seconds()
    if seconds <= 0:
        return 0
    return max(1, int((seconds + 86399) // 86400))


def _sync_subscription(factory: Factory) -> None:
    now = datetime.now(timezone.utc)
    if factory.trial_start_date is None:
        factory.trial_start_date = now
    if factory.trial_end_date is None:
        factory.trial_end_date = now + timedelta(days=3)
    trial_end = factory.trial_end_date
    if trial_end.tzinfo is None:
        trial_end = trial_end.replace(tzinfo=timezone.utc)
    if factory.subscription_status == "trial" and trial_end < now:
        factory.subscription_status = "expired"


def _factory_for_user(db: Session, current_user: User) -> Factory:
    factory = db.query(Factory).filter(Factory.id == current_user.factory_id).first()
    if factory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Factory not found")
    _sync_subscription(factory)
    db.commit()
    db.refresh(factory)
    return factory


def _razorpay_client():
    if razorpay is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay SDK is not installed",
        )
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay credentials are not configured",
        )
    return key_id, razorpay.Client(auth=(key_id, key_secret))


def _status_payload(factory: Factory, current_user: User) -> BillingStatusResponse:
    return BillingStatusResponse(
        subscription_status=factory.subscription_status or "trial",
        trial_end_date=factory.trial_end_date,
        trial_days_remaining=_remaining_days(factory),
        is_access_allowed=(factory.subscription_status in {"trial", "active"}),
        is_owner=(current_user.role == "Owner"),
    )


@router.get("/status", response_model=BillingStatusResponse)
def billing_status(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    factory = _factory_for_user(db, current_user)
    return _status_payload(factory, current_user)


@router.post("/create-order", response_model=CreateOrderResponse)
def create_order(
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    factory = _factory_for_user(db, current_user)
    key_id, client = _razorpay_client()
    order = client.order.create(
        {
            "amount": SUBSCRIPTION_AMOUNT_PAISE,
            "currency": SUBSCRIPTION_CURRENCY,
            "receipt": f"factory_{factory.id}_{int(datetime.now(timezone.utc).timestamp())}",
            "notes": {"factory_id": str(factory.id), "plan": "munshi-ai-monthly"},
        }
    )
    return CreateOrderResponse(
        key_id=key_id,
        order_id=order["id"],
        amount=int(order["amount"]),
        currency=order["currency"],
    )


@router.post("/verify", response_model=VerifyPaymentResponse)
def verify_payment(
    payload: VerifyPaymentRequest,
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    factory = _factory_for_user(db, current_user)
    _, client = _razorpay_client()
    try:
        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": payload.razorpay_order_id,
                "razorpay_payment_id": payload.razorpay_payment_id,
                "razorpay_signature": payload.razorpay_signature,
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Razorpay payment verification failed",
        ) from exc

    factory.subscription_status = "active"
    factory.trial_end_date = datetime.now(timezone.utc) + timedelta(days=30)
    factory.razorpay_subscription_id = payload.razorpay_payment_id
    db.commit()
    db.refresh(factory)
    status_payload = _status_payload(factory, current_user)
    return VerifyPaymentResponse(
        **status_payload.model_dump(),
        razorpay_payment_id=payload.razorpay_payment_id,
    )

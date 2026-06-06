from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import get_current_active_user
from db import get_db
from models import Factory, User
from billing_schemas import BillingMeResponse


router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@router.get("/me", response_model=BillingMeResponse)
def billing_me(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    factory = db.query(Factory).filter(Factory.id == current_user.factory_id).first()
    if factory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Factory not found")
    now = datetime.now(timezone.utc)
    subscription_status = factory.subscription_status
    current_period_end = factory.current_period_end
    if current_period_end and current_period_end.tzinfo is None:
        current_period_end = current_period_end.replace(tzinfo=timezone.utc)
    if subscription_status == "active" and current_period_end and current_period_end < now:
        subscription_status = "past_due"
    trial_end = factory.trial_end or factory.trial_end_date
    is_payable = subscription_status in {None, "cancelled", "past_due", "expired", "trial_expired", "payment_pending"}
    if subscription_status in {"trial", "trial_active"}:
        is_payable = bool(trial_end and (trial_end.replace(tzinfo=timezone.utc) if trial_end.tzinfo is None else trial_end) < now)
    return BillingMeResponse(
        subscription_status=subscription_status,
        trial_end=trial_end,
        current_period_start=factory.current_period_start,
        current_period_end=current_period_end,
        next_billing_at=factory.next_billing_at,
        cancelled_at=factory.cancelled_at,
        plan_code=factory.cashfree_plan_code,
        is_payable=is_payable,
    )

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, HttpUrl


class CashfreeCreateSubscriptionRequest(BaseModel):
    factory_id: int
    plan_code: Literal["monthly", "quarterly", "yearly"]


class CashfreeCreateSubscriptionResponse(BaseModel):
    cashfree_customer_id: str
    cashfree_subscription_id: str
    hosted_payment_url: HttpUrl
    subscription_status: str


class BillingMeResponse(BaseModel):
    subscription_status: str | None
    trial_end: datetime | None
    current_period_start: datetime | None
    current_period_end: datetime | None
    next_billing_at: datetime | None
    cancelled_at: datetime | None
    plan_code: str | None
    is_payable: bool
    hosted_payment_url: str | None = None

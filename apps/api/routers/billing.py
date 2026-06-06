from datetime import datetime, timedelta, timezone
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, object_session

from auth import JWT_ALGORITHM, check_permissions, get_current_active_user, get_effective_subscription, get_jwt_secret_key, get_user_by_subject, is_trial_bypass_enabled, normalize_phone_number, set_no_store_headers
from db import get_db
from models import CustomPlanEnquiry, DemoBookingRequest, Factory, SubscriptionPayment, User

try:
    import razorpay
except ImportError:  # pragma: no cover - optional SaaS dependency
    razorpay = None


router = APIRouter(prefix="/api/billing", tags=["billing"])
optional_bearer = HTTPBearer(auto_error=False)


SUBSCRIPTION_CURRENCY = "INR"
TRIAL_DAYS = 7
EXPIRED_STATUSES = {"trial_expired", "expired", "cancelled", "payment_pending"}


class PlanPrice(BaseModel):
    monthly: int
    yearly_original: Optional[int] = None
    yearly_discounted: Optional[int] = None
    starts_from: Optional[int] = None


class PricingPlan(BaseModel):
    code: str
    name: str
    machine_limit_label: str
    monthly_label: str
    yearly_label: Optional[str] = None
    features: list[str]
    price: PlanPrice
    is_custom: bool = False


class BillingStatusResponse(BaseModel):
    subscription_status: str
    trial_start_date: Optional[datetime] = None
    trial_end_date: Optional[datetime] = None
    trial_days_remaining: int
    is_access_allowed: bool
    access_allowed: bool
    is_owner: bool
    active_plan: Optional[str] = None
    plan_name: Optional[str] = None
    plan_expires_at: Optional[datetime] = None
    billing_cycle: Optional[str] = None
    subscription_start_date: Optional[datetime] = None
    subscription_end_date: Optional[datetime] = None
    payment_status: Optional[str] = None
    days_left: int = 0
    server_time: datetime
    is_manual_override: bool = False
    effective_plan: Optional[str] = None
    effective_status: Optional[str] = None
    effective_expires_at: Optional[datetime] = None


class SubscriptionPaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_code: str
    billing_cycle: str
    amount_paise: int
    currency: str
    payment_status: str
    provider: Optional[str] = None
    provider_payment_id: Optional[str] = None
    subscription_start_date: datetime
    subscription_end_date: datetime
    created_at: datetime


class CreateOrderRequest(BaseModel):
    plan_code: str = "basic"
    billing_cycle: str = "monthly"


class StartTrialRequest(BaseModel):
    plan_code: str = "basic"


class CreateOrderResponse(BaseModel):
    key_id: str
    order_id: str
    amount: int
    currency: str
    plan_code: str
    billing_cycle: str


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan_code: str = "basic"
    billing_cycle: str = "monthly"


class ActivateSubscriptionRequest(BaseModel):
    plan_code: str
    billing_cycle: str
    provider_payment_id: Optional[str] = None
    payment_status: str = "paid"


class VerifyPaymentResponse(BillingStatusResponse):
    razorpay_payment_id: str


class CustomPlanEnquiryRequest(BaseModel):
    owner_name: str = Field(min_length=2)
    factory_name: str = Field(min_length=2)
    country_code: str = Field(default="+91", min_length=1, max_length=8)
    phone: str = Field(min_length=6)
    email: str = Field(min_length=5)
    number_of_machines: int = Field(ge=51)
    requirement_details: str = Field(min_length=10)


class DemoBookingRequestPayload(BaseModel):
    owner_name: str = Field(min_length=2)
    factory_name: Optional[str] = None
    country_code: str = Field(default="+91", min_length=1, max_length=8)
    phone: str = Field(min_length=6)
    email: str = Field(min_length=5)
    preferred_plan: Optional[str] = None
    message: Optional[str] = None


class SubmissionResponse(BaseModel):
    id: int
    message: str


PLANS: list[PricingPlan] = [
    PricingPlan(
        code="basic",
        name="Basic",
        machine_limit_label="Up to 7 Machines",
        monthly_label="₹999 + GST / month",
        yearly_label="₹9,999 + GST / year",
        features=["Up to 7 Machines", "Production, inventory, finance", "E-invoicing", "AI reports"],
        price=PlanPrice(monthly=99900, yearly_original=1198800, yearly_discounted=999900),
    ),
    PricingPlan(
        code="growth",
        name="Growth",
        machine_limit_label="Up to 20 Machines",
        monthly_label="₹1,999 + GST / month",
        yearly_label="₹19,999 + GST / year",
        features=["Up to 20 Machines", "Advanced dashboards", "Payment reminders", "n8n automation"],
        price=PlanPrice(monthly=199900, yearly_original=2398800, yearly_discounted=1999900),
    ),
    PricingPlan(
        code="premium",
        name="Premium",
        machine_limit_label="20 to 50 Machines",
        monthly_label="₹4,999 + GST / month",
        yearly_label="₹49,999 + GST / year",
        features=["20 to 50 Machines", "Priority AI workflows", "Advanced analytics", "Priority support"],
        price=PlanPrice(monthly=499900, yearly_original=5998800, yearly_discounted=4999900),
    ),
    PricingPlan(
        code="custom",
        name="Custom",
        machine_limit_label="50+ machines / special requirements",
        monthly_label="Starts from ₹1,00,000 + GST",
        features=["50+ machines", "Custom workflows", "Implementation support", "Dedicated success planning"],
        price=PlanPrice(monthly=0, starts_from=10000000),
        is_custom=True,
    ),
]


def plan_by_code(plan_code: str) -> PricingPlan:
    for plan in PLANS:
        if plan.code == plan_code:
            return plan
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown billing plan")


def amount_for(plan_code: str, billing_cycle: str) -> int:
    plan = plan_by_code(plan_code)
    if plan.is_custom:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Custom plan requires sales enquiry")
    if billing_cycle == "monthly":
        return plan.price.monthly
    if billing_cycle == "yearly" and plan.price.yearly_discounted is not None:
        return plan.price.yearly_discounted
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid billing cycle")


def has_active_access(factory: Factory) -> bool:
    if factory.subscription_status == "active":
        return True
    return factory.subscription_status == "trial_active" and factory.active_plan == "basic"


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if credentials is None:
        return None
    try:
        payload = jwt.decode(credentials.credentials, get_jwt_secret_key(), algorithms=[JWT_ALGORITHM])
        subject = payload.get("sub")
        if not isinstance(subject, str):
            return None
    except JWTError:
        return None
    return get_user_by_subject(db, subject)


def normalize_status(factory: Factory) -> None:
    if factory.subscription_status == "trial":
        factory.subscription_status = "trial_active"
    if factory.subscription_status == "trial_active" and not factory.active_plan:
        factory.active_plan = "basic"
    if factory.payment_status is None:
        factory.payment_status = "payment_pending"


def remaining_trial_days(factory: Factory) -> int:
    if factory.trial_end_date is None:
        return 0
    trial_end = factory.trial_end_date
    if trial_end.tzinfo is None:
        trial_end = trial_end.replace(tzinfo=timezone.utc)
    seconds = (trial_end - datetime.now(timezone.utc)).total_seconds()
    if seconds <= 0:
        return 0
    return max(1, int((seconds + 86399) // 86400))


def sync_subscription(factory: Factory) -> None:
    now = datetime.now(timezone.utc)
    
    # If manual override is active, bypass standard expiration check
    if getattr(factory, "subscription_override", False) is True:
        # Auto-restore override status if override expires in the future
        override_expires_at = getattr(factory, "override_expires_at", None)
        if override_expires_at is not None and override_expires_at.tzinfo is None:
            override_expires_at = override_expires_at.replace(tzinfo=timezone.utc)
        if override_expires_at is None or override_expires_at >= now:
            factory.subscription_status = "active"
            if factory.payment_status not in {"manual_override", "paid"}:
                factory.payment_status = "manual_override"
        else:
            factory.subscription_status = "expired"
            factory.payment_status = "payment_pending"
        return

    normalize_status(factory)
    if factory.trial_start_date is None:
        factory.trial_start_date = now
    if factory.trial_end_date is None:
        factory.trial_end_date = now + timedelta(days=TRIAL_DAYS)
        
    trial_end = factory.trial_end_date
    if trial_end is not None and trial_end.tzinfo is None:
        trial_end = trial_end.replace(tzinfo=timezone.utc)
    subscription_end = factory.subscription_end_date or getattr(factory, "subscription_end", None)
    if subscription_end is not None and subscription_end.tzinfo is None:
        subscription_end = subscription_end.replace(tzinfo=timezone.utc)
    plan_expires_at = getattr(factory, "plan_expires_at", None)
    if plan_expires_at is not None and plan_expires_at.tzinfo is None:
        plan_expires_at = plan_expires_at.replace(tzinfo=timezone.utc)
    paid_future_expiry = next(
        (expiry for expiry in (subscription_end, plan_expires_at) if expiry is not None and expiry >= now),
        None,
    )

    # AUTO-RESTORE logic:
    # If DB contains a future expiry date but status is expired/trial_expired, auto-restore them!
    if factory.subscription_status in {"expired", "trial_expired", "cancelled", "payment_pending"}:
        if paid_future_expiry is not None:
            factory.subscription_status = "active"
            factory.payment_status = "paid"
        elif trial_end is not None and trial_end >= now:
            factory.subscription_status = "trial_active"
            factory.payment_status = "payment_pending"

    if is_trial_bypass_enabled():
        return

    if factory.subscription_status == "trial_active" and trial_end is not None and trial_end < now:
        factory.subscription_status = "trial_expired"
        factory.payment_status = "payment_pending"
    if factory.subscription_status == "active" and paid_future_expiry is None and (subscription_end is not None or plan_expires_at is not None):
        factory.subscription_status = "expired"
        factory.payment_status = "payment_pending"


def factory_for_user(db: Session, current_user: User) -> Factory:
    factory = db.query(Factory).filter(Factory.id == current_user.factory_id).populate_existing().first()
    if factory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Factory not found")
    sync_subscription(factory)
    db.commit()
    db.refresh(factory)
    return factory


def razorpay_client():
    if razorpay is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Razorpay SDK is not installed")
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Razorpay credentials are not configured")
    return key_id, razorpay.Client(auth=(key_id, key_secret))


def status_payload(factory: Factory, current_user: User, res: Optional[dict] = None) -> BillingStatusResponse:
    if res is None:
        res = get_effective_subscription(object_session(factory), factory.id) if object_session(factory) else None
    if res is None:
        from auth import resolve_factory_subscription
        res = resolve_factory_subscription(factory)
    bypass_enabled = is_trial_bypass_enabled()
    
    is_access_allowed = bypass_enabled or res["access_allowed"]
    
    return BillingStatusResponse(
        subscription_status=res["subscription_status"] or "trial_active",
        trial_start_date=factory.trial_start_date,
        trial_end_date=res["trial_end_date"],
        trial_days_remaining=res["days_left"] if res["effective_status"] == "trial_active" else remaining_trial_days(factory),
        is_access_allowed=is_access_allowed,
        access_allowed=is_access_allowed,
        is_owner=(current_user.role == "Owner"),
        active_plan=res["active_plan"] or res["plan_name"],
        plan_name=res["plan_name"],
        plan_expires_at=res["plan_expires_at"],
        billing_cycle=res["billing_cycle"],
        subscription_start_date=factory.subscription_start_date,
        subscription_end_date=res["subscription_end_date"],
        payment_status=res["payment_status"],
        days_left=res["days_left"],
        server_time=res["server_time"],
        is_manual_override=res["is_manual_override"],
        effective_plan=res["effective_plan"],
        effective_status=res["effective_status"],
        effective_expires_at=res["effective_expires_at"],
    )


def activate_factory_subscription(db: Session, factory: Factory, plan_code: str, billing_cycle: str, provider_payment_id: Optional[str]) -> None:
    now = datetime.now(timezone.utc)
    duration = timedelta(days=365 if billing_cycle == "yearly" else 30)
    amount = amount_for(plan_code, billing_cycle)
    existing_end = factory.subscription_end_date or getattr(factory, "subscription_end", None) or factory.plan_expires_at
    if existing_end is not None and existing_end.tzinfo is None:
        existing_end = existing_end.replace(tzinfo=timezone.utc)
    cycle_start = existing_end if existing_end is not None and existing_end > now else now
    cycle_end = cycle_start + duration

    factory.subscription_status = "active"
    factory.active_plan = plan_code
    factory.plan_name = plan_code
    factory.billing_cycle = billing_cycle
    factory.subscription_start_date = factory.subscription_start_date or cycle_start
    factory.subscription_end_date = cycle_end
    factory.subscription_start = cycle_start
    factory.subscription_end = cycle_end
    factory.plan_expires_at = cycle_end
    factory.payment_status = "paid"
    factory.is_active = True
    if provider_payment_id:
        factory.razorpay_subscription_id = provider_payment_id
    db.add(
        SubscriptionPayment(
            factory_id=factory.id,
            plan_code=plan_code,
            billing_cycle=billing_cycle,
            amount_paise=amount,
            currency=SUBSCRIPTION_CURRENCY,
            payment_status="paid",
            provider="razorpay" if provider_payment_id else "manual",
            provider_payment_id=provider_payment_id,
            subscription_start_date=cycle_start,
            subscription_end_date=cycle_end,
        )
    )


@router.get("/plans", response_model=list[PricingPlan])
def pricing_plans():
    try:
        return PLANS if PLANS else []
    except Exception:
        return []


@router.post("/custom-enquiry", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
def custom_plan_enquiry(
    payload: CustomPlanEnquiryRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    full_phone_number, _ = normalize_phone_number(payload.phone, payload.country_code)
    enquiry = CustomPlanEnquiry(
        factory_id=current_user.factory_id if current_user and current_user.factory_id > 0 else None,
        owner_name=payload.owner_name,
        factory_name=payload.factory_name,
        phone=full_phone_number,
        email=str(payload.email),
        number_of_machines=payload.number_of_machines,
        requirement_details=payload.requirement_details,
    )
    db.add(enquiry)
    db.commit()
    db.refresh(enquiry)
    return SubmissionResponse(id=enquiry.id, message="Custom plan enquiry submitted")


@router.post("/demo-booking", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
def demo_booking_request(
    payload: DemoBookingRequestPayload,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    full_phone_number, _ = normalize_phone_number(payload.phone, payload.country_code)
    booking = DemoBookingRequest(
        factory_id=current_user.factory_id if current_user and current_user.factory_id > 0 else None,
        owner_name=payload.owner_name,
        factory_name=payload.factory_name,
        phone=full_phone_number,
        email=str(payload.email),
        preferred_plan=payload.preferred_plan,
        message=payload.message,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return SubmissionResponse(id=booking.id, message="Demo booking request submitted")


@router.post("/start-free-trial", response_model=BillingStatusResponse)
def start_free_trial(
    payload: StartTrialRequest = StartTrialRequest(),
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    if payload.plan_code != "basic":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Free trial is available only on the Basic plan",
        )
    factory = factory_for_user(db, current_user)
    now = datetime.now(timezone.utc)
    factory.trial_start_date = factory.trial_start_date or now
    factory.trial_end_date = now + timedelta(days=TRIAL_DAYS)
    factory.subscription_status = "trial_active"
    factory.active_plan = "basic"
    factory.billing_cycle = None
    factory.payment_status = "payment_pending"
    db.commit()
    db.refresh(factory)
    return status_payload(factory, current_user)


@router.get("/status", response_model=BillingStatusResponse)
def billing_status(
    response: Response,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    set_no_store_headers(response)
    res = get_effective_subscription(db, current_user.factory_id)
    factory = db.query(Factory).filter(Factory.id == current_user.factory_id).populate_existing().first()
    if factory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Factory not found")
    return status_payload(factory, current_user, res)


@router.get("/history", response_model=list[SubscriptionPaymentResponse])
def billing_history(
    response: Response,
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    set_no_store_headers(response)
    return (
        db.query(SubscriptionPayment)
        .filter(SubscriptionPayment.factory_id == current_user.factory_id)
        .order_by(SubscriptionPayment.subscription_start_date.desc(), SubscriptionPayment.id.desc())
        .all()
    )


@router.post("/create-order", response_model=CreateOrderResponse)
def create_order(
    payload: CreateOrderRequest,
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    factory = factory_for_user(db, current_user)
    amount = amount_for(payload.plan_code, payload.billing_cycle)
    key_id, client = razorpay_client()
    order = client.order.create(
        {
            "amount": amount,
            "currency": SUBSCRIPTION_CURRENCY,
            "receipt": f"factory_{factory.id}_{payload.plan_code}_{int(datetime.now(timezone.utc).timestamp())}",
            "notes": {"factory_id": str(factory.id), "plan": payload.plan_code, "billing_cycle": payload.billing_cycle},
        }
    )
    return CreateOrderResponse(
        key_id=key_id,
        order_id=order["id"],
        amount=int(order["amount"]),
        currency=order["currency"],
        plan_code=payload.plan_code,
        billing_cycle=payload.billing_cycle,
    )


@router.post("/verify", response_model=VerifyPaymentResponse)
def verify_payment(
    payload: VerifyPaymentRequest,
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    factory = factory_for_user(db, current_user)
    _, client = razorpay_client()
    try:
        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": payload.razorpay_order_id,
                "razorpay_payment_id": payload.razorpay_payment_id,
                "razorpay_signature": payload.razorpay_signature,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Razorpay payment verification failed") from exc

    activate_factory_subscription(db, factory, payload.plan_code, payload.billing_cycle, payload.razorpay_payment_id)
    db.commit()
    db.refresh(factory)
    status_response = status_payload(factory, current_user)
    return VerifyPaymentResponse(**status_response.model_dump(), razorpay_payment_id=payload.razorpay_payment_id)


@router.post("/activate", response_model=BillingStatusResponse)
def activate_subscription(
    payload: ActivateSubscriptionRequest,
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    factory = factory_for_user(db, current_user)
    if payload.payment_status != "paid":
        factory.payment_status = "payment_pending"
        factory.subscription_status = "payment_pending"
    else:
        activate_factory_subscription(db, factory, payload.plan_code, payload.billing_cycle, payload.provider_payment_id)
    db.commit()
    db.refresh(factory)
    return status_payload(factory, current_user)


@router.get("/expiring-soon", response_model=list[BillingStatusResponse])
def subscriptions_expiring_soon(
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    soon = now + timedelta(days=7)
    factories = (
        db.query(Factory)
        .filter(Factory.subscription_status == "active")
        .filter(Factory.subscription_end_date.isnot(None))
        .filter(Factory.subscription_end_date >= now)
        .filter(Factory.subscription_end_date <= soon)
        .order_by(Factory.subscription_end_date.asc())
        .all()
    )
    return [status_payload(factory, current_user) for factory in factories]

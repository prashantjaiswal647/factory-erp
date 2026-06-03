from datetime import datetime, timedelta, timezone
import os
import random
import re
from typing import Callable, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from db import get_db
from models import AppUsageLog, Factory, OTPStore, User, SuperAdminAuditLog
#from services.google_sheets_provider import initialize_factory_google_sheet_task

try:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token
except ImportError:  # pragma: no cover - optional SaaS dependency
    google_requests = None
    google_id_token = None


JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES") or "480") # 8 hours
OTP_EXPIRE_MINUTES = int(os.getenv("OTP_EXPIRE_MINUTES") or "10")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

router = APIRouter(prefix="/api/auth", tags=["auth"])
public_router = APIRouter(prefix="/auth", tags=["auth"])
v1_router = APIRouter(prefix="/api/v1", tags=["v1"])


def is_trial_bypass_enabled() -> bool:
    return (
        os.getenv("ENV", "").strip().lower() == "development"
        or os.getenv("APP_ENV", "").strip().lower() == "development"
        or os.getenv("BYPASS_TRIAL", "").strip().lower() in {"1", "true", "yes", "on"}
    )


def get_jwt_secret_key() -> str:
    secret_key = os.getenv("JWT_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("JWT_SECRET_KEY environment variable is required")
    return secret_key


def ensure_auth_config() -> None:
    get_jwt_secret_key()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


SUPPORTED_PHONE_COUNTRIES = {
    "+91": {"name": "India", "min": 10, "max": 10},
    "+1": {"name": "United States", "min": 10, "max": 10},
    "+44": {"name": "United Kingdom", "min": 10, "max": 10},
    "+971": {"name": "UAE", "min": 9, "max": 9},
}


def phone_digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def normalize_country_code(country_code: str | None) -> str:
    code = (country_code or "").strip()
    if code and not code.startswith("+"):
        code = f"+{code}"
    if code not in SUPPORTED_PHONE_COUNTRIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported country code",
        )
    return code


def normalize_phone_number(phone_number: str, country_code: str | None = None) -> tuple[str, str]:
    raw = (phone_number or "").strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Phone number is required",
        )
    if raw.startswith("+"):
        compact = raw.replace(" ", "")
        code = next(
            (item for item in sorted(SUPPORTED_PHONE_COUNTRIES, key=len, reverse=True) if compact.startswith(item)),
            "",
        )
        if not code:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unsupported country code",
            )
        local_digits = phone_digits(compact[len(code):])
    elif country_code:
        code = normalize_country_code(country_code)
        local_digits = phone_digits(raw)
    else:
        code = "+91"
        local_digits = phone_digits(raw)

    rule = SUPPORTED_PHONE_COUNTRIES[code]
    if len(local_digits) < rule["min"] or len(local_digits) > rule["max"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {rule['name']} mobile number",
        )
    return f"{code}{local_digits}", local_digits


def normalized_phone_digits_for_lookup(phone_number: str | None) -> str | None:
    if not phone_number:
        return None
    try:
        _, local_digits = normalize_phone_number(phone_number)
        return local_digits
    except HTTPException:
        digits = phone_digits(phone_number)
        return digits or None


def create_access_token(subject: str, role: str, factory_id: Optional[int], user_id: Optional[str] = None) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": subject,
        "user_id": user_id,
        "role": role,
        "factory_id": factory_id,
        "exp": expires_at,
    }
    return jwt.encode(payload, get_jwt_secret_key(), algorithm=JWT_ALGORITHM)


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return (
        db.query(User)
        .filter(sql_func.lower(User.username) == username.lower())
        .first()
    )


def get_user_by_phone(db: Session, phone_number: str) -> Optional[User]:
    raw = (phone_number or "").strip()
    normalized_digits = phone_digits(raw)
    if normalized_digits:
        user = (
            db.query(User)
            .filter(User.phone_number_normalized == normalized_digits)
            .first()
        )
        if user is not None:
            return user
    return (
        db.query(User)
        .filter(sql_func.lower(User.phone_number) == raw.lower())
        .first()
    )


def get_user_by_subject(db: Session, subject: str) -> Optional[User]:
    # Try phone first, then fallback to username
    user = (
        db.query(User)
        .filter(sql_func.lower(User.phone_number) == subject.lower())
        .first()
    )
    if user is not None:
        return user
    return get_user_by_username(db, subject)


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    identifier = username.strip()
    user = get_user_by_username(db, identifier) if "@" in identifier else get_user_by_phone(db, identifier)
    if user is None and "@" not in identifier:
        user = get_user_by_username(db, identifier)
    if user is None:
        print(f"AUTH DEBUG: User not found for identifier={identifier!r}")
        return None
    try:
        password_matches = verify_password(password, user.password_hash)
    except Exception as exc:
        print(f"AUTH DEBUG: Password hash verification error for user_id={user.id}, identifier={identifier!r}: {exc}")
        return None
    if not password_matches:
        print(f"AUTH DEBUG: Password mismatch for user_id={user.id}, identifier={identifier!r}")
        return None
    print(f"AUTH DEBUG: Authentication success for user_id={user.id}, role={user.role}, factory_id={user.factory_id}")
    return user


class LoginRequest(BaseModel):
    identifier: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=255)


class SignupRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = Field(default=None, max_length=255)
    country_code: str = Field(default="+91", min_length=1, max_length=8)
    phone_number: str = Field(..., min_length=1, max_length=50)
    factory_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=6, max_length=255)


class GoogleLoginRequest(BaseModel):
    credential: str = Field(..., min_length=1)


class GoogleSignupCompleteRequest(BaseModel):
    credential: str = Field(..., min_length=1)
    country_code: str = Field(default="+91", min_length=1, max_length=8)
    phone_number: str = Field(..., min_length=5, max_length=50)


class UserProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255)
    country_code: str = Field(default="+91", min_length=1, max_length=8)
    phone_number: str = Field(..., min_length=5, max_length=50)


class AuthUserProfile(BaseModel):
    id: int
    user_id: Optional[str] = None
    factory_id: int
    username: str
    phone_number: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    factory_name: Optional[str] = None
    subscription_status: Optional[str] = None
    trial_end_date: Optional[datetime] = None
    trial_days_remaining: int = 0


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserProfile


def ensure_user_uuid(user: User, db: Session) -> str:
    if not user.user_id:
        user.user_id = str(uuid4())
        db.commit()
        db.refresh(user)
    return user.user_id


def ensure_factory_trial(factory: Optional[Factory]) -> None:
    if factory is None:
        return
    now = datetime.now(timezone.utc)
    
    # If manual override is active, do not run standard trial expiration check
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

    if factory.trial_start_date is None:
        factory.trial_start_date = now
    if factory.trial_end_date is None:
        factory.trial_end_date = now + timedelta(days=7)
    if not factory.subscription_status:
        factory.subscription_status = "trial_active"
    if factory.subscription_status in {"trial", "trial_active"} and not getattr(factory, "active_plan", None):
        factory.active_plan = "basic"
    if factory.payment_status is None:
        factory.payment_status = "payment_pending"
        
    trial_end = factory.trial_end_date
    if trial_end is not None and trial_end.tzinfo is None:
        trial_end = trial_end.replace(tzinfo=timezone.utc)
    subscription_end = getattr(factory, "subscription_end_date", None) or getattr(factory, "subscription_end", None)
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

    if factory.subscription_status == "trial":
        factory.subscription_status = "trial_active"
    if factory.subscription_status == "trial_active" and trial_end is not None and trial_end < now:
        factory.subscription_status = "trial_expired"
        factory.payment_status = "payment_pending"
    if factory.subscription_status == "active" and paid_future_expiry is None and (subscription_end is not None or plan_expires_at is not None):
        factory.subscription_status = "expired"
        factory.payment_status = "payment_pending"


def resolve_factory_subscription(factory: Optional[Factory]) -> dict:
    now = datetime.now(timezone.utc)

    def as_utc(value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def days_until(value: Optional[datetime]) -> int:
        if value is None or value < now:
            return 0
        total_seconds = int((value - now).total_seconds())
        return (total_seconds + 86399) // 86400

    def base_response(
        *,
        plan_name: str,
        plan_expires_at: Optional[datetime],
        subscription_status: Optional[str],
        payment_status: Optional[str],
        billing_cycle: Optional[str],
        is_manual_override: bool,
        raw_active_plan: Optional[str],
        raw_plan_name: Optional[str],
        raw_subscription_end_date: Optional[datetime],
        raw_plan_expires_at: Optional[datetime],
        raw_trial_end_date: Optional[datetime],
        access_allowed: bool,
        effective_plan: str,
        effective_status: Optional[str],
        effective_expires_at: Optional[datetime],
    ) -> dict:
        return {
            "plan_name": plan_name,
            "active_plan": raw_active_plan,
            "plan_expires_at": plan_expires_at,
            "subscription_status": subscription_status,
            "payment_status": payment_status,
            "billing_cycle": billing_cycle,
            "days_left": days_until(effective_expires_at),
            "server_time": now,
            "trial_end_date": raw_trial_end_date,
            "subscription_end_date": raw_subscription_end_date,
            "is_manual_override": is_manual_override,
            "access_allowed": access_allowed,
            "raw_active_plan": raw_active_plan,
            "raw_plan_name": raw_plan_name,
            "raw_subscription_end_date": raw_subscription_end_date,
            "raw_plan_expires_at": raw_plan_expires_at,
            "raw_trial_end_date": raw_trial_end_date,
            "effective_plan": effective_plan,
            "effective_status": effective_status,
            "effective_expires_at": effective_expires_at,
        }

    if factory is None:
        return base_response(
            plan_name="Free/Trial",
            plan_expires_at=None,
            subscription_status=None,
            payment_status=None,
            billing_cycle=None,
            is_manual_override=False,
            raw_active_plan=None,
            raw_plan_name=None,
            raw_subscription_end_date=None,
            raw_plan_expires_at=None,
            raw_trial_end_date=None,
            access_allowed=False,
            effective_plan="Free/Trial",
            effective_status=None,
            effective_expires_at=None,
        )

    # Extract raw fields
    raw_active_plan = getattr(factory, "active_plan", None)
    raw_plan_name = getattr(factory, "plan_name", None)
    raw_subscription_end_date = as_utc(getattr(factory, "subscription_end_date", None) or getattr(factory, "subscription_end", None))
    raw_plan_expires_at = as_utc(getattr(factory, "plan_expires_at", None))
    raw_trial_end_date = as_utc(getattr(factory, "trial_end_date", None))
        
    subscription_status = getattr(factory, "subscription_status", None)
    payment_status = getattr(factory, "payment_status", None)
    payment_status_key = payment_status.strip().lower() if isinstance(payment_status, str) else payment_status
    billing_cycle = getattr(factory, "billing_cycle", None)
    override_expires_at = as_utc(getattr(factory, "override_expires_at", None))
    paid_expires_at = next(
        (expiry for expiry in (raw_subscription_end_date, raw_plan_expires_at) if expiry is not None and expiry >= now),
        raw_subscription_end_date or raw_plan_expires_at,
    )

    if getattr(factory, "subscription_override", False) is True and override_expires_at is not None and override_expires_at >= now:
        plan_name = getattr(factory, "override_plan", None) or raw_active_plan or raw_plan_name or "premium"
        return base_response(
            plan_name=plan_name,
            plan_expires_at=override_expires_at,
            subscription_status="active",
            payment_status="manual_override",
            billing_cycle=billing_cycle,
            is_manual_override=True,
            raw_active_plan=raw_active_plan,
            raw_plan_name=raw_plan_name,
            raw_subscription_end_date=raw_subscription_end_date,
            raw_plan_expires_at=raw_plan_expires_at,
            raw_trial_end_date=raw_trial_end_date,
            access_allowed=True,
            effective_plan=plan_name,
            effective_status="active",
            effective_expires_at=override_expires_at,
        )

    if subscription_status == "active" and paid_expires_at is not None and paid_expires_at >= now:
        plan_name = raw_active_plan or raw_plan_name or "premium"
        return base_response(
            plan_name=plan_name,
            plan_expires_at=paid_expires_at,
            subscription_status="active",
            payment_status=payment_status,
            billing_cycle=billing_cycle,
            is_manual_override=False,
            raw_active_plan=raw_active_plan,
            raw_plan_name=raw_plan_name,
            raw_subscription_end_date=raw_subscription_end_date,
            raw_plan_expires_at=raw_plan_expires_at,
            raw_trial_end_date=raw_trial_end_date,
            access_allowed=True,
            effective_plan=plan_name,
            effective_status="active",
            effective_expires_at=paid_expires_at,
        )

    if subscription_status in {"trial", "trial_active"} and raw_trial_end_date is not None and raw_trial_end_date >= now:
        plan_name = raw_active_plan or raw_plan_name or "basic"
        return base_response(
            plan_name=plan_name,
            plan_expires_at=raw_trial_end_date,
            subscription_status="trial_active",
            payment_status=payment_status or "payment_pending",
            billing_cycle=billing_cycle,
            is_manual_override=False,
            raw_active_plan=raw_active_plan,
            raw_plan_name=raw_plan_name,
            raw_subscription_end_date=raw_subscription_end_date,
            raw_plan_expires_at=raw_plan_expires_at,
            raw_trial_end_date=raw_trial_end_date,
            access_allowed=True,
            effective_plan=plan_name,
            effective_status="trial_active",
            effective_expires_at=raw_trial_end_date,
        )

    expired_status = subscription_status or "expired"
    if payment_status_key == "payment_pending":
        expired_status = "payment_pending"
    elif expired_status in {"trial", "trial_active"}:
        expired_status = "trial_expired"
    elif expired_status == "active":
        expired_status = "expired"
    plan_name = raw_active_plan or raw_plan_name or "Free/Trial"
    expires_at = paid_expires_at or raw_trial_end_date
    return base_response(
        plan_name=plan_name,
        plan_expires_at=expires_at,
        subscription_status=expired_status,
        payment_status=payment_status or "payment_pending",
        billing_cycle=billing_cycle,
        is_manual_override=False,
        raw_active_plan=raw_active_plan,
        raw_plan_name=raw_plan_name,
        raw_subscription_end_date=raw_subscription_end_date,
        raw_plan_expires_at=raw_plan_expires_at,
        raw_trial_end_date=raw_trial_end_date,
        access_allowed=False,
        effective_plan=plan_name,
        effective_status=expired_status,
        effective_expires_at=expires_at,
    )


def log_subscription_resolution(factory_id: Optional[int], res: dict) -> None:
    print(
        "[SUBSCRIPTION_RESOLVER] "
        f"factory_id={factory_id} "
        f"active_plan={res.get('active_plan')} "
        f"plan_name={res.get('plan_name')} "
        f"subscription_status={res.get('subscription_status')} "
        f"payment_status={res.get('payment_status')} "
        f"subscription_end_date={res.get('subscription_end_date')} "
        f"plan_expires_at={res.get('plan_expires_at')} "
        f"days_left={res.get('days_left')} "
        f"access_allowed={res.get('access_allowed')}"
    )


def get_effective_subscription(db: Session, factory_id: Optional[int]) -> dict:
    if factory_id is None or factory_id <= 0:
        res = resolve_factory_subscription(None)
        log_subscription_resolution(factory_id, res)
        return res
    db.expire_all()
    factory = (
        db.query(Factory)
        .filter(Factory.id == factory_id)
        .populate_existing()
        .first()
    )
    res = resolve_factory_subscription(factory)
    log_subscription_resolution(factory_id, res)
    return res


def set_no_store_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


def trial_days_remaining(factory: Optional[Factory]) -> int:
    if factory is None or factory.trial_end_date is None:
        return 0
    trial_end = factory.trial_end_date
    if trial_end.tzinfo is None:
        trial_end = trial_end.replace(tzinfo=timezone.utc)
    seconds = (trial_end - datetime.now(timezone.utc)).total_seconds()
    if seconds <= 0:
        return 0
    return max(1, int((seconds + 86399) // 86400))


def build_login_response(user: User, db: Session) -> LoginResponse:
    user.last_login_at = datetime.now(timezone.utc)
    if user.phone_number and not user.phone_number_normalized:
        user.phone_number_normalized = normalized_phone_digits_for_lookup(user.phone_number)
    user_uuid = ensure_user_uuid(user, db)
    ensure_factory_trial(user.factory)
    if user.factory_id:
        db.add(
            AppUsageLog(
                factory_id=user.factory_id,
                user_id=user.id,
                event_type="login",
                route_or_module="auth",
                method="POST",
                meta={"role": user.role},
            )
        )
    db.commit()
    db.refresh(user)
    subject = user.phone_number if user.phone_number else user.username
    token = create_access_token(
        subject=subject,
        role=user.role,
        factory_id=user.factory_id if user.factory_id > 0 else None,
        user_id=user_uuid,
    )
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=AuthUserProfile(
            id=user.id,
            user_id=user_uuid,
            factory_id=user.factory_id,
            username=user.username,
            phone_number=user.phone_number,
            full_name=user.full_name,
            role=user.role,
            factory_name=user.factory.factory_name or user.factory.name if user.factory else None,
            subscription_status=user.factory.subscription_status if user.factory else None,
            trial_end_date=user.factory.trial_end_date if user.factory else None,
            trial_days_remaining=trial_days_remaining(user.factory),
        ),
    )


def is_subscription_bypass_path(path: str) -> bool:
    return (
        path.startswith("/api/auth")
        or path.startswith("/api/billing")
        or path.startswith("/api/v1/users/me/subscription")
        or path.startswith("/api/v1/dashboard/subscription-status")
    )


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, get_jwt_secret_key(), algorithms=[JWT_ALGORITHM])
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise credentials_error
    except JWTError as exc:
        raise credentials_error from exc

    user = get_user_by_subject(db, subject)
    if user is None:
        raise credentials_error
    if user.factory_id is not None and user.factory_id > 0:
        from services.tenant_context import set_current_tenant_id
        set_current_tenant_id(user.factory_id)
        res = get_effective_subscription(db, user.factory_id)
        has_subscription_access = res["access_allowed"]
        if not has_subscription_access and not is_subscription_bypass_path(request.url.path):
            if not is_trial_bypass_enabled():
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="Factory subscription expired",
                )
    return user


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if getattr(current_user, "is_active", True) is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user


def normalize_role(role: str | None) -> str:
    return (role or "").strip().lower()


def check_permissions(allowed_roles: list[str]) -> Callable[[User], User]:
    allowed = {normalize_role(role) for role in allowed_roles}

    def dependency(current_user: User = Depends(get_current_active_user)) -> User:
        if normalize_role(current_user.role) not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource",
            )
        return current_user

    return dependency


def require_owner(current_user: User = Depends(get_current_user)) -> User:
    return check_permissions(["Owner", "Sub-Owner"])(current_user)


def assert_owner_delete_permission(current_user: User) -> None:
    if current_user.role != "Owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Only the Factory Owner is authorized to delete entries.",
        )


def require_owner_delete(current_user: User = Depends(get_current_user)) -> User:
    assert_owner_delete_permission(current_user)
    return current_user


# ---------------------------------------------------------------------------
# OTP Helpers
# ---------------------------------------------------------------------------

def generate_otp() -> str:
    return str(random.randint(100000, 999999))


def store_otp(db: Session, phone_number: str, otp_code: str) -> OTPStore:
    phone_number, _ = normalize_phone_number(phone_number)
    # Invalidate previous OTPs for this phone
    db.query(OTPStore).filter(
        sql_func.lower(OTPStore.phone_number) == phone_number.lower()
    ).delete(synchronize_session=False)

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRE_MINUTES)
    record = OTPStore(
        phone_number=phone_number,
        otp_code=otp_code,
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()
    return record


def verify_stored_otp(db: Session, phone_number: str, otp_code: str) -> bool:
    phone_number, _ = normalize_phone_number(phone_number)
    record = (
        db.query(OTPStore)
        .filter(sql_func.lower(OTPStore.phone_number) == phone_number.lower())
        .filter(OTPStore.otp_code == otp_code)
        .first()
    )
    if record is None:
        return False
    expires_at = record.expires_at
    if expires_at.tzinfo is not None:
        now = datetime.now(timezone.utc)
    else:
        now = datetime.utcnow()
    if now > expires_at:
        return False
    # Clean up used OTP
    db.delete(record)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Auth Endpoints
# ---------------------------------------------------------------------------

from schemas import OTPRequest, OTPVerifyRequest, TokenResponse


@router.post("/request-otp", status_code=status.HTTP_202_ACCEPTED)
def request_otp(
    payload: OTPRequest,
    db: Session = Depends(get_db),
):
    full_phone_number, _ = normalize_phone_number(payload.phone_number, payload.country_code)
    otp = generate_otp()
    store_otp(db, full_phone_number, otp)
    # MOCK: In production, integrate Twilio / AWS SNS / MSG91 here.
    print(f"[MOCK OTP] Phone: {full_phone_number} | OTP: {otp}")
    return {"message": "OTP sent successfully (mock)", "phone_number": full_phone_number}


@router.post("/verify-otp", response_model=TokenResponse)
def verify_otp(
    payload: OTPVerifyRequest,
    db: Session = Depends(get_db),
):
    full_phone_number, normalized_phone = normalize_phone_number(payload.phone_number, payload.country_code)
    if not verify_stored_otp(db, full_phone_number, payload.otp):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP",
        )

    user = get_user_by_phone(db, full_phone_number)
    if user is None:
        # Auto-register user as Owner on first verified OTP
        user = User(
            username=full_phone_number,
            phone_number=full_phone_number,
            phone_number_normalized=normalized_phone,
            password_hash=hash_password(payload.password),
            role="Owner",
            is_verified=True,
            factory_id=0,  # Temporary; will be updated at Step 1
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.is_verified = True
        if payload.password:
            user.password_hash = hash_password(payload.password)
        db.commit()
        db.refresh(user)

    token = create_access_token(
        subject=user.phone_number,
        role=user.role,
        factory_id=user.factory_id if user.factory_id > 0 else None,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        phone_number=user.phone_number,
        role=user.role,
        factory_id=user.factory_id if user.factory_id > 0 else None,
    )


@router.post("/token", response_model=TokenResponse)
@router.post("/api/auth/token", response_model=TokenResponse, include_in_schema=False)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    x_factory_id: Optional[int] = Header(default=None, alias="X-Factory-ID"),
    db: Session = Depends(get_db),
):
    print(f"AUTH DEBUG: OAuth login attempt username={form_data.username!r}")
    user = authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if x_factory_id is not None and user.factory_id not in (None, 0, x_factory_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Factory access denied",
        )

    subject = user.phone_number if user.phone_number else user.username
    token = create_access_token(
        subject=subject,
        role=user.role,
        factory_id=user.factory_id if user.factory_id > 0 else None,
        user_id=ensure_user_uuid(user, db),
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        phone_number=user.phone_number or user.username,
        role=user.role,
        factory_id=user.factory_id if user.factory_id > 0 else None,
    )


@router.post("/login", response_model=LoginResponse)
@router.post("/login/", response_model=LoginResponse, include_in_schema=False)
@public_router.post("/login", response_model=LoginResponse)
@public_router.post("/login/", response_model=LoginResponse, include_in_schema=False)
def login_json(payload: LoginRequest, db: Session = Depends(get_db)):
    print(f"AUTH DEBUG: JSON login attempt identifier={payload.identifier.strip()!r}")
    user = authenticate_user(db, payload.identifier.strip(), payload.password)
    if user is None:
        print(f"AUTH DEBUG: JSON login rejected identifier={payload.identifier.strip()!r}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    if user.factory_id is None or user.factory_id <= 0:
        print(f"AUTH DEBUG: JSON login rejected, factory missing user_id={user.id}, factory_id={user.factory_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Factory is not assigned",
        )
    return build_login_response(user, db)


@router.post("/signup", status_code=status.HTTP_201_CREATED)
@public_router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup_json(payload: SignupRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    email = payload.email.strip().lower() if payload.email else None
    phone_number, phone_number_normalized = normalize_phone_number(payload.phone_number, payload.country_code)
    full_name = payload.full_name.strip()
    factory_name = payload.factory_name.strip()

    if not phone_number or not full_name or not factory_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Full name, phone number, and factory name are required",
        )

    existing_email = get_user_by_username(db, email) if email else None
    existing_phone = get_user_by_phone(db, phone_number)
    if existing_email is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists",
        )
    if existing_phone is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phone number already exists",
        )

    unique_factory_name = factory_name
    suffix = 1
    while db.query(Factory).filter(sql_func.lower(Factory.name) == unique_factory_name.lower()).first():
        suffix += 1
        unique_factory_name = f"{factory_name} {suffix}"

    try:
        now = datetime.now(timezone.utc)
        factory = Factory(
            name=unique_factory_name,
            factory_name=factory_name,
            trial_start_date=now,
            trial_end_date=now + timedelta(days=7),
            subscription_status="trial_active",
            active_plan="basic",
            payment_status="payment_pending",
        )
        db.add(factory)
        db.flush()

        user = User(
            user_id=str(uuid4()),
            factory_id=factory.id,
            username=email or phone_number,
            phone_number=phone_number,
            phone_number_normalized=phone_number_normalized,
            full_name=full_name,
            password_hash=hash_password(payload.password),
            role="Owner",
            is_verified=True,
        )
        db.add(user)
        db.flush()
        factory.owner_id = user.id
        factory.owner_phone_number = user.phone_number
        db.commit()
        db.refresh(user)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Signup failed",
        ) from exc

    # Legacy Google Sheet task commented out (now handled by n8n sheets automation)
    # background_tasks.add_task(initialize_factory_google_sheet_task, factory.id)
    print(f"[SIGNUP] Skipping legacy google sheets task for factory_id={factory.id} - handled by n8n flow")

    return {
        "message": "Signup successful. Please log in.",
        "factory_id": user.factory_id,
        "factory_name": factory.factory_name or factory.name,
        "role": user.role,
    }


def verify_google_credential(credential: str) -> dict:
    if google_id_token is None or google_requests is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth dependencies are not installed",
        )
    google_client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not google_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GOOGLE_CLIENT_ID is not configured",
        )

    try:
        return google_id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            google_client_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        ) from exc


@router.post("/google")
def login_google(payload: GoogleLoginRequest, db: Session = Depends(get_db)):
    claims = verify_google_credential(payload.credential)
    email = str(claims.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Google account email is required",
        )

    user = get_user_by_username(db, email)
    if user is None:
        return {
            "requires_phone_number": True,
            "email": email,
            "full_name": str(claims.get("name") or email.split("@")[0]).strip(),
            "message": "Phone number is required to complete Google sign up.",
        }
    else:
        ensure_factory_trial(user.factory)
        db.commit()
        db.refresh(user)

    return build_login_response(user, db)


@router.post("/google/complete", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def complete_google_signup(payload: GoogleSignupCompleteRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    claims = verify_google_credential(payload.credential)
    email = str(claims.get("email") or "").strip().lower()
    phone_number, phone_number_normalized = normalize_phone_number(payload.phone_number, payload.country_code)
    if not email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Google account email is required")
    if get_user_by_username(db, email) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    if get_user_by_phone(db, phone_number) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phone number already exists")

    now = datetime.now(timezone.utc)
    display_name = str(claims.get("name") or email.split("@")[0]).strip()
    base_factory_name = f"{display_name} Factory"
    factory_name = base_factory_name
    suffix = 1
    while db.query(Factory).filter(sql_func.lower(Factory.name) == factory_name.lower()).first():
        suffix += 1
        factory_name = f"{base_factory_name} {suffix}"

    factory = Factory(
        name=factory_name,
        factory_name=factory_name,
        trial_start_date=now,
        trial_end_date=now + timedelta(days=7),
        subscription_status="trial_active",
        active_plan="basic",
        payment_status="payment_pending",
    )
    db.add(factory)
    db.flush()

    user = User(
        user_id=str(uuid4()),
        factory_id=factory.id,
        username=email,
        phone_number=phone_number,
        phone_number_normalized=phone_number_normalized,
        full_name=display_name,
        password_hash=hash_password(uuid4().hex),
        role="Owner",
        is_verified=True,
    )
    db.add(user)
    db.flush()
    factory.owner_id = user.id
    factory.owner_phone_number = user.phone_number
    db.commit()
    db.refresh(user)

    # Legacy Google Sheet task commented out (now handled by n8n sheets automation)
    # background_tasks.add_task(initialize_factory_google_sheet_task, factory.id)
    print(f"[GOOGLE SIGNUP] Skipping legacy google sheets task for factory_id={factory.id} - handled by n8n flow")

    return build_login_response(user, db)


@v1_router.put("/users/me/profile", response_model=AuthUserProfile)
def update_user_profile(
    payload: UserProfileUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(User.id == current_user.id)
        .filter(User.factory_id == current_user.factory_id)
        .with_for_update()
        .first()
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    full_phone_number, phone_number_normalized = normalize_phone_number(payload.phone_number, payload.country_code)
    existing_phone = (
        db.query(User)
        .filter(User.phone_number == full_phone_number)
        .filter(User.factory_id == current_user.factory_id)
        .first()
    )
    if existing_phone is not None and existing_phone.id != current_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phone number already exists")

    user.phone_number = full_phone_number
    user.phone_number_normalized = phone_number_normalized
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip() or user.full_name
    db.commit()
    db.refresh(user)
    return AuthUserProfile(
        id=current_user.id,
        user_id=current_user.user_id,
        factory_id=current_user.factory_id,
        username=current_user.username,
        phone_number=current_user.phone_number,
        full_name=current_user.full_name,
        role=current_user.role,
        factory_name=current_user.factory.factory_name or current_user.factory.name if current_user.factory else None,
        subscription_status=current_user.factory.subscription_status if current_user.factory else None,
        trial_end_date=current_user.factory.trial_end_date if current_user.factory else None,
        trial_days_remaining=trial_days_remaining(current_user.factory),
    )


class ChangePasswordRequest(BaseModel):
    current_password: Optional[str] = Field(default=None)
    new_password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)
    user_id: Optional[int] = Field(default=None)


@v1_router.patch("/profile/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    import re
    if payload.new_password != payload.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match.",
        )
    
    if len(payload.new_password) < 8 or not re.search(r"[A-Za-z]", payload.new_password) or not re.search(r"\d", payload.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long and contain both letters and numbers.",
        )
        
    if payload.user_id is not None and payload.user_id != current_user.id:
        if current_user.role != "Owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the Owner can reset other users' passwords.",
            )
        
        target_user = db.query(User).filter(User.id == payload.user_id).first()
        if target_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Staff member not found.",
            )
            
        if target_user.factory_id != current_user.factory_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only manage users in your own factory.",
            )
            
        target_user.password_hash = hash_password(payload.new_password)
        
        db.add(
            SuperAdminAuditLog(
                admin_email=current_user.username,
                action_type="CHANGE_PASSWORD",
                entity_type="user",
                entity_id=str(target_user.id),
                old_value=None,
                new_value={"password_changed": True},
                note="Owner reset staff password",
            )
        )
        db.commit()
        return {"message": "Password changed successfully."}
        
    else:
        if not payload.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is required.",
            )
            
        if not verify_password(payload.current_password, current_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect.",
            )
            
        current_user.password_hash = hash_password(payload.new_password)
        
        db.add(
            SuperAdminAuditLog(
                admin_email=current_user.username,
                action_type="CHANGE_PASSWORD",
                entity_type="user",
                entity_id=str(current_user.id),
                old_value=None,
                new_value={"password_changed": True},
                note="User changed password",
            )
        )
        db.commit()
        return {"message": "Password changed successfully."}


from schemas import UserSubscriptionResponse

@v1_router.get("/users/me/subscription", response_model=UserSubscriptionResponse)
def get_user_subscription(
    response: Response,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    set_no_store_headers(response)
    factory = db.query(Factory).filter(Factory.id == current_user.factory_id).populate_existing().first()
    res = get_effective_subscription(db, current_user.factory_id)
    
    # Query fresh user data to get accurate last_login_at
    fresh_user = db.query(User).filter(User.id == current_user.id).first()
    last_login = getattr(fresh_user, "last_login_at", None)
    now = res["server_time"]
    trial_start = getattr(factory, "trial_start_date", None)
    trial_end = res["trial_end_date"]
    if trial_start is not None and trial_start.tzinfo is None:
        trial_start = trial_start.replace(tzinfo=timezone.utc)
    is_within_trial_bracket = bool(
        trial_end is not None
        and trial_end >= now
        and (trial_start is None or trial_start <= now)
        and res["effective_status"] == "trial_active"
    )
    is_trial = res["plan_name"] == "Free Trial" or is_within_trial_bracket
    
    return UserSubscriptionResponse(
        active_plan=res["active_plan"],
        plan_name=res["plan_name"],
        plan_expires_at=res["plan_expires_at"],
        trial_end_date=res["trial_end_date"],
        subscription_end_date=res["subscription_end_date"],
        days_left=res["days_left"],
        last_login=last_login,
        server_time=res["server_time"],
        subscription_status=res["subscription_status"],
        billing_cycle=res["billing_cycle"],
        payment_status=res["payment_status"],
        is_manual_override=res["is_manual_override"],
        is_trial=is_trial,
        access_allowed=res["access_allowed"],
        raw_active_plan=res["raw_active_plan"],
        raw_plan_name=res["raw_plan_name"],
        raw_subscription_end_date=res["raw_subscription_end_date"],
        raw_plan_expires_at=res["raw_plan_expires_at"],
        raw_trial_end_date=res["raw_trial_end_date"],
        effective_plan=res["effective_plan"],
        effective_status=res["effective_status"],
        effective_expires_at=res["effective_expires_at"]
    )


import hashlib
import hmac
import time

def generate_signed_portal_token(customer_id: int, factory_id: int, validity_seconds: int = 2592000) -> str:
    """Generates a secure time-bound signed token valid for 30 days by default."""
    expires_at = int(time.time()) + validity_seconds
    secret = get_jwt_secret_key().encode()
    message = f"portal:{customer_id}:{factory_id}:{expires_at}".encode()
    signature = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return f"{customer_id}.{factory_id}.{expires_at}.{signature}"


def decode_signed_portal_token(token: str) -> tuple[int, int] | None:
    """Returns (customer_id, factory_id) when a signed portal token is valid."""
    try:
        customer_id_str, factory_id_str, expires_at_str, signature = token.split(".")
        customer_id = int(customer_id_str)
        factory_id = int(factory_id_str)
        expires_at = int(expires_at_str)
        if time.time() > expires_at:
            return None
        secret = get_jwt_secret_key().encode()
        expected_message = f"portal:{customer_id}:{factory_id}:{expires_at}".encode()
        expected_signature = hmac.new(secret, expected_message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            return None
        return customer_id, factory_id
    except Exception:
        return None

def verify_signed_portal_token(token: str, customer_id: int, factory_id: int) -> bool:
    """Verifies a cryptographically signed time-bound token."""
    decoded = decode_signed_portal_token(token)
    if decoded is None:
        return False
    return decoded == (int(customer_id), int(factory_id))


def generate_storefront_session_token(customer_id: int, store_token: str, validity_seconds: int = 7200) -> str:
    """Generates a secure cryptographically signed storefront session token."""
    import base64
    expires_at = int(time.time()) + validity_seconds
    secret = get_jwt_secret_key().encode()
    clean_token = store_token.strip()
    message = f"storefront_session:{customer_id}:{clean_token}:{expires_at}".encode()
    signature = hmac.new(secret, message, hashlib.sha256).hexdigest()
    b64_token = base64.b64encode(clean_token.encode()).decode()
    return f"{customer_id}.{expires_at}.{b64_token}.{signature}"


def decode_storefront_session_token(token: str) -> tuple[int, str] | None:
    """Returns (customer_id, store_token) if the storefront session token is valid."""
    import base64
    try:
        customer_id_str, expires_at_str, b64_token, signature = token.split(".", 3)
        customer_id = int(customer_id_str)
        expires_at = int(expires_at_str)
        if time.time() > expires_at:
            return None
        store_token = base64.b64decode(b64_token.encode()).decode()
        secret = get_jwt_secret_key().encode()
        expected_message = f"storefront_session:{customer_id}:{store_token}:{expires_at}".encode()
        expected_signature = hmac.new(secret, expected_message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            return None
        return customer_id, store_token
    except Exception:
        return None

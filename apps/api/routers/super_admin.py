import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import uuid4
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from auth import JWT_ALGORITHM, hash_password, normalize_phone_number, verify_password
from db import get_db
from models import (
    AdvancePayment,
    AppUsageLog,
    AttendanceLog,
    BlankStock,
    BottomStock,
    BoxStock,
    CostingMaster,
    CostingOutputMaster,
    Customer,
    CustomerActivity,
    CustomPlanEnquiry,
    DailyProduction,
    DailySale,
    DemoBookingRequest,
    Employee,
    ExpenseLog,
    Factory,
    FactoryAutomationSheet,
    FactoryExpense,
    FactoryInventory,
    FactorySettings,
    FinalProductStock,
    FinishedGoodsStock,
    HisabSettlement,
    Inventory,
    Machine,
    MachineOnboarding,
    MachineTemplate,
    MaterialYield,
    Order,
    OrderItem,
    PackagingMetrics,
    PackagingProfile,
    Payment,
    PlasticStock,
    PolybagStock,
    ProductionLog,
    RawMaterial,
    RawMaterialMetrics,
    SalesInvoice,
    SubscriptionPayment,
    SuperAdminAuditLog,
    TokenUsageLog,
    User,
    Worker,
)


router = APIRouter(prefix="/api/super-admin", tags=["super-admin"])
admin_router = APIRouter(prefix="/api/admin", tags=["super-admin"])
bearer = HTTPBearer(auto_error=False)
SUPER_ADMIN_TOKEN_EXPIRE_MINUTES = int(os.getenv("SUPER_ADMIN_TOKEN_EXPIRE_MINUTES") or "720")
BULK_DELETE_CONFIRMATION = "DELETE SELECTED FACTORIES"
SINGLE_DELETE_CONFIRMATION = "DELETE FACTORY"


_super_admin_failed_attempts = {}
_super_admin_lockouts = {}

MFA_FILE = Path("storage/super_admin_mfa.json")

def load_mfa_settings() -> dict:
    if not MFA_FILE.exists():
        return {"mfa_enabled": False, "mfa_secret": None, "pending_secret": None, "password_hash": None}
    try:
        with open(MFA_FILE, "r") as f:
            data = json.load(f)
            for k in ["mfa_enabled", "mfa_secret", "pending_secret", "password_hash"]:
                if k not in data:
                    data[k] = None
            return data
    except Exception:
        return {"mfa_enabled": False, "mfa_secret": None, "pending_secret": None, "password_hash": None}

def save_mfa_settings(settings: dict):
    MFA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MFA_FILE, "w") as f:
        json.dump(settings, f, indent=2)

def generate_base32_secret() -> str:
    random_bytes = secrets.token_bytes(20)
    return base64.b32encode(random_bytes).decode().rstrip("=")

def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    if not secret or not code:
        return False
    secret = secret.strip().replace(" ", "")
    missing_padding = len(secret) % 8
    if missing_padding:
        secret += "=" * (8 - missing_padding)
    try:
        key = base64.b32decode(secret, casefold=True)
    except Exception:
        return False
        
    now_intervals = int(time.time() / 30)
    for i in range(-window, window + 1):
        intervals = now_intervals + i
        msg = struct.pack(">Q", intervals)
        hs = hmac.new(key, msg, hashlib.sha1).digest()
        offset = hs[-1] & 0x0f
        binary = struct.unpack(">I", hs[offset:offset+4])[0] & 0x7fffffff
        val = binary % 1000000
        if str(val).zfill(6) == code.strip():
            return True
    return False

def _record_failed_attempt(ip: str):
    now = time.time()
    attempts = _super_admin_failed_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < 900]
    attempts.append(now)
    _super_admin_failed_attempts[ip] = attempts
    if len(attempts) >= 5:
        _super_admin_lockouts[ip] = now + 900


class SuperAdminLoginRequest(BaseModel):
    email: str
    password: str
    totp_code: Optional[str] = None


class SuperAdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str
    role: str = "super_admin"
    mfa_required: bool = False


class SuperAdminChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class MFAVerifyRequest(BaseModel):
    code: str


class SuperAdminMeResponse(BaseModel):
    email: str
    role: str = "super_admin"


class FactorySheetOverviewResponse(BaseModel):
    factory_id: int
    factory_name: str
    registered_owner_email: Optional[str] = None
    phone_number: Optional[str] = None
    google_spreadsheet_id: Optional[str] = None
    created_at: Optional[datetime] = None


class FactorySheetUpdateRequest(BaseModel):
    google_spreadsheet_id: str = Field(..., min_length=1, max_length=500)


class FactoryCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    factory_name: Optional[str] = None
    owner_id: Optional[int] = None
    is_active: bool = True
    address: Optional[str] = None
    admin_note: Optional[str] = None


class FactoryPatchRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    factory_name: Optional[str] = None
    owner_id: Optional[int] = None
    is_active: Optional[bool] = None
    address: Optional[str] = None
    admin_note: Optional[str] = None


class OwnerPatchRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[str] = None


class OwnerStatusRequest(BaseModel):
    is_active: bool
    note: Optional[str] = None


class OwnerCreateRequest(BaseModel):
    owner_name: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = None
    country_code: str = "+91"
    phone_number: Optional[str] = None
    password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)
    factory_name: str = Field(..., min_length=1, max_length=255)
    factory_address: Optional[str] = None
    initial_subscription_plan: str = "trial"
    subscription_status: str = "trial_active"
    payment_status: str = "free"
    billing_cycle: Optional[str] = None
    subscription_start_date: Optional[datetime] = None
    subscription_end_date: Optional[datetime] = None
    usage_limit: Optional[int] = None
    token_limit: Optional[int] = None
    notes: Optional[str] = None


class SubscriptionPatchRequest(BaseModel):
    active_plan: Optional[str] = None
    plan_name: Optional[str] = None
    subscription_status: Optional[str] = None
    billing_cycle: Optional[str] = None
    payment_status: Optional[str] = None
    trial_start_date: Optional[datetime] = None
    trial_end_date: Optional[datetime] = None
    subscription_start_date: Optional[datetime] = None
    subscription_end_date: Optional[datetime] = None
    plan_expires_at: Optional[datetime] = None
    usage_limit: Optional[int] = None
    token_limit: Optional[int] = None
    admin_note: Optional[str] = None
    note: Optional[str] = None


class ManualSubscriptionAdjustment(BaseModel):
    factory_id: int
    plan_name: str = "premium"
    subscription_status: str = "active"
    payment_status: str = "paid"
    billing_cycle: Optional[str] = "monthly"
    subscription_end_date: datetime
    subscription_start_date: Optional[datetime] = None
    usage_limit: Optional[int] = None
    token_limit: Optional[int] = None
    admin_note: Optional[str] = None
    note: Optional[str] = None


class OwnerSubscriptionRequest(SubscriptionPatchRequest):
    pass


class PaymentPatchRequest(BaseModel):
    payment_status: Optional[str] = None
    amount_paise: Optional[int] = None
    provider_payment_id: Optional[str] = None
    note: Optional[str] = None


class ManualPaymentEntry(BaseModel):
    factory_id: int
    plan_code: str = "manual"
    billing_cycle: str = "monthly"
    amount_paise: int = 0
    payment_status: str = "paid"
    provider_payment_id: Optional[str] = None
    subscription_start_date: Optional[datetime] = None
    subscription_end_date: datetime
    note: Optional[str] = None


class BulkFactoryIdsRequest(BaseModel):
    factory_ids: list[int] = Field(..., min_length=1)


class BulkDeleteRequest(BulkFactoryIdsRequest):
    confirmation: str


class SingleFactoryDeleteRequest(BaseModel):
    confirmation: str


def apply_factory_subscription_update(factory: Factory, data: dict) -> None:
    """Keep the Factory subscription columns synchronized for partial admin edits."""
    for field, value in data.items():
        setattr(factory, field, value)

    if "active_plan" in data and "plan_name" not in data:
        factory.plan_name = data["active_plan"]
    elif "plan_name" in data and "active_plan" not in data:
        factory.active_plan = data["plan_name"]

    if "subscription_start_date" in data:
        factory.subscription_start = data["subscription_start_date"]

    if "subscription_end_date" in data:
        factory.subscription_end = data["subscription_end_date"]
        if "plan_expires_at" not in data:
            factory.plan_expires_at = data["subscription_end_date"]
    elif "plan_expires_at" in data:
        factory.subscription_end_date = data["plan_expires_at"]
        factory.subscription_end = data["plan_expires_at"]


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


def request_client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def client_ip_aliases(client_ip: str) -> list[str]:
    aliases = [client_ip, "testclient", "testserver", "127.0.0.1"]
    return list(dict.fromkeys(aliases))


def bulk_delete_enabled() -> bool:
    return os.getenv("ENABLE_SUPER_ADMIN_BULK_DELETE", "").strip().lower() in {"1", "true", "yes", "on"}


def factory_delete_enabled() -> bool:
    return os.getenv("ENABLE_SUPER_ADMIN_FACTORY_DELETE", "").strip().lower() in {"1", "true", "yes", "on"}


def bulk_delete_max() -> int:
    try:
        return max(1, int(os.getenv("SUPER_ADMIN_BULK_DELETE_MAX") or "50"))
    except ValueError:
        return 50


def validate_bulk_factory_ids(db: Session, factory_ids: list[int]) -> list[Factory]:
    unique_ids = list(dict.fromkeys(factory_ids))
    if not unique_ids:
        raise HTTPException(status_code=422, detail="factory_ids cannot be empty")
    if len(unique_ids) > bulk_delete_max():
        raise HTTPException(status_code=422, detail=f"You can delete up to {bulk_delete_max()} factories at a time")
    factories = db.query(Factory).filter(Factory.id.in_(unique_ids)).all()
    found_ids = {factory.id for factory in factories}
    missing = [factory_id for factory_id in unique_ids if factory_id not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"Factories not found: {missing}")
    return sorted(factories, key=lambda factory: unique_ids.index(factory.id))


def get_super_admin_email() -> str:
    email = os.getenv("SUPER_ADMIN_EMAIL", "").strip().lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Super admin is not configured")
    return email


def get_super_admin_secret() -> str:
    secret = os.getenv("SUPER_ADMIN_JWT_SECRET", "")
    if not secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Super admin JWT is not configured")
    return secret


def verify_super_admin_password(password: str) -> bool:
    password_hash = os.getenv("SUPER_ADMIN_PASSWORD_HASH", "").strip()
    if not password_hash:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Super admin password is not configured")
    return verify_password(password, password_hash)


def create_super_admin_token(email: str) -> str:
    payload = {
        "sub": email.lower(),
        "role": "super_admin",
        "scope": "super_admin",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=SUPER_ADMIN_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, get_super_admin_secret(), algorithm=JWT_ALGORITHM)


def require_super_admin(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Super admin authentication required")
    try:
        payload = jwt.decode(credentials.credentials, get_super_admin_secret(), algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid super admin token")
    email = (payload.get("sub") or "").lower()
    if payload.get("role") != "super_admin" or payload.get("scope") != "super_admin" or email != get_super_admin_email():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")
    return email


def audit(
    db: Session,
    request: Request,
    admin_email: str,
    action_type: str,
    entity_type: str,
    entity_id: Any,
    old_value: Optional[dict] = None,
    new_value: Optional[dict] = None,
    note: Optional[str] = None,
) -> None:
    entity_id_text = str(entity_id) if entity_id is not None else None
    if entity_id_text and len(entity_id_text) > 100:
        entity_id_text = f"{entity_id_text[:97]}..."
    db.add(
        SuperAdminAuditLog(
            admin_email=admin_email,
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id_text,
            old_value=json_safe(old_value),
            new_value=json_safe(new_value),
            note=note,
            ip_address=request.client.host if request.client else None,
        )
    )


def json_safe(value: Any) -> Any:
    from datetime import date, datetime as dt_class
    from uuid import UUID
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, (dt_class, date)) or (hasattr(value, "isoformat") and callable(value.isoformat)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return str(value)
    except Exception:
        return None


def owner_query(db: Session):
    return db.query(User).filter(func.lower(User.role) == "owner")


def user_public(user: Optional[User]) -> Optional[dict]:
    if not user:
        return None
    return {
        "id": user.id,
        "user_id": user.user_id,
        "full_name": user.full_name,
        "username": user.username,
        "email": user.email,
        "phone_number": user.phone_number,
        "role": user.role,
        "factory_id": user.factory_id,
        "is_active": user.is_active,
        "last_login_at": user.last_login_at,
    }


def usage_summary(db: Session, factory_id: int, owner_id: Optional[int] = None) -> dict:
    app_query = db.query(AppUsageLog).filter(AppUsageLog.factory_id == factory_id)
    token_query = db.query(TokenUsageLog).filter(TokenUsageLog.factory_id == factory_id)
    if owner_id:
        app_query = app_query.filter(AppUsageLog.user_id == owner_id)
        token_query = token_query.filter(TokenUsageLog.user_id == owner_id)
    last_app = app_query.order_by(AppUsageLog.created_at.desc()).first()
    total_tokens = token_query.with_entities(func.coalesce(func.sum(TokenUsageLog.total_tokens), 0)).scalar() or 0
    monthly_tokens = (
        token_query.filter(TokenUsageLog.created_at >= datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0))
        .with_entities(func.coalesce(func.sum(TokenUsageLog.total_tokens), 0))
        .scalar()
        or 0
    )
    return {
        "app_usage_count": app_query.count(),
        "last_active_at": last_app.created_at if last_app else None,
        "total_token_usage": int(total_tokens),
        "monthly_token_usage": int(monthly_tokens),
    }


def factory_summary(db: Session, factory: Factory) -> dict:
    owner = db.query(User).filter(User.id == factory.owner_id).first() if factory.owner_id else None
    if owner is None:
        owner = db.query(User).filter(User.factory_id == factory.id, func.lower(User.role) == "owner").first()
    usage = usage_summary(db, factory.id, owner.id if owner else None)
    return {
        "id": factory.id,
        "name": factory.name,
        "factory_name": factory.factory_name,
        "owner": user_public(owner),
        "owner_id": factory.owner_id,
        "owner_phone_number": factory.owner_phone_number,
        "created_at": factory.created_at,
        "is_active": factory.is_active,
        "address": factory.address,
        "active_plan": factory.active_plan,
        "plan_name": factory.plan_name,
        "subscription_status": factory.subscription_status,
        "payment_status": factory.payment_status,
        "billing_cycle": factory.billing_cycle,
        "trial_start_date": factory.trial_start_date,
        "trial_end_date": factory.trial_end_date,
        "subscription_start_date": factory.subscription_start_date,
        "subscription_end_date": factory.subscription_end_date,
        "plan_expires_at": factory.plan_expires_at,
        "usage_limit": factory.usage_limit,
        "token_limit": factory.token_limit,
        "admin_note": factory.admin_note,
        **usage,
    }


def resolve_factory_owner(db: Session, factory: Factory) -> Optional[User]:
    if factory.owner_id:
        owner = db.query(User).filter(User.id == factory.owner_id).first()
        if owner is not None:
            return owner
    return db.query(User).filter(User.factory_id == factory.id, func.lower(User.role) == "owner").first()


def resolve_factory_google_sheet_id(db: Session, factory: Factory) -> Optional[str]:
    if factory.google_sheet_id:
        return factory.google_sheet_id
    sheet = (
        db.query(FactoryAutomationSheet)
        .filter(FactoryAutomationSheet.factory_id == factory.id)
        .filter(FactoryAutomationSheet.is_active.is_(True))
        .order_by(FactoryAutomationSheet.updated_at.desc(), FactoryAutomationSheet.created_at.desc())
        .first()
    )
    return sheet.google_sheet_id if sheet else None


def parse_google_spreadsheet_id(value: str) -> str:
    candidate = (value or "").strip()
    if not candidate:
        raise HTTPException(status_code=422, detail="google_spreadsheet_id is required")
    if "/spreadsheets/d/" in candidate:
        candidate = candidate.split("/spreadsheets/d/", 1)[1].split("/", 1)[0]
    candidate = candidate.split("?", 1)[0].split("#", 1)[0].strip()
    if not candidate:
        raise HTTPException(status_code=422, detail="Valid Google Spreadsheet ID is required")
    return candidate


def factory_sheet_overview(db: Session, factory: Factory) -> FactorySheetOverviewResponse:
    owner = resolve_factory_owner(db, factory)
    return FactorySheetOverviewResponse(
        factory_id=factory.id,
        factory_name=factory.factory_name or factory.name,
        registered_owner_email=owner.email if owner else None,
        phone_number=(owner.phone_number if owner else None) or factory.owner_phone_number,
        google_spreadsheet_id=resolve_factory_google_sheet_id(db, factory),
        created_at=factory.created_at,
    )


def factory_counts(db: Session, factory_id: int) -> dict:
    return {
        "production_records_count": db.query(DailyProduction).filter(DailyProduction.factory_id == factory_id).count(),
        "inventory_records_count": db.query(FactoryInventory).filter(FactoryInventory.factory_id == factory_id).count(),
        "sales_records_count": db.query(DailySale).filter(DailySale.factory_id == factory_id).count(),
        "expenses_records_count": db.query(FactoryExpense).filter(FactoryExpense.factory_id == factory_id).count(),
        "payments_records_count": db.query(Payment).filter(Payment.factory_id == factory_id).count(),
        "staff_count": db.query(User).filter(User.factory_id == factory_id).count(),
        "employee_count": db.query(Employee).filter(Employee.factory_id == factory_id).count(),
        "bottom_stock_count": db.query(BottomStock).filter(BottomStock.factory_id == factory_id).count(),
        "box_stock_count": db.query(BoxStock).filter(BoxStock.factory_id == factory_id).count(),
    }


CASCADE_MODEL_ORDER = [
    Payment,
    DailySale,
    SalesInvoice,
    OrderItem,
    Order,
    CustomerActivity,
    Customer,
    ProductionLog,
    FinishedGoodsStock,
    CostingOutputMaster,
    PackagingProfile,
    PackagingMetrics,
    RawMaterialMetrics,
    RawMaterial,
    Inventory,
    FactoryInventory,
    FactoryExpense,
    ExpenseLog,
    AttendanceLog,
    AdvancePayment,
    HisabSettlement,
    DailyProduction,
    Employee,
    Worker,
    MaterialYield,
    CostingMaster,
    FactorySettings,
    MachineOnboarding,
    Machine,
    BlankStock,
    BottomStock,
    BoxStock,
    PlasticStock,
    PolybagStock,
    FinalProductStock,
    SubscriptionPayment,
    CustomPlanEnquiry,
    DemoBookingRequest,
    AppUsageLog,
    TokenUsageLog,
]


COUNT_LABELS = {
    DailyProduction: "production",
    ProductionLog: "production",
    FactoryInventory: "inventory",
    Inventory: "inventory",
    RawMaterial: "inventory",
    DailySale: "sales",
    SalesInvoice: "sales",
    Order: "sales",
    OrderItem: "sales",
    FactoryExpense: "expenses",
    ExpenseLog: "expenses",
    Payment: "payments",
    SubscriptionPayment: "subscriptions",
    User: "staff",
    Employee: "staff",
    Worker: "staff",
    AttendanceLog: "attendance",
    Customer: "customers",
    CustomerActivity: "customers",
    Machine: "machines",
    MachineOnboarding: "machines",
    PackagingProfile: "products",
    FinishedGoodsStock: "products",
    FinalProductStock: "products",
    AppUsageLog: "app_usage_logs",
    TokenUsageLog: "token_usage_logs",
}


PREVIEW_COUNT_KEYS = [
    "production",
    "inventory",
    "sales",
    "expenses",
    "payments",
    "staff",
    "attendance",
    "customers",
    "machines",
    "products",
    "subscriptions",
    "app_usage_logs",
    "token_usage_logs",
    "audit_logs",
]


def empty_delete_counts() -> dict:
    counts = {key: 0 for key in PREVIEW_COUNT_KEYS}
    counts.update({"owners": 0, "workers": 0, "usage_logs": 0, "token_logs": 0})
    return counts


def add_count(counts: dict, key: str, value: int) -> None:
    counts[key] = counts.get(key, 0) + int(value or 0)


def resolve_delete_owner_action(db: Session, factory: Factory, owner: Optional[User]) -> tuple[str, list[str]]:
    if owner is None:
        return "none", ["No owner is linked to this factory."]
    if owner.factory_id == factory.id:
        return "delete_owner_because_only_factory", ["Owner login will be deleted because users belong to exactly one factory in the current auth model."]
    return "kept_multiple_factories", ["Owner account is linked outside this factory and will be kept."]


def factory_delete_preview(db: Session, factory: Factory) -> dict:
    counts = empty_delete_counts()
    user_ids = [row.id for row in db.query(User).filter(User.factory_id == factory.id).all()]
    for model in CASCADE_MODEL_ORDER:
        key = COUNT_LABELS.get(model)
        if key:
            add_count(counts, key, db.query(model).filter(model.factory_id == factory.id).count())
    add_count(counts, "staff", db.query(User).filter(User.factory_id == factory.id).count())
    add_count(counts, "owners", db.query(User).filter(User.factory_id == factory.id, func.lower(User.role) == "owner").count())
    add_count(counts, "workers", db.query(Worker).filter(Worker.factory_id == factory.id).count())
    counts["usage_logs"] = counts["app_usage_logs"]
    counts["token_logs"] = counts["token_usage_logs"]
    if user_ids:
        add_count(counts, "machines", db.query(MachineTemplate).filter(MachineTemplate.creator_id.in_(user_ids)).count())
    add_count(counts, "audit_logs", db.query(SuperAdminAuditLog).filter(SuperAdminAuditLog.entity_type == "factory", SuperAdminAuditLog.entity_id == str(factory.id)).count())
    owner = db.query(User).filter(User.id == factory.owner_id).first() if factory.owner_id else None
    if owner is None:
        owner = db.query(User).filter(User.factory_id == factory.id, func.lower(User.role) == "owner").first()
    owner_action, warnings = resolve_delete_owner_action(db, factory, owner)
    return {
        "factory_id": factory.id,
        "factory_name": factory.factory_name or factory.name,
        "owner": {
            "id": owner.id if owner else None,
            "name": owner.full_name if owner else None,
            "email": owner.email if owner else None,
            "phone": owner.phone_number if owner else None,
            "action": owner_action,
        },
        "owner_name": owner.full_name if owner else None,
        "owner_email": owner.email if owner else None,
        "owner_phone": owner.phone_number if owner else None,
        "owner_action": owner_action,
        "record_counts": counts,
        "warnings": warnings,
    }


def combine_preview_counts(previews: list[dict]) -> dict:
    totals = {"factories": len(previews), **empty_delete_counts()}
    for preview in previews:
        for key, value in preview["record_counts"].items():
            add_count(totals, key, value)
    return totals


def delete_factory_cascade(db: Session, factory_id: int | Factory, admin_user: Optional[str] = None, mode: str = "single") -> dict:
    factory = factory_id if isinstance(factory_id, Factory) else db.query(Factory).filter(Factory.id == factory_id).first()
    if factory is None:
        raise HTTPException(status_code=404, detail="Factory not found")
    preview = factory_delete_preview(db, factory)
    deleted_counts = {key: value for key, value in preview["record_counts"].items() if key != "audit_logs"}

    user_ids = [row.id for row in db.query(User).filter(User.factory_id == factory.id).all()]
    if user_ids:
        db.query(MachineTemplate).filter(MachineTemplate.creator_id.in_(user_ids)).delete(synchronize_session=False)

    for model in CASCADE_MODEL_ORDER:
        db.query(model).filter(model.factory_id == factory.id).delete(synchronize_session=False)

    factory.owner_id = None
    factory.owner_phone_number = None
    db.flush()
    db.query(User).filter(User.factory_id == factory.id).delete(synchronize_session=False)
    db.delete(factory)
    return {
        "factory_id": preview["factory_id"],
        "owner_action": preview["owner_action"],
        "preview": preview,
        "deleted_counts": deleted_counts,
        "mode": mode,
        "admin_user": admin_user,
    }


@router.post("/login", response_model=SuperAdminLoginResponse)
def login(
    payload: SuperAdminLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    no_store(response)
    email = payload.email.strip().lower()
    client_ip = request_client_ip(request)
    client_ip_keys = client_ip_aliases(client_ip)

    def audit_login_event(action_type: str, entity_id: Any, note: Optional[str]) -> None:
        audit(db, request, email, action_type, "super_admin", entity_id, None, None, note)
        db.commit()
    
    # 1. Rate Limiting Check
    from main import is_rate_limited
    if any(
        is_rate_limited(f"rate_limit:super_admin_login:{ip_key}", limit=10, window_seconds=60)
        for ip_key in client_ip_keys
    ):
        # Log failure due to rate limit
        audit_login_event("login_failure_rate_limited", email, "Super admin login rate limit exceeded.")
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts. Please try again in a minute.")
        
    # 2. Lockout Check
    lockout_until = max((_super_admin_lockouts.get(ip_key, 0) for ip_key in client_ip_keys), default=0)
    now = time.time()
    if now < lockout_until:
        remaining = int(lockout_until - now)
        audit_login_event("login_failure_locked_out", email, "Super admin login blocked under active lockout.")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"IP locked out due to multiple failures. Try again in {remaining} seconds."
        )

    # 3. Check credentials
    settings = load_mfa_settings()
    stored_hash = settings.get("password_hash")
    
    if email != get_super_admin_email():
        _record_failed_attempt(client_ip)
        audit_login_event("login_failure_invalid_email", email, "Invalid super admin email.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid super admin credentials")
        
    if stored_hash:
        valid_password = verify_password(payload.password, stored_hash)
    else:
        try:
            valid_password = verify_super_admin_password(payload.password)
        except Exception as exc:
            audit_login_event("login_failure_config_error", email, "Super admin password configuration error.")
            raise
            
    if not valid_password:
        _record_failed_attempt(client_ip)
        audit_login_event("login_failure_invalid_password", email, "Invalid password.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid super admin credentials")

    # 4. MFA check
    if settings.get("mfa_enabled"):
        if not payload.totp_code:
            audit_login_event("login_mfa_required", email, "MFA code verification prompt sent.")
            return SuperAdminLoginResponse(
                access_token="",
                email=email,
                mfa_required=True
            )
        
        if not verify_totp(settings.get("mfa_secret"), payload.totp_code):
            _record_failed_attempt(client_ip)
            audit_login_event("login_failure_invalid_mfa", email, "Invalid MFA code.")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")

    # 5. Success! Clear limits
    for ip_key in client_ip_keys:
        _super_admin_failed_attempts.pop(ip_key, None)
        _super_admin_lockouts.pop(ip_key, None)
    
    audit_login_event("login_success", email, "Super admin logged in successfully.")
    
    return SuperAdminLoginResponse(
        access_token=create_super_admin_token(email),
        email=email,
        mfa_required=False
    )


@router.post("/change-password")
def change_password(
    payload: SuperAdminChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_email: str = Depends(require_super_admin)
):
    settings = load_mfa_settings()
    stored_hash = settings.get("password_hash")
    
    if stored_hash:
        valid_old = verify_password(payload.old_password, stored_hash)
    else:
        valid_old = verify_super_admin_password(payload.old_password)
        
    if not valid_old:
        raise HTTPException(status_code=400, detail="Invalid old password")
        
    new_hash = hash_password(payload.new_password)
    settings["password_hash"] = new_hash
    save_mfa_settings(settings)

    audit(db, request, admin_email, "super_admin_password_change", "super_admin", admin_email, None, None, "Super Admin password changed successfully.")
    db.commit()  # Persist the audit log – previously missing
    return {"status": "success", "message": "Password changed successfully."}


@router.post("/mfa/setup")
def setup_mfa(admin_email: str = Depends(require_super_admin)):
    settings = load_mfa_settings()
    secret = generate_base32_secret()
    settings["pending_secret"] = secret
    save_mfa_settings(settings)
    
    provisioning_uri = f"otpauth://totp/MunshiAI:{admin_email}?secret={secret}&issuer=MunshiAI"
    return {
        "secret": secret,
        "provisioning_uri": provisioning_uri
    }


@router.post("/mfa/enable")
def enable_mfa(
    payload: MFAVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_email: str = Depends(require_super_admin)
):
    settings = load_mfa_settings()
    secret = settings.get("pending_secret")
    if not secret:
        raise HTTPException(status_code=400, detail="MFA setup has not been initiated. Call /mfa/setup first.")
    
    if not verify_totp(secret, payload.code):
        audit(db, request, admin_email, "mfa_enable_failure", "mfa", None, note="Invalid verification code entered.")
        raise HTTPException(status_code=400, detail="Invalid verification code")
    
    settings["mfa_secret"] = secret
    settings["mfa_enabled"] = True
    settings["pending_secret"] = None
    save_mfa_settings(settings)
    
    audit(db, request, admin_email, "mfa_enabled", "mfa", None, note="Super admin MFA successfully enabled.")
    return {"status": "success", "message": "MFA has been successfully enabled."}


@router.post("/mfa/disable")
def disable_mfa(
    payload: MFAVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_email: str = Depends(require_super_admin)
):
    settings = load_mfa_settings()
    if not settings.get("mfa_enabled"):
        raise HTTPException(status_code=400, detail="MFA is not enabled.")
    
    if not verify_totp(settings.get("mfa_secret"), payload.code):
        audit(db, request, admin_email, "mfa_disable_failure", "mfa", None, note="Invalid code entered during disable attempt.")
        raise HTTPException(status_code=400, detail="Invalid code")
    
    settings["mfa_secret"] = None
    settings["mfa_enabled"] = False
    settings["pending_secret"] = None
    save_mfa_settings(settings)
    
    audit(db, request, admin_email, "mfa_disabled", "mfa", None, note="Super admin MFA successfully disabled.")
    return {"status": "success", "message": "MFA has been disabled."}


@router.get("/settings")
def settings(response: Response, admin_email: str = Depends(require_super_admin)):
    no_store(response)
    return {
        "bulk_delete_enabled": bulk_delete_enabled(),
        "factory_delete_enabled": factory_delete_enabled(),
        "bulk_delete_max": bulk_delete_max(),
    }


@router.get("/me", response_model=SuperAdminMeResponse)
def me(response: Response, admin_email: str = Depends(require_super_admin)):
    no_store(response)
    return SuperAdminMeResponse(email=admin_email)


@router.get("/dashboard")
def dashboard(response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    total_factories = db.query(Factory).count()
    total_owners = owner_query(db).count()
    paid_statuses = {"paid", "manual_override", "success", "completed"}
    total_usage_tokens = db.query(func.coalesce(func.sum(TokenUsageLog.total_tokens), 0)).scalar() or 0
    return {
        "total_factories": total_factories,
        "total_factory_owners": total_owners,
        "free_users_count": db.query(Factory).filter(or_(Factory.plan_name.ilike("%free%"), Factory.active_plan.ilike("%free%"))).count(),
        "paid_users_count": db.query(Factory).filter(Factory.payment_status.in_(paid_statuses)).count(),
        "trial_users_count": db.query(Factory).filter(Factory.subscription_status.in_(["trial", "trial_active"])).count(),
        "expired_users_count": db.query(Factory).filter(Factory.subscription_status.in_(["expired", "trial_expired", "cancelled"])).count(),
        "active_subscriptions": db.query(Factory).filter(Factory.subscription_status == "active").count(),
        "pending_payments": db.query(Factory).filter(Factory.payment_status.in_(["payment_pending", "pending", "unpaid"])).count(),
        "total_usage_tokens": int(total_usage_tokens),
        "recent_signups": [user_public(row) for row in owner_query(db).order_by(User.id.desc()).limit(10).all()],
        "recent_payments": [
            {
                "id": p.id,
                "factory_id": p.factory_id,
                "plan_code": p.plan_code,
                "amount_paise": p.amount_paise,
                "payment_status": p.payment_status,
                "created_at": p.created_at,
            }
            for p in db.query(SubscriptionPayment).order_by(SubscriptionPayment.created_at.desc()).limit(10).all()
        ],
    }


@router.get("/overview", response_model=list[FactorySheetOverviewResponse])
@admin_router.get("/overview", response_model=list[FactorySheetOverviewResponse])
def admin_overview(response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    factories = (
        db.query(Factory)
        .filter(Factory.is_active.is_(True))
        .order_by(Factory.id.asc())
        .limit(1000)
        .all()
    )
    return [factory_sheet_overview(db, factory) for factory in factories]


@admin_router.post("/factory/{factory_id}/update-sheet", response_model=FactorySheetOverviewResponse)
def update_factory_google_sheet(
    factory_id: int,
    payload: FactorySheetUpdateRequest,
    response: Response,
    db: Session = Depends(get_db),
    admin_email: str = Depends(require_super_admin),
):
    no_store(response)
    factory = db.query(Factory).filter(Factory.id == factory_id).first()
    if factory is None:
        raise HTTPException(status_code=404, detail="Factory not found")

    factory.google_sheet_id = parse_google_spreadsheet_id(payload.google_spreadsheet_id)
    db.commit()
    db.refresh(factory)
    return factory_sheet_overview(db, factory)


@router.get("/owners")
def owners(
    response: Response,
    search: Optional[str] = None,
    subscription_status: Optional[str] = None,
    payment_status: Optional[str] = None,
    active: Optional[bool] = None,
    sort: str = "newest",
    db: Session = Depends(get_db),
    admin_email: str = Depends(require_super_admin),
):
    no_store(response)
    query = owner_query(db).outerjoin(Factory, User.factory_id == Factory.id)
    if search:
        term = f"%{search}%"
        query = query.filter(or_(User.full_name.ilike(term), User.email.ilike(term), User.phone_number.ilike(term), Factory.name.ilike(term), Factory.factory_name.ilike(term)))
    if subscription_status:
        query = query.filter(Factory.subscription_status == subscription_status)
    if payment_status:
        query = query.filter(Factory.payment_status == payment_status)
    if active is not None:
        query = query.filter(User.is_active == active)
    query = query.order_by(User.id.asc() if sort == "oldest" else User.id.desc())
    return [
        {
            **user_public(user),
            "factory": factory_summary(db, user.factory) if user.factory else None,
        }
        for user in query.limit(500).all()
    ]


@router.post("/owners")
def create_owner(payload: OwnerCreateRequest, request: Request, response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=422, detail="Password and confirm password do not match")
    email = payload.email.strip().lower() if (payload.email and payload.email.strip()) else None
    phone_number_cleaned = payload.phone_number.strip() if (payload.phone_number and payload.phone_number.strip()) else None
    if not email and not phone_number_cleaned:
        raise HTTPException(status_code=422, detail="Email or phone number is required")

    full_phone = None
    local_phone = None
    if phone_number_cleaned:
        full_phone, local_phone = normalize_phone_number(phone_number_cleaned, payload.country_code)

    if email and db.query(User).filter(func.lower(User.email) == email).first():
        raise HTTPException(status_code=409, detail="Email already exists")
    if full_phone and db.query(User).filter(or_(User.phone_number == full_phone, User.phone_number_normalized == local_phone)).first():
        raise HTTPException(status_code=409, detail="Phone number already exists")
    if db.query(Factory).filter(or_(Factory.name == payload.factory_name, Factory.factory_name == payload.factory_name)).first():
        raise HTTPException(status_code=409, detail="Factory name already exists")

    now = datetime.now(timezone.utc)
    start = payload.subscription_start_date or now
    end = payload.subscription_end_date
    if end is None and payload.subscription_status in {"trial", "trial_active"}:
        end = now + timedelta(days=7)

    factory = Factory(
        name=payload.factory_name,
        factory_name=payload.factory_name,
        address=payload.factory_address,
        active_plan=payload.initial_subscription_plan,
        plan_name=payload.initial_subscription_plan,
        subscription_status=payload.subscription_status,
        payment_status=payload.payment_status,
        billing_cycle=payload.billing_cycle,
        trial_start_date=start if payload.subscription_status in {"trial", "trial_active"} else None,
        trial_end_date=end if payload.subscription_status in {"trial", "trial_active"} else None,
        subscription_start_date=start if payload.subscription_status == "active" else None,
        subscription_end_date=end if payload.subscription_status == "active" else None,
        subscription_start=start if payload.subscription_status == "active" else None,
        subscription_end=end if payload.subscription_status == "active" else None,
        plan_expires_at=end,
        usage_limit=payload.usage_limit,
        token_limit=payload.token_limit,
        admin_note=payload.notes,
        is_active=True,
    )
    db.add(factory)
    db.flush()

    username = email or full_phone or f"owner-{uuid4()}"
    owner = User(
        user_id=str(uuid4()),
        factory_id=factory.id,
        username=username,
        email=email,
        phone_number=full_phone,
        phone_number_normalized=local_phone,
        full_name=payload.owner_name,
        password_hash=hash_password(payload.password),
        role="Owner",
        is_verified=True,
        is_active=True,
    )
    db.add(owner)
    db.flush()
    factory.owner_id = owner.id
    factory.owner_phone_number = owner.phone_number

    summary = {"owner": user_public(owner), "factory": factory_summary(db, factory)}
    audit(db, request, admin_email, "CREATE_FACTORY_OWNER", "owner", owner.id, None, summary, payload.notes)
    db.commit()
    db.refresh(owner)
    db.refresh(factory)
    return {"owner": user_public(owner), "factory": factory_summary(db, factory)}


@router.get("/owners/{owner_id}")
def owner_detail(owner_id: int, response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    owner = owner_query(db).filter(User.id == owner_id).first()
    if owner is None:
        raise HTTPException(status_code=404, detail="Owner not found")
    return {**user_public(owner), "factory": factory_summary(db, owner.factory) if owner.factory else None}


@router.patch("/owners/{owner_id}")
def patch_owner(owner_id: int, payload: OwnerPatchRequest, request: Request, response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    owner = owner_query(db).filter(User.id == owner_id).first()
    if owner is None:
        raise HTTPException(status_code=404, detail="Owner not found")
    old = user_public(owner)
    
    # Audit role change if role is changing
    if payload.role is not None and payload.role != owner.role:
        audit(db, request, admin_email, "role_change", "user", owner.id, {"role": owner.role}, {"role": payload.role}, f"User role updated to {payload.role}")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(owner, field, value)
    audit(db, request, admin_email, "owner_update", "user", owner.id, old, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(owner)
    return user_public(owner)


@router.patch("/owners/{owner_id}/status")
def patch_owner_status(owner_id: int, payload: OwnerStatusRequest, request: Request, response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    owner = owner_query(db).filter(User.id == owner_id).first()
    if owner is None:
        raise HTTPException(status_code=404, detail="Owner not found")
    old = {"is_active": owner.is_active}
    owner.is_active = payload.is_active
    audit(db, request, admin_email, "owner_status_update", "user", owner.id, old, {"is_active": owner.is_active}, payload.note)
    db.commit()
    return user_public(owner)


@router.get("/factories")
def factories(response: Response, search: Optional[str] = None, active: Optional[bool] = None, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    query = db.query(Factory).outerjoin(User, Factory.owner_id == User.id)
    if search:
        term = f"%{search}%"
        query = query.filter(or_(Factory.name.ilike(term), Factory.factory_name.ilike(term), User.full_name.ilike(term), User.email.ilike(term), User.phone_number.ilike(term)))
    if active is not None:
        query = query.filter(Factory.is_active == active)
    return [factory_summary(db, factory) for factory in query.order_by(Factory.id.desc()).limit(500).all()]


@router.post("/factories")
def create_factory(payload: FactoryCreateRequest, request: Request, response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    factory = Factory(name=payload.name, factory_name=payload.factory_name or payload.name, owner_id=payload.owner_id, is_active=payload.is_active, address=payload.address, admin_note=payload.admin_note)
    db.add(factory)
    db.flush()
    audit(db, request, admin_email, "factory_create", "factory", factory.id, None, payload.model_dump())
    db.commit()
    db.refresh(factory)
    return factory_summary(db, factory)


@router.post("/factories/bulk-delete-preview")
def bulk_delete_preview(payload: BulkFactoryIdsRequest, response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    factories = validate_bulk_factory_ids(db, payload.factory_ids)
    previews = [factory_delete_preview(db, factory) for factory in factories]
    return {"factories": previews, "total_counts": combine_preview_counts(previews)}


@router.get("/factories/{factory_id}/delete-preview")
def single_delete_preview(factory_id: int, response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    factory = db.query(Factory).filter(Factory.id == factory_id).first()
    if factory is None:
        raise HTTPException(status_code=404, detail="Factory not found")
    return factory_delete_preview(db, factory)


@router.delete("/factories/bulk-delete")
def bulk_delete_factories(payload: BulkDeleteRequest, request: Request, response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    if not bulk_delete_enabled():
        raise HTTPException(status_code=403, detail="Bulk delete is disabled by server configuration.")
    if payload.confirmation != BULK_DELETE_CONFIRMATION:
        raise HTTPException(status_code=422, detail=f"Confirmation phrase must be exactly: {BULK_DELETE_CONFIRMATION}")

    factories = validate_bulk_factory_ids(db, payload.factory_ids)
    deleted_factory_ids = [factory.id for factory in factories]
    previews = [factory_delete_preview(db, factory) for factory in factories]
    deleted_counts = {"factories": len(factories), **empty_delete_counts()}
    deleted_counts.pop("audit_logs", None)

    try:
        for factory in factories:
            result = delete_factory_cascade(db, factory, admin_email, mode="bulk")
            for key, value in result["deleted_counts"].items():
                add_count(deleted_counts, key, value)
        audit(
            db,
            request,
            admin_email,
            "BULK_DELETE_FACTORIES_CASCADE",
            "factory",
            deleted_factory_ids,
            {"selected_factories": previews, "related_record_counts": combine_preview_counts(previews)},
            {"deleted": True, "deleted_factory_ids": deleted_factory_ids, "deleted_counts": deleted_counts},
            f"Deleted {len(deleted_factory_ids)} factories from Super Admin bulk delete",
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Bulk delete failed and was rolled back: {exc}") from exc

    return {
        "deleted_factory_ids": deleted_factory_ids,
        "deleted_counts": deleted_counts,
        "message": "Selected factories and their associated owners, workers, and related data deleted successfully.",
    }


@router.get("/factories/{factory_id}")
def factory_detail(factory_id: int, response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    factory = db.query(Factory).filter(Factory.id == factory_id).first()
    if factory is None:
        raise HTTPException(status_code=404, detail="Factory not found")
    return {**factory_summary(db, factory), "counts": factory_counts(db, factory_id)}


@router.patch("/factories/{factory_id}")
def patch_factory(factory_id: int, payload: FactoryPatchRequest, request: Request, response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    factory = db.query(Factory).filter(Factory.id == factory_id).first()
    if factory is None:
        raise HTTPException(status_code=404, detail="Factory not found")
    old = factory_summary(db, factory)
    
    # Audit factory suspension
    if payload.is_active is not None and payload.is_active != factory.is_active:
        action = "factory_suspension" if not payload.is_active else "factory_unsuspension"
        audit(db, request, admin_email, action, "factory", factory.id, {"is_active": factory.is_active}, {"is_active": payload.is_active}, "Factory status changed.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(factory, field, value)
    audit(db, request, admin_email, "factory_update", "factory", factory.id, old, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(factory)
    return factory_summary(db, factory)


@router.delete("/factories/{factory_id}")
def delete_factory(factory_id: int, payload: SingleFactoryDeleteRequest, request: Request, response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    if not factory_delete_enabled():
        raise HTTPException(status_code=403, detail="Factory delete is disabled by server configuration.")
    if payload.confirmation != SINGLE_DELETE_CONFIRMATION:
        raise HTTPException(status_code=422, detail=f"Confirmation phrase must be exactly: {SINGLE_DELETE_CONFIRMATION}")
    try:
        result = delete_factory_cascade(db, factory_id, admin_email, mode="single")
        audit(
            db,
            request,
            admin_email,
            "DELETE_FACTORY_CASCADE",
            "factory",
            factory_id,
            result["preview"],
            {"deleted": True, "deleted_factory_ids": [factory_id], "owner_actions": {str(factory_id): result["owner_action"]}, "deleted_counts": result["deleted_counts"]},
            f"Deleted factory {factory_id} from Super Admin single delete",
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Factory delete failed and was rolled back: {exc}") from exc
    return {
        "deleted_factory_id": factory_id,
        "owner_action": result["owner_action"],
        "deleted_counts": result["deleted_counts"],
        "message": "Factory and associated owner, workers, and related data deleted successfully.",
    }


@router.get("/subscriptions")
def subscriptions(response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    return [factory_summary(db, factory) for factory in db.query(Factory).order_by(Factory.id.desc()).limit(500).all()]


@router.patch("/subscriptions/{subscription_id}")
def patch_subscription(subscription_id: int, payload: SubscriptionPatchRequest, request: Request, response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    factory = db.query(Factory).filter(Factory.id == subscription_id).first()
    if factory is None:
        raise HTTPException(status_code=404, detail="Subscription/factory not found")
    old = factory_summary(db, factory)
    data = payload.model_dump(exclude_unset=True)
    note = data.pop("note", None)
    admin_note = data.pop("admin_note", None)
    apply_factory_subscription_update(factory, data)
    if admin_note is not None:
        factory.admin_note = admin_note
    # Emit a dedicated subscription_override event when subscription-critical fields are touched
    _OVERRIDE_FIELDS = {"active_plan", "plan_name", "subscription_status", "payment_status",
                       "subscription_end_date", "plan_expires_at", "usage_limit", "token_limit"}
    if _OVERRIDE_FIELDS.intersection(data.keys()):
        audit(db, request, admin_email, "subscription_override", "factory", factory.id, old, data, note or "Subscription fields overridden by super admin.")
    audit(db, request, admin_email, "subscription_update", "factory", factory.id, old, data, note)
    db.commit()
    db.refresh(factory)
    return factory_summary(db, factory)


@router.post("/owners/{owner_id}/subscription")
def owner_subscription(owner_id: int, payload: OwnerSubscriptionRequest, request: Request, response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    owner = owner_query(db).filter(User.id == owner_id).first()
    if owner is None or owner.factory is None:
        raise HTTPException(status_code=404, detail="Owner or factory not found")
    factory = owner.factory
    old = factory_summary(db, factory)
    data = payload.model_dump(exclude_unset=True)
    note = data.pop("note", None)
    apply_factory_subscription_update(factory, data)
    audit(db, request, admin_email, "owner_subscription_update", "factory", factory.id, old, data, note)
    db.commit()
    db.refresh(factory)
    return factory_summary(db, factory)


@router.post("/subscriptions/manual-adjustment")
def manual_subscription(payload: ManualSubscriptionAdjustment, request: Request, response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    factory = db.query(Factory).filter(Factory.id == payload.factory_id).first()
    if factory is None:
        raise HTTPException(status_code=404, detail="Factory not found")
    old = factory_summary(db, factory)
    start = payload.subscription_start_date or datetime.now(timezone.utc)
    factory.active_plan = payload.plan_name
    factory.plan_name = payload.plan_name
    factory.subscription_status = payload.subscription_status
    factory.payment_status = payload.payment_status
    factory.billing_cycle = payload.billing_cycle
    factory.subscription_start_date = start
    factory.subscription_start = start
    factory.subscription_end_date = payload.subscription_end_date
    factory.subscription_end = payload.subscription_end_date
    factory.plan_expires_at = payload.subscription_end_date
    factory.usage_limit = payload.usage_limit
    factory.token_limit = payload.token_limit
    factory.admin_note = payload.admin_note
    # Dedicated subscription_override audit event for manual adjustments
    audit(db, request, admin_email, "subscription_override", "factory", factory.id, old, payload.model_dump(), payload.note or "Manual subscription adjustment by super admin.")
    audit(db, request, admin_email, "subscription_manual_adjustment", "factory", factory.id, old, payload.model_dump(), payload.note)
    db.commit()
    db.refresh(factory)
    return factory_summary(db, factory)


@router.get("/payments")
def payments(response: Response, status_filter: Optional[str] = None, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    query = db.query(SubscriptionPayment)
    if status_filter:
        query = query.filter(SubscriptionPayment.payment_status == status_filter)
    return [
        {
            "id": p.id,
            "factory_id": p.factory_id,
            "plan_code": p.plan_code,
            "billing_cycle": p.billing_cycle,
            "amount_paise": p.amount_paise,
            "currency": p.currency,
            "payment_status": p.payment_status,
            "provider": p.provider,
            "provider_payment_id": p.provider_payment_id,
            "subscription_start_date": p.subscription_start_date,
            "subscription_end_date": p.subscription_end_date,
            "created_at": p.created_at,
        }
        for p in query.order_by(SubscriptionPayment.created_at.desc()).limit(500).all()
    ]


@router.patch("/payments/{payment_id}")
def patch_payment(payment_id: int, payload: PaymentPatchRequest, request: Request, response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    payment = db.query(SubscriptionPayment).filter(SubscriptionPayment.id == payment_id).first()
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    old = {"payment_status": payment.payment_status, "amount_paise": payment.amount_paise, "provider_payment_id": payment.provider_payment_id}
    data = payload.model_dump(exclude_unset=True)
    note = data.pop("note", None)
    for field, value in data.items():
        setattr(payment, field, value)
    audit(db, request, admin_email, "payment_update", "subscription_payment", payment.id, old, data, note)
    db.commit()
    return {"ok": True}


@router.post("/payments/manual-entry")
def manual_payment(payload: ManualPaymentEntry, request: Request, response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    start = payload.subscription_start_date or datetime.now(timezone.utc)
    payment = SubscriptionPayment(
        factory_id=payload.factory_id,
        plan_code=payload.plan_code,
        billing_cycle=payload.billing_cycle,
        amount_paise=payload.amount_paise,
        payment_status=payload.payment_status,
        provider="manual",
        provider_payment_id=payload.provider_payment_id,
        subscription_start_date=start,
        subscription_end_date=payload.subscription_end_date,
    )
    db.add(payment)
    db.flush()
    audit(db, request, admin_email, "payment_manual_entry", "subscription_payment", payment.id, None, payload.model_dump(), payload.note)
    db.commit()
    return {"ok": True, "id": payment.id}


@router.get("/audit-logs")
def audit_logs(response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    return [
        {
            "id": row.id,
            "admin_email": row.admin_email,
            "action_type": row.action_type,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "old_value": row.old_value,
            "new_value": row.new_value,
            "note": row.note,
            "ip_address": row.ip_address,
            "created_at": row.created_at,
        }
        for row in db.query(SuperAdminAuditLog).order_by(SuperAdminAuditLog.created_at.desc(), SuperAdminAuditLog.id.desc()).limit(500).all()
    ]


@router.get("/usage/summary")
def usage_overview(response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    total_app_events = db.query(AppUsageLog).count()
    total_tokens = db.query(func.coalesce(func.sum(TokenUsageLog.total_tokens), 0)).scalar() or 0
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_tokens = db.query(func.coalesce(func.sum(TokenUsageLog.total_tokens), 0)).filter(TokenUsageLog.created_at >= month_start).scalar() or 0
    last_activity = db.query(AppUsageLog).order_by(AppUsageLog.created_at.desc()).first()
    return {
        "total_app_events": total_app_events,
        "total_token_usage": int(total_tokens),
        "monthly_token_usage": int(monthly_tokens),
        "last_active_at": last_activity.created_at if last_activity else None,
    }


@router.get("/usage/factories")
def usage_factories(response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    return [factory_summary(db, factory) for factory in db.query(Factory).order_by(Factory.id.desc()).limit(500).all()]


@router.get("/usage/owners")
def usage_owners(response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    return [
        {**user_public(owner), "usage": usage_summary(db, owner.factory_id, owner.id), "factory": factory_summary(db, owner.factory) if owner.factory else None}
        for owner in owner_query(db).order_by(User.id.desc()).limit(500).all()
    ]


@router.get("/usage/token-logs")
def usage_token_logs(response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    return [
        {
            "id": row.id,
            "factory_id": row.factory_id,
            "user_id": row.user_id,
            "provider": row.provider,
            "model": row.model,
            "feature_name": row.feature_name,
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "total_tokens": row.total_tokens,
            "estimated_cost": str(row.estimated_cost) if row.estimated_cost is not None else None,
            "created_at": row.created_at,
        }
        for row in db.query(TokenUsageLog).order_by(TokenUsageLog.created_at.desc(), TokenUsageLog.id.desc()).limit(500).all()
    ]


@router.get("/usage/app-logs")
def usage_app_logs(response: Response, db: Session = Depends(get_db), admin_email: str = Depends(require_super_admin)):
    no_store(response)
    return [
        {
            "id": row.id,
            "factory_id": row.factory_id,
            "user_id": row.user_id,
            "event_type": row.event_type,
            "route_or_module": row.route_or_module,
            "method": row.method,
            "created_at": row.created_at,
        }
        for row in db.query(AppUsageLog).order_by(AppUsageLog.created_at.desc(), AppUsageLog.id.desc()).limit(500).all()
    ]

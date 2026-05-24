from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
import hmac
import httpx
import json
import os
import re
from typing import Dict, List, Optional, Tuple
from urllib import request as urlrequest
from urllib.error import URLError

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.security import OAuth2PasswordRequestForm
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func as sql_func, text
from sqlalchemy.orm import Session

from ai_agent import build_ai_tool_context, parse_factory_intent_with_agent, save_agent_context
from auth import (
    authenticate_user,
    create_access_token,
    ensure_auth_config,
    get_current_user,
    get_user_by_username,
    hash_password,
    public_router as public_auth_router,
    require_owner,
    router as auth_router,
    v1_router,
)
from db import Base, engine, get_db
from models import (
    AdvancePayment,
    AttendanceLog,
    BlankStock,
    BottomStock,
    BoxStock,
    Customer,
    CustomerActivity,
    DailyProduction,
    Employee,
    ExpenseLog,
    FactoryExpense,
    Factory,
    FinalProductStock,
    FactoryInventory,
    FinishedGoodsStock,
    Inventory,
    Machine,
    Order,
    OrderItem,
    PackagingProfile,
    PackagingMetrics,
    Payment,
    ProductionLog,
    RawMaterialMetrics,
    SalesInvoice,
    User,
    Worker,
    HisabSettlement,
    AppUsageLog,
    TokenUsageLog,
)
from routers.onboarding import router as onboarding_router
from routers.calculator import router as calculator_router
from routers.automation import router as automation_router
from routers.phase1 import router as phase1_router
from routers.operations import router as operations_router
from routers import sales
from routers import inventory
from routers import payments
from routers import dashboard
from routers import attendance
from routers import billing
from routers import staff
from routers import super_admin
from routers import expenses
from routers import integrations
from routers import machine_onboarding
from routers import machine_templates

app = FastAPI(title="AI ERP API", version="0.1.0")


def parse_cors_origins() -> List[str]:
    default_origins = [
        # Local development
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:4173",   # Vite preview mode
        "http://127.0.0.1:4173",
        "http://localhost:8000",   # Direct API access during dev
        "http://127.0.0.1:8000",
        "http://localhost:80",
        "http://localhost",
        # Production
        "https://munshiai.co.in",
        "https://www.munshiai.co.in",
    ]
    configured = [
        os.getenv("FRONTEND_ORIGIN"),
        os.getenv("HOSTINGER_DOMAIN"),
        os.getenv("HOSTINGER_IP"),
    ]
    configured.extend((os.getenv("CORS_ORIGINS") or "").split(","))

    origins = []
    for origin in [*default_origins, *configured]:
        if not origin:
            continue
        cleaned = origin.strip().rstrip("/")
        candidates = [cleaned]
        if cleaned and not cleaned.startswith(("http://", "https://")):
            candidates = [f"https://{cleaned}", f"http://{cleaned}"]
        for candidate in candidates:
            if candidate and candidate not in origins:
                origins.append(candidate)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(onboarding_router)
app.include_router(calculator_router)
app.include_router(automation_router)
app.include_router(phase1_router)
app.include_router(operations_router)
app.include_router(sales.router, prefix="/api/sales", tags=["sales"])
app.include_router(sales.router, prefix="/api", tags=["customers"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
app.include_router(payments.router)
app.include_router(auth_router)
app.include_router(public_auth_router)
app.include_router(v1_router)
app.include_router(dashboard.router)
app.include_router(dashboard.v1_router)
app.include_router(attendance.router)
app.include_router(billing.router)
app.include_router(staff.router)
app.include_router(staff.v1_router)
app.include_router(staff.staff_v1_router)
app.include_router(staff.security_v1_router)
app.include_router(super_admin.router)
app.include_router(expenses.router)
app.include_router(integrations.router)
app.include_router(machine_onboarding.router)
app.include_router(machine_templates.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


class InventoryCreate(BaseModel):
    raw_material_name: str = Field(..., min_length=1, max_length=255)
    quantity: int = Field(..., ge=0)


class InventoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    raw_material_name: str
    category: Optional[str] = None
    packaging_size: Optional[str] = None
    pieces_per_packet: Optional[int] = None
    packets_per_box: Optional[int] = None
    quantity: Optional[int] = None
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    factory_id: int


class CurrentUserResponse(BaseModel):
    id: int
    username: str
    role: str
    factory_id: int
    phone_number: Optional[str] = None
    telegram_id: Optional[str] = None


class N8NTestRequest(BaseModel):
    factory_id: int
    message: str


class IntegrationSettings(BaseModel):
    phone_number: Optional[str] = Field(default=None, max_length=50)
    telegram_id: Optional[str] = Field(default=None, max_length=100)


class ExternalChatPlatform(str, Enum):
    whatsapp = "whatsapp"
    telegram = "telegram"


class ExternalChatRequest(BaseModel):
    sender_id: str = Field(..., min_length=1, max_length=100)
    platform: ExternalChatPlatform
    message: str = Field(..., min_length=1)


class ExternalChatResponse(BaseModel):
    reply: str
    status: str
    action_taken: str


class FactoryIntentType(str, Enum):
    production_entry = "production_entry"
    sales_entry = "sales_entry"
    expense_entry = "expense_entry"
    employee_entry = "employee_entry"
    general_qa = "general_qa"


class SupervisorToolName(str, Enum):
    check_inventory = "check_inventory"
    record_sale = "record_sale"
    log_production = "log_production"


class ProductionIntentData(BaseModel):
    product_name: Optional[str] = None
    cup_size_ml: Optional[int] = None
    packing_profile_name: Optional[str] = None
    quantity: Optional[int] = None
    boxes_produced: Optional[int] = None
    blank_used: Optional[int] = 0
    bottom_used: Optional[float] = 0
    blank_waste: Optional[int] = 0
    bottom_waste: Optional[float] = 0
    machine_speed: Optional[float] = None
    wastage: Optional[float] = 0


class SalesIntentData(BaseModel):
    customer_name: Optional[str] = None
    product_name: Optional[str] = None
    cup_size_ml: Optional[int] = None
    packing_profile_name: Optional[str] = None
    quantity: Optional[int] = None
    boxes_sold: Optional[int] = None
    rate_per_box: Optional[float] = None
    amount_received: Optional[float] = None


class ExpenseIntentData(BaseModel):
    category: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    payment_method: Optional[str] = None


class EmployeeIntentData(BaseModel):
    employee_name: Optional[str] = None
    is_present: Optional[bool] = None
    overtime_hours: Optional[float] = None
    advance_given: Optional[float] = None


class GeneralQAData(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None


class FactoryIntent(BaseModel):
    intent_type: FactoryIntentType
    tool_name: Optional[SupervisorToolName] = None
    tool_args: Dict[str, str | int | float | None] = Field(default_factory=dict)
    production_data: Optional[ProductionIntentData] = None
    sales_data: Optional[SalesIntentData] = None
    expense_data: Optional[ExpenseIntentData] = None
    employee_data: Optional[EmployeeIntentData] = None
    general_data: Optional[GeneralQAData] = None


class AskAIRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str = Field(default="default", min_length=1, max_length=100)
    chat_history: Optional[List[Dict[str, str]]] = None
    factory_id: Optional[int] = None
    system_prompt: Optional[str] = None


class BusinessExecutionResult(BaseModel):
    status: str
    message: str
    production_log_id: Optional[int] = None
    sales_invoice_id: Optional[int] = None
    packaging_profile_id: Optional[int] = None
    finished_goods_boxes_available: Optional[int] = None
    total_boxes_needed: Optional[int] = None
    total_polys_needed: Optional[int] = None
    total_packing_cost: Optional[Decimal] = None
    total_raw_material_cost: Optional[Decimal] = None
    total_production_cost: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    amount_paid: Optional[Decimal] = None
    customer_balance_amount: Optional[Decimal] = None
    expense_log_id: Optional[int] = None
    expense_amount: Optional[Decimal] = None
    employee_id: Optional[int] = None
    attendance_log_id: Optional[int] = None
    advance_payment_id: Optional[int] = None
    advance_amount: Optional[Decimal] = None
    overtime_hours: Optional[float] = None


class AskAIResponse(BaseModel):
    ai_reply: str
    action_taken: FactoryIntentType
    status: str
    intent: Optional[FactoryIntent] = None
    result: Optional[BusinessExecutionResult] = None
    error: Optional[str] = None


ALLOWED_AUDIO_EXTENSIONS = {".ogg", ".mp3", ".wav", ".m4a", ".webm"}
LOW_STOCK_THRESHOLD_KG = Decimal("50")
SUPPLIER_WHATSAPP_NUMBER = "+919999999999"


class ProfitLossReport(BaseModel):
    revenue: Decimal
    cash_received: Decimal
    outstanding_receivables: Decimal
    total_packing_cost: Decimal
    total_raw_material_cost: Decimal
    total_production_cost: Decimal
    total_expenses: Decimal
    net_profit: Decimal


class DailyProductionSales(BaseModel):
    date: date
    production_boxes: int
    sales_boxes: int


class WastageMix(BaseModel):
    good_production_pcs: int
    blank_waste_pcs: int
    bottom_waste_kg: Decimal


class DashboardStats(BaseModel):
    monthly_net_profit: Decimal
    total_pending_recoveries: Decimal
    total_boxes_in_stock: int
    overall_wastage_percent: Decimal
    recent_7_days: List[DailyProductionSales]
    wastage_mix: WastageMix


class CustomerBalanceRow(BaseModel):
    customer_name: str
    total_billed: Decimal
    pending_amount: Decimal


class PendingPaymentRow(BaseModel):
    name: str
    contact_number: Optional[str] = None
    pending_amount: Decimal


class VerifiedStoreCustomerRow(BaseModel):
    name: str
    contact_number: Optional[str] = None
    store_token: str


class LowStockInventoryRow(BaseModel):
    id: int
    item_name: str
    category: Optional[str] = None
    packaging_size: Optional[str] = None
    pieces_per_packet: Optional[int] = None
    packets_per_box: Optional[int] = None
    unit: str
    quantity: Decimal
    supplier_whatsapp_number: str


class LiveActivityRow(BaseModel):
    id: int
    customer_id: int
    customer_name: str
    activity_type: str
    created_at: datetime


class ProductionLogRow(BaseModel):
    id: int
    date: date
    shift: str
    cup_size_ml: int
    packaging_profile_name: str
    boxes_produced: int
    estimated_good_cups: int
    blank_waste_pcs: int
    bottom_waste_kg: Decimal
    blank_wastage_percent: Decimal
    total_packing_cost: Decimal
    total_production_cost: Decimal


class InventoryRow(BaseModel):
    id: int
    item_name: str
    category: Optional[str] = None
    packaging_size: Optional[str] = None
    pieces_per_packet: Optional[int] = None
    packets_per_box: Optional[int] = None
    unit: str
    quantity: Decimal
    price_per_unit: Decimal


class FinishedGoodsRow(BaseModel):
    id: int
    cup_size_ml: int
    packaging_profile_name: str
    boxes_available: int
    updated_at: datetime


class LiveInventoryReport(BaseModel):
    raw_materials: List[InventoryRow]
    packaging_materials: List[InventoryRow]
    finished_goods: List[FinishedGoodsRow]


class StorefrontProduct(BaseModel):
    product_id: int
    cup_size_ml: int
    packaging_profile_name: str
    availability_status: str
    base_price: Decimal
    image_url: Optional[str] = None
    print_design_name: Optional[str] = None


class StorefrontResponse(BaseModel):
    customer_id: int
    customer_name: str
    contact_number: Optional[str] = None
    advance_discount_pct: float
    terms_and_conditions: str
    products: List[StorefrontProduct]


class StoreCheckoutItem(BaseModel):
    product_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)


class StoreCheckoutRequest(BaseModel):
    items: List[StoreCheckoutItem] = Field(..., min_length=1)
    payment_method: str
    terms_accepted: bool


class StoreCheckoutItemResponse(BaseModel):
    product_id: int
    packaging_profile_name: str
    quantity: int
    base_rate: Decimal
    final_rate: Decimal
    line_total: Decimal


class StoreCheckoutResponse(BaseModel):
    message: str
    order_id: int
    status: str
    payment_method: str
    discount_pct: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    previous_balance: Decimal
    new_total_balance: Decimal
    upi_payment_details: Optional[Dict[str, str]] = None
    items: List[StoreCheckoutItemResponse]


class RevokeDiscountResponse(BaseModel):
    message: str
    order_id: int
    customer_id: int
    payment_method: str
    previous_total_amount: Decimal
    recalculated_total_amount: Decimal
    discount_revoked_amount: Decimal
    customer_balance_amount: Decimal


class EmployeeReport(BaseModel):
    employee_id: int
    employee_name: str
    role: str
    month_start: date
    month_end: date
    days_present: int
    total_overtime_hours: float
    daily_wage: Decimal
    overtime_rate: Decimal
    gross_salary: Decimal
    total_advance: Decimal
    net_payable: Decimal


async def transcribe_audio_upload(audio: UploadFile) -> str:
    filename = audio.filename or "voice-note.ogg"
    _, extension = os.path.splitext(filename.lower())
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "Unsupported audio file type. Upload one of: "
                + ", ".join(sorted(ALLOWED_AUDIO_EXTENSIONS))
            ),
        )

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured for voice transcription",
        )

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded audio file is empty",
        )

    try:
        client = OpenAI(api_key=openai_api_key)
        transcription = client.audio.transcriptions.create(
            model=os.getenv("OPENAI_WHISPER_MODEL") or "whisper-1",
            file=(filename, audio_bytes, audio.content_type or "application/octet-stream"),
            response_format="text",
        )
    except OpenAIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Whisper transcription failed: {exc}",
        ) from exc

    transcribed_text = (
        transcription.strip()
        if isinstance(transcription, str)
        else str(getattr(transcription, "text", "")).strip()
    )
    if not transcribed_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Whisper returned an empty transcription",
        )
    return transcribed_text


def extract_first_int(message: str, patterns: List[str]) -> Optional[int]:
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def extract_first_float(message: str, patterns: List[str]) -> Optional[float]:
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def extract_cup_size_ml(message: str) -> Optional[int]:
    return extract_first_int(message, [r"\b(\d+)\s*ml\b"])


def extract_packing_profile_name(message: str, cup_size_ml: Optional[int]) -> Optional[str]:
    match = re.search(
        r"\b\d+\s*ml\b\s*(?:ke|ki|ka|mein|me|with|of)?\s*([a-zA-Z ]*packing)\b",
        message,
        flags=re.IGNORECASE,
    )
    if not match or cup_size_ml is None:
        return None

    packing_type = re.sub(r"\s+", " ", match.group(1)).strip().title()
    return f"{cup_size_ml}ml {packing_type}"


def extract_customer_name(message: str) -> Optional[str]:
    match = re.search(
        r"(?:customer|party|client)\s+([a-zA-Z][a-zA-Z ]{1,80}?)(?:\s+ko|\s+ne|\s+for|\s+sold|\s+sale|$)",
        message,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    return re.sub(r"\s+", " ", match.group(1)).strip().title()


def extract_expense_description(message: str) -> str:
    cleaned = re.sub(r"\b\d+(?:\.\d+)?\b", "", message)
    cleaned = re.sub(
        r"\b(expense|kharcha|paid|payment|amount|rs|inr|rupees|rupaye|ka|ke|ki|for|on)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title() if cleaned else "General Expense"


def extract_expense_category(message: str) -> str:
    lowered = message.lower()
    category_keywords = {
        "Electricity": ("electric", "bijli", "power"),
        "Rent": ("rent", "kiraya"),
        "Salary": ("salary", "wages", "mazdoori"),
        "Transport": ("transport", "freight", "diesel", "petrol"),
        "Maintenance": ("repair", "maintenance", "machine"),
    }

    for category, keywords in category_keywords.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return "General"


def extract_employee_name(message: str) -> Optional[str]:
    patterns = [
        r"\b([a-zA-Z][a-zA-Z ]{1,80}?)\s+(?:was\s+)?(?:present|absent)\b",
        r"\b([a-zA-Z][a-zA-Z ]{1,80}?)\s+(?:did|worked)\s+\d+(?:\.\d+)?\s*(?:hours?|hrs?)\s+overtime\b",
        r"\b([a-zA-Z][a-zA-Z ]{1,80}?)\s+(?:took|received|got)\s+\d+(?:\.\d+)?\s+advance\b",
        r"(?:employee|worker|staff)\s+([a-zA-Z][a-zA-Z ]{1,80}?)(?:\s+was|\s+is|\s+present|\s+absent|\s+took|\s+did|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip().title()
    return None


def extract_employee_presence(message: str) -> Optional[bool]:
    lowered = message.lower()
    if re.search(r"\b(absent|chhutti|leave)\b", lowered):
        return False
    if re.search(r"\b(present|aaya|aayi|available)\b", lowered):
        return True
    return None


def extract_employee_data(message: str) -> EmployeeIntentData:
    overtime_hours = extract_first_float(
        message,
        [
            r"(?:did|worked)?\s*(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\s+overtime",
            r"overtime\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)?",
            r"ot\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)?",
        ],
    )
    advance_given = extract_first_float(
        message,
        [
            r"(?:took|received|got|advance)\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\s*(?:advance|rs|inr|rupees|rupaye)?",
            r"\b(\d+(?:\.\d+)?)\s*(?:advance)\b",
            r"\b(\d+(?:\.\d+)?)\s*(?:rs|inr|rupees|rupaye)\s*(?:advance)\b",
        ],
    )
    return EmployeeIntentData(
        employee_name=extract_employee_name(message),
        is_present=extract_employee_presence(message),
        overtime_hours=overtime_hours,
        advance_given=advance_given,
    )


def infer_intent_type(message: str) -> FactoryIntentType:
    lowered = message.lower()
    sales_markers = ("sold", "sale", "invoice", "becha", "beche", "bika", "nikal", "dispatch", "customer", "payment", "paid", "received")
    expense_markers = ("expense", "kharcha", "rent", "salary", "bijli", "electricity", "repair", "maintenance")
    employee_markers = ("present", "absent", "overtime", " ot ", "advance", "employee", "worker", "staff")
    production_markers = ("box bane", "produced", "production", "blank", "bottom", "waste", "add karo", "banaya", "made")

    if any(marker in lowered for marker in employee_markers):
        return FactoryIntentType.employee_entry
    if any(marker in lowered for marker in expense_markers):
        return FactoryIntentType.expense_entry
    if any(marker in lowered for marker in sales_markers):
        return FactoryIntentType.sales_entry
    if any(marker in lowered for marker in production_markers) or re.search(r"\b\d+\s*(?:box|boxes)\b", lowered):
        return FactoryIntentType.production_entry
    if "?" in message or any(word in lowered for word in ("what", "how", "kitna", "kya", "show", "report", "balance", "stock")):
        return FactoryIntentType.general_qa
    return FactoryIntentType.production_entry


def extract_factory_intent(message: str) -> FactoryIntent:
    cup_size_ml = extract_cup_size_ml(message)
    packing_profile_name = extract_packing_profile_name(message, cup_size_ml)
    intent_type = infer_intent_type(message)

    if intent_type == FactoryIntentType.sales_entry:
        sales_data = SalesIntentData(
            customer_name=extract_customer_name(message),
            product_name=f"{cup_size_ml}ml Paper Cup" if cup_size_ml is not None else None,
            cup_size_ml=cup_size_ml,
            packing_profile_name=packing_profile_name,
            quantity=extract_first_int(message, [r"\b(\d+)\s*(?:box|boxes)\b"]),
            boxes_sold=extract_first_int(message, [r"\b(\d+)\s*(?:box|boxes)\b"]),
            rate_per_box=extract_first_float(message, [r"(?:rate|rate_per_box)\s*(?:is|=|:)?\s*(\d+(?:\.\d+)?)"]),
            amount_received=extract_first_float(
                message,
                [r"(?:received|paid|amount_received|payment)\s*(?:is|=|:)?\s*(\d+(?:\.\d+)?)"],
            ),
        )
        return FactoryIntent(
            intent_type=intent_type,
            tool_name=SupervisorToolName.record_sale,
            sales_data=sales_data,
        )

    if intent_type == FactoryIntentType.expense_entry:
        expense_data = ExpenseIntentData(
            category=extract_expense_category(message),
            description=extract_expense_description(message),
            amount=extract_first_float(
                message,
                [
                    r"(?:expense|kharcha|paid|amount|rs|inr|rupees|rupaye)\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)",
                    r"\b(\d+(?:\.\d+)?)\s*(?:rs|inr|rupees|rupaye)\b",
                ],
            ),
            payment_method=None,
        )
        return FactoryIntent(intent_type=intent_type, expense_data=expense_data)

    if intent_type == FactoryIntentType.employee_entry:
        return FactoryIntent(
            intent_type=intent_type,
            employee_data=extract_employee_data(message),
        )

    if intent_type == FactoryIntentType.general_qa:
        general_data = GeneralQAData(
            question=message,
            answer="I can help with production, sales, expenses, inventory, and customer balance questions.",
        )
        tool_name = SupervisorToolName.check_inventory if "stock" in message.lower() else None
        return FactoryIntent(intent_type=intent_type, tool_name=tool_name, general_data=general_data)

    production_data = ProductionIntentData(
        product_name=f"{cup_size_ml}ml Paper Cup" if cup_size_ml is not None else None,
        cup_size_ml=cup_size_ml,
        packing_profile_name=packing_profile_name,
        quantity=extract_first_int(message, [r"\b(\d+)\s*(?:box|boxes)\b"]),
        boxes_produced=extract_first_int(message, [r"\b(\d+)\s*(?:box|boxes)\b"]),
        blank_used=extract_first_int(message, [r"(?:blank|blanks)\s*(?:used)?\s*(\d+)"]),
        bottom_used=extract_first_float(message, [r"(?:bottom)\s*(?:used)?\s*(\d+(?:\.\d+)?)\s*kg?"]),
        blank_waste=extract_first_int(message, [r"(?:blank|blanks)\s*waste\s*(\d+)"]),
        bottom_waste=extract_first_float(message, [r"(?:bottom)\s*waste\s*(\d+(?:\.\d+)?)\s*kg?"]),
    )
    return FactoryIntent(
        intent_type=intent_type,
        tool_name=SupervisorToolName.log_production,
        production_data=production_data,
    )


MONEY_QUANT = Decimal("0.01")
QTY_QUANT = Decimal("0.001")


def to_money(value: Optional[int | float | Decimal]) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def to_quantity(value: Optional[int | float | Decimal]) -> Decimal:
    return Decimal(str(value or 0)).quantize(QTY_QUANT, rounding=ROUND_HALF_UP)


def require_positive_int(value: Optional[int], field_name: str) -> int:
    if value is None or value <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} is required and must be greater than zero",
        )
    return value


def require_text(value: Optional[str], field_name: str) -> str:
    if value is None or not value.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} is required",
        )
    return value.strip()


def seed_default_users(db: Session):
    factory_name = os.getenv("DEFAULT_FACTORY_NAME") or "Default Factory"
    factory = (
        db.query(Factory)
        .filter(sql_func.lower(Factory.name) == factory_name.lower())
        .first()
    )
    if factory is None:
        factory = Factory(name=factory_name)
        db.add(factory)
        db.flush()

    owner_password = os.getenv("DEFAULT_OWNER_PASSWORD")
    operator_password = os.getenv("DEFAULT_OPERATOR_PASSWORD")
    missing_password_envs = [
        env_name
        for env_name, value in (
            ("DEFAULT_OWNER_PASSWORD", owner_password),
            ("DEFAULT_OPERATOR_PASSWORD", operator_password),
        )
        if not value
    ]
    if missing_password_envs:
        raise RuntimeError(
            "Missing required user bootstrap environment variables: "
            + ", ".join(missing_password_envs)
        )
    assert owner_password is not None
    assert operator_password is not None

    defaults = [
        (
            os.getenv("DEFAULT_OWNER_USERNAME") or "owner",
            owner_password,
            "Owner",
        ),
        (
            os.getenv("DEFAULT_OPERATOR_USERNAME") or "operator",
            operator_password,
            "Operator",
        ),
    ]

    for username, password, role in defaults:
        if get_user_by_username(db, username) is None:
            db.add(
                User(
                    factory_id=factory.id,
                    username=username,
                    password_hash=hash_password(password),
                    role=role,
                )
            )
    db.commit()


def verify_n8n_api_key(x_n8n_api_key: Optional[str] = Header(default=None)) -> None:
    expected_api_key = os.getenv("N8N_API_KEY")
    if not expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="N8N_API_KEY is not configured",
        )
    if not x_n8n_api_key or not hmac.compare_digest(x_n8n_api_key, expected_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing n8n API key",
        )


def get_n8n_factory_id(
    x_factory_id: Optional[int] = Header(default=None),
    db: Session = Depends(get_db),
    _: None = Depends(verify_n8n_api_key),
) -> int:
    if x_factory_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Factory-Id header is required for n8n requests",
        )
    factory_exists = db.query(Factory.id).filter(Factory.id == x_factory_id).first()
    if factory_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Factory not found",
        )
    return x_factory_id


def build_n8n_test_webhook_url() -> str:
    webhook_url = (os.getenv("N8N_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="N8N_WEBHOOK_URL is not configured",
        )
    if webhook_url.rstrip("/").endswith("/test-ai"):
        return webhook_url
    return f"{webhook_url.rstrip('/')}/test-ai"


@app.post("/api/n8n/test")
async def test_n8n_webhook(payload: N8NTestRequest):
    api_key = os.getenv("N8N_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="N8N_API_KEY is not configured",
        )

    webhook_url = build_n8n_test_webhook_url()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                webhook_url,
                json=payload.model_dump(),
                headers={"x-api-key": api_key},
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not connect to n8n webhook: {exc}",
        ) from exc

    try:
        return JSONResponse(content=response.json(), status_code=response.status_code)
    except ValueError:
        return Response(
            content=response.text,
            status_code=response.status_code,
            media_type=response.headers.get("content-type") or "text/plain",
        )


def ensure_runtime_schema():
    default_factory_name = (os.getenv("DEFAULT_FACTORY_NAME") or "Default Factory").replace("'", "''")
    tenant_tables = [
        "users",
        "factory_inventory",
        "machines",
        "factory_settings",
        "customers",
        "customer_activities",
        "inventory",
        "raw_materials",
        "packaging_profiles",
        "production_logs",
        "finished_goods_stock",
        "expense_logs",
        "factory_expenses",
        "employees",
        "workers",
        "attendance_logs",
        "advance_payments",
        "orders",
        "order_items",
        "sales_invoices",
        "hisab_settlements",
        "material_yields",
        "costing_master",
        "payments",
        "worker_opening_attendance",
    ]
    statements = [
        (
            "CREATE TABLE IF NOT EXISTS factories ("
            "id SERIAL PRIMARY KEY, "
            "name VARCHAR(255) NOT NULL UNIQUE, "
            "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        "CREATE INDEX IF NOT EXISTS ix_factories_id ON factories (id)",
        "CREATE INDEX IF NOT EXISTS ix_factories_name ON factories (name)",
        "CREATE INDEX IF NOT EXISTS ix_factories_created_at ON factories (created_at)",
        f"INSERT INTO factories (name) VALUES ('{default_factory_name}') ON CONFLICT (name) DO NOTHING",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS factory_name VARCHAR(255)",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS owner_id INTEGER",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS trial_start_date TIMESTAMP WITH TIME ZONE DEFAULT NOW()",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS trial_end_date TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '7 days')",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(50) NOT NULL DEFAULT 'trial_active'",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS active_plan VARCHAR(50)",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS plan_name VARCHAR(50) NOT NULL DEFAULT 'Free Trial'",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS billing_cycle VARCHAR(20)",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS subscription_start_date TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS subscription_end_date TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS subscription_start TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS subscription_end TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS payment_status VARCHAR(50) NOT NULL DEFAULT 'payment_pending'",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS address TEXT",
        "ALTER TABLE factories DROP CONSTRAINT IF EXISTS ck_factories_subscription_status",
        (
            "ALTER TABLE factories ADD CONSTRAINT ck_factories_subscription_status "
            "CHECK (subscription_status IN ('trial_active', 'trial_expired', 'active', 'inactive', 'expired', 'cancelled', 'payment_pending', 'trial', 'suspended'))"
        ),
        "UPDATE factories SET subscription_status = 'trial_active' WHERE subscription_status = 'trial'",
        (
            "UPDATE factories SET subscription_status = 'trial_expired', payment_status = 'payment_pending' "
            "WHERE subscription_status = 'expired' AND subscription_end_date IS NULL"
        ),
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS razorpay_customer_id VARCHAR(255)",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS razorpay_subscription_id VARCHAR(255)",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS telegram_bot_token VARCHAR(255)",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS telegram_token VARCHAR(500)",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR(255)",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS telegram_bot_username VARCHAR(255)",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS subscription_override BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS plan_expires_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS override_plan VARCHAR",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS override_expires_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS override_reason TEXT",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS override_updated_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS usage_limit INTEGER",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS token_limit INTEGER",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS admin_note TEXT",
        "UPDATE factories SET plan_name = COALESCE(active_plan, 'Free Trial') WHERE plan_name IS NULL",
        "UPDATE factories SET subscription_start = subscription_start_date WHERE subscription_start IS NULL AND subscription_start_date IS NOT NULL",
        "UPDATE factories SET subscription_end = subscription_end_date WHERE subscription_end IS NULL AND subscription_end_date IS NOT NULL",
        (
            "CREATE TABLE IF NOT EXISTS custom_plan_enquiries ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER REFERENCES factories(id), "
            "owner_name VARCHAR(255) NOT NULL, "
            "factory_name VARCHAR(255) NOT NULL, "
            "phone VARCHAR(50) NOT NULL, "
            "email VARCHAR(255) NOT NULL, "
            "number_of_machines INTEGER NOT NULL, "
            "requirement_details TEXT NOT NULL, "
            "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS demo_booking_requests ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER REFERENCES factories(id), "
            "owner_name VARCHAR(255) NOT NULL, "
            "factory_name VARCHAR(255), "
            "phone VARCHAR(50) NOT NULL, "
            "email VARCHAR(255) NOT NULL, "
            "preferred_plan VARCHAR(50), "
            "message TEXT, "
            "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS subscription_payments ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "plan_code VARCHAR(50) NOT NULL, "
            "billing_cycle VARCHAR(20) NOT NULL, "
            "amount_paise INTEGER NOT NULL, "
            "currency VARCHAR(10) NOT NULL DEFAULT 'INR', "
            "payment_status VARCHAR(50) NOT NULL DEFAULT 'paid', "
            "provider VARCHAR(50), "
            "provider_payment_id VARCHAR(255), "
            "subscription_start_date TIMESTAMP WITH TIME ZONE NOT NULL, "
            "subscription_end_date TIMESTAMP WITH TIME ZONE NOT NULL, "
            "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS super_admin_audit_logs ("
            "id SERIAL PRIMARY KEY, "
            "admin_email VARCHAR(255) NOT NULL, "
            "action_type VARCHAR(100) NOT NULL, "
            "entity_type VARCHAR(100) NOT NULL, "
            "entity_id VARCHAR(100), "
            "old_value JSONB, "
            "new_value JSONB, "
            "note TEXT, "
            "ip_address VARCHAR(100), "
            "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS app_usage_logs ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "user_id INTEGER REFERENCES users(id), "
            "event_type VARCHAR(100) NOT NULL, "
            "route_or_module VARCHAR(255), "
            "method VARCHAR(20), "
            "meta JSONB, "
            "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS token_usage_logs ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "user_id INTEGER REFERENCES users(id), "
            "provider VARCHAR(100), "
            "model VARCHAR(255), "
            "feature_name VARCHAR(255) NOT NULL, "
            "prompt_tokens INTEGER, "
            "completion_tokens INTEGER, "
            "total_tokens INTEGER, "
            "estimated_cost NUMERIC(14, 6), "
            "meta JSONB, "
            "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        "CREATE INDEX IF NOT EXISTS ix_custom_plan_enquiries_factory_id ON custom_plan_enquiries (factory_id)",
        "CREATE INDEX IF NOT EXISTS ix_demo_booking_requests_factory_id ON demo_booking_requests (factory_id)",
        "CREATE INDEX IF NOT EXISTS ix_subscription_payments_factory_id ON subscription_payments (factory_id)",
        "CREATE INDEX IF NOT EXISTS ix_super_admin_audit_logs_created_at ON super_admin_audit_logs (created_at)",
        "CREATE INDEX IF NOT EXISTS ix_super_admin_audit_logs_entity ON super_admin_audit_logs (entity_type, entity_id)",
        "CREATE INDEX IF NOT EXISTS ix_app_usage_logs_factory_id ON app_usage_logs (factory_id)",
        "CREATE INDEX IF NOT EXISTS ix_app_usage_logs_user_id ON app_usage_logs (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_app_usage_logs_created_at ON app_usage_logs (created_at)",
        "CREATE INDEX IF NOT EXISTS ix_token_usage_logs_factory_id ON token_usage_logs (factory_id)",
        "CREATE INDEX IF NOT EXISTS ix_token_usage_logs_user_id ON token_usage_logs (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_token_usage_logs_created_at ON token_usage_logs (created_at)",
        "CREATE INDEX IF NOT EXISTS ix_factories_subscription_end_date ON factories (subscription_end_date)",
        "CREATE INDEX IF NOT EXISTS ix_factories_subscription_end ON factories (subscription_end)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
        "UPDATE factories SET factory_name = name WHERE factory_name IS NULL",
        (
            "CREATE TABLE IF NOT EXISTS machines ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "name VARCHAR(255) NOT NULL, "
            "machine_type VARCHAR(50) NOT NULL DEFAULT 'Paper Cup', "
            "machine_number VARCHAR(50), "
            "mould_size_ml INTEGER, "
            "machine_sequence_number VARCHAR(50), "
            "speed_per_minute INTEGER NOT NULL DEFAULT 0, "
            "speed_bpm INTEGER NOT NULL DEFAULT 0, "
            "speed_cups_per_minute INTEGER NOT NULL DEFAULT 0, "
            "cup_size_ml INTEGER, "
            "bottom_size_mm INTEGER, "
            "default_mould_size VARCHAR(100), "
            "current_mould_size VARCHAR(100), "
            "bottom_size VARCHAR(100), "
            "current_bottom_size VARCHAR(100), "
            "can_swap_moulds BOOLEAN NOT NULL DEFAULT false"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS factory_settings ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "last_month_electricity_bill NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "number_of_machines INTEGER NOT NULL DEFAULT 0, "
            "default_shift_hours DOUBLE PRECISION NOT NULL DEFAULT 8.0"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS raw_materials ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "name VARCHAR(255) NOT NULL, "
            "material_type VARCHAR(50) NOT NULL, "
            "type VARCHAR(50), "
            "size_name VARCHAR(100), "
            "size_ml INTEGER, "
            "gsm INTEGER, "
            "unit VARCHAR(50) NOT NULL, "
            "opening_stock NUMERIC(14, 3) NOT NULL DEFAULT 0, "
            "current_stock NUMERIC(14, 3) NOT NULL DEFAULT 0, "
            "stock_quantity NUMERIC(14, 3) NOT NULL DEFAULT 0, "
            "price_per_unit NUMERIC(14, 2) NOT NULL DEFAULT 0"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS workers ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "name VARCHAR(255) NOT NULL, "
            "salary NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "daily_salary NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "shift_hours DOUBLE PRECISION NOT NULL DEFAULT 8.0, "
            "shift_timing VARCHAR(100), "
            "shift_type VARCHAR(100)"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS material_yields ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "material_type VARCHAR(50) NOT NULL, "
            "size_ml INTEGER NOT NULL, "
            "gsm INTEGER, "
            "pieces_per_kg NUMERIC(14, 3) NOT NULL"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS costing_master ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "paper_price_per_kg NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "bottom_roll_price_per_kg NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "polybag_price NUMERIC(14, 4) NOT NULL DEFAULT 0, "
            "carton_price NUMERIC(14, 4) NOT NULL DEFAULT 0, "
            "labour_cost_per_box NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "electricity_cost_per_box NUMERIC(14, 2) NOT NULL DEFAULT 0"
            ")"
        ),
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(50) NOT NULL DEFAULT 'Operator'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS user_id VARCHAR(36)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number VARCHAR(50)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number_normalized VARCHAR(50)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_id VARCHAR(100)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP WITH TIME ZONE",
        "UPDATE users SET email = username WHERE email IS NULL AND username LIKE '%@%'",
        (
            "UPDATE users SET phone_number_normalized = CASE "
            "WHEN phone_number LIKE '+971%' THEN regexp_replace(substr(phone_number, 5), '\\D', '', 'g') "
            "WHEN phone_number LIKE '+91%' THEN regexp_replace(substr(phone_number, 4), '\\D', '', 'g') "
            "WHEN phone_number LIKE '+44%' THEN regexp_replace(substr(phone_number, 4), '\\D', '', 'g') "
            "WHEN phone_number LIKE '+1%' THEN regexp_replace(substr(phone_number, 3), '\\D', '', 'g') "
            "ELSE regexp_replace(phone_number, '\\D', '', 'g') END "
            "WHERE phone_number IS NOT NULL AND (phone_number_normalized IS NULL OR phone_number_normalized = regexp_replace(phone_number, '\\D', '', 'g'))"
        ),
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users (email) WHERE email IS NOT NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_user_id ON users (user_id) WHERE user_id IS NOT NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone_number ON users (phone_number) WHERE phone_number IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS ix_users_phone_number_normalized ON users (phone_number_normalized) WHERE phone_number_normalized IS NOT NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_telegram_id ON users (telegram_id) WHERE telegram_id IS NOT NULL",
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role",
        "UPDATE users SET role = 'Operator' WHERE role = 'Worker'",
        "ALTER TABLE users ADD CONSTRAINT ck_users_role CHECK (role IN ('Owner', 'Sub-Owner', 'Supervisor', 'Operator'))",
        (
            "CREATE TABLE IF NOT EXISTS factory_expenses ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "expense_name VARCHAR(255) NOT NULL, "
            "amount NUMERIC(14, 2) NOT NULL, "
            "category VARCHAR(100) NOT NULL DEFAULT 'General', "
            "timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS machine_templates ("
            "id SERIAL PRIMARY KEY, "
            "creator_id INTEGER NOT NULL REFERENCES users(id), "
            "machine_type VARCHAR(100) NOT NULL, "
            "base_config JSONB NOT NULL DEFAULT '{}', "
            "custom_fields JSONB NOT NULL DEFAULT '{}', "
            "status VARCHAR(20) NOT NULL DEFAULT 'processing', "
            "ai_confidence DOUBLE PRECISION, "
            "ai_review JSONB NOT NULL DEFAULT '{}', "
            "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(), "
            "updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        "CREATE INDEX IF NOT EXISTS ix_factory_expenses_factory_id ON factory_expenses (factory_id)",
        "CREATE INDEX IF NOT EXISTS ix_factory_expenses_timestamp ON factory_expenses (timestamp)",
        "ALTER TABLE factory_expenses DROP CONSTRAINT IF EXISTS ck_factory_expenses_amount_non_negative",
        "ALTER TABLE factory_expenses ADD CONSTRAINT ck_factory_expenses_amount_non_negative CHECK (amount >= 0)",
        "ALTER TABLE machines ADD COLUMN IF NOT EXISTS machine_type VARCHAR(50) NOT NULL DEFAULT 'Paper Cup'",
        "ALTER TABLE machines ADD COLUMN IF NOT EXISTS machine_number VARCHAR(50)",
        "ALTER TABLE machines ADD COLUMN IF NOT EXISTS mould_size_ml INTEGER",
        "ALTER TABLE machines ADD COLUMN IF NOT EXISTS machine_sequence_number VARCHAR(50)",
        "ALTER TABLE machines ADD COLUMN IF NOT EXISTS speed_cups_per_minute INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE machines ADD COLUMN IF NOT EXISTS cup_size_ml INTEGER",
        "ALTER TABLE machines ADD COLUMN IF NOT EXISTS bottom_size_mm INTEGER",
        "UPDATE machines SET machine_number = machine_sequence_number WHERE machine_number IS NULL AND machine_sequence_number IS NOT NULL",
        "UPDATE machines SET mould_size_ml = cup_size_ml WHERE mould_size_ml IS NULL AND cup_size_ml IS NOT NULL",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS contact_number VARCHAR(50)",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS telegram_id VARCHAR(100)",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS address TEXT",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS phone VARCHAR(50)",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS previous_due NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS total_due NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "UPDATE customers SET phone = contact_number WHERE phone IS NULL AND contact_number IS NOT NULL",
        "UPDATE customers SET total_due = COALESCE(balance_amount, pending_balance, 0) WHERE total_due = 0",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS firm_name VARCHAR(255)",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS store_token VARCHAR(255)",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS is_portal_approved BOOLEAN NOT NULL DEFAULT false",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS portal_access_token VARCHAR(255)",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS last_balance_update TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS last_whatsapp_reminder_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS advance_discount_pct DOUBLE PRECISION NOT NULL DEFAULT 5.0",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS pending_dues DOUBLE PRECISION NOT NULL DEFAULT 0",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS pending_balance NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_store_token ON customers (store_token) WHERE store_token IS NOT NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_portal_access_token ON customers (portal_access_token) WHERE portal_access_token IS NOT NULL",
        (
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'orders' AND column_name = 'payment_type') "
            "AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'orders' AND column_name = 'payment_method') "
            "THEN ALTER TABLE orders RENAME COLUMN payment_type TO payment_method; "
            "END IF; END $$"
        ),
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_discount_revoked BOOLEAN NOT NULL DEFAULT false",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS owner_confirmed_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS amount_paid NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS balance_amount NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS base_rate NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE order_items ALTER COLUMN product_id DROP NOT NULL",
        "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS product_size_ml INTEGER",
        "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS variety VARCHAR(100)",
        "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS packaging_size_name VARCHAR(100)",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_status VARCHAR(50) NOT NULL DEFAULT 'Unpaid'",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS pending_amount NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "CREATE INDEX IF NOT EXISTS ix_orders_payment_status ON orders (payment_status)",
        "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS boxes_sold INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS loose_packets_sold INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS rate_per_box NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS rate_per_packet NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders_payment_type",
        "ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders_payment_method",
        "ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders_status",
        "UPDATE orders SET payment_method = 'Full_Advance_Doorstep' WHERE payment_method = 'Advance'",
        "UPDATE orders SET payment_method = 'Normal_Credit' WHERE payment_method = 'Credit'",
        "UPDATE order_items SET base_rate = final_rate WHERE base_rate = 0",
        (
            "ALTER TABLE orders ADD CONSTRAINT ck_orders_status "
            "CHECK (status IN ('pending_owner', 'confirmed', 'cancelled', 'adjusted_closed', 'Pending', 'Approved', 'Rejected'))"
        ),
        "UPDATE orders SET balance_amount = GREATEST(total_amount - amount_paid, 0) WHERE balance_amount = 0 AND total_amount > 0",
        (
            "ALTER TABLE orders ADD CONSTRAINT ck_orders_payment_method "
            "CHECK (payment_method IN ('Normal_Credit', 'Full_Advance_UPI', 'Full_Advance_Doorstep'))"
        ),
        "ALTER TABLE order_items DROP CONSTRAINT IF EXISTS ck_order_items_base_rate_non_negative",
        "ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders_amount_paid_non_negative",
        "ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders_balance_amount_non_negative",
        "ALTER TABLE order_items DROP CONSTRAINT IF EXISTS ck_order_items_boxes_sold_non_negative",
        "ALTER TABLE order_items DROP CONSTRAINT IF EXISTS ck_order_items_loose_packets_sold_non_negative",
        "ALTER TABLE order_items DROP CONSTRAINT IF EXISTS ck_order_items_rate_per_box_non_negative",
        "ALTER TABLE order_items DROP CONSTRAINT IF EXISTS ck_order_items_rate_per_packet_non_negative",
        (
            "ALTER TABLE order_items ADD CONSTRAINT ck_order_items_base_rate_non_negative "
            "CHECK (base_rate >= 0)"
        ),
        "ALTER TABLE orders ADD CONSTRAINT ck_orders_amount_paid_non_negative CHECK (amount_paid >= 0)",
        "ALTER TABLE orders ADD CONSTRAINT ck_orders_balance_amount_non_negative CHECK (balance_amount >= 0)",
        "ALTER TABLE order_items ADD CONSTRAINT ck_order_items_boxes_sold_non_negative CHECK (boxes_sold >= 0)",
        "ALTER TABLE order_items ADD CONSTRAINT ck_order_items_loose_packets_sold_non_negative CHECK (loose_packets_sold >= 0)",
        "ALTER TABLE order_items ADD CONSTRAINT ck_order_items_rate_per_box_non_negative CHECK (rate_per_box >= 0)",
        "ALTER TABLE order_items ADD CONSTRAINT ck_order_items_rate_per_packet_non_negative CHECK (rate_per_packet >= 0)",
        "ALTER TABLE production_logs ADD COLUMN IF NOT EXISTS box_packing_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE production_logs ADD COLUMN IF NOT EXISTS poly_packing_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE production_logs ADD COLUMN IF NOT EXISTS total_packing_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE production_logs ADD COLUMN IF NOT EXISTS blank_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE production_logs ADD COLUMN IF NOT EXISTS bottom_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE production_logs ADD COLUMN IF NOT EXISTS total_raw_material_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE production_logs ADD COLUMN IF NOT EXISTS total_production_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE packaging_profiles ADD COLUMN IF NOT EXISTS product_name VARCHAR(255)",
        "ALTER TABLE packaging_profiles ADD COLUMN IF NOT EXISTS product_name_ml INTEGER",
        "ALTER TABLE packaging_profiles ADD COLUMN IF NOT EXISTS image_url VARCHAR(1000)",
        "ALTER TABLE packaging_profiles ADD COLUMN IF NOT EXISTS print_design_name VARCHAR(255)",
        "ALTER TABLE packaging_profiles ADD COLUMN IF NOT EXISTS polybag_capacity INTEGER",
        "ALTER TABLE packaging_profiles ADD COLUMN IF NOT EXISTS box_capacity INTEGER",
        "ALTER TABLE packaging_profiles ADD COLUMN IF NOT EXISTS box_size_name VARCHAR(100)",
        "ALTER TABLE packaging_profiles ADD COLUMN IF NOT EXISTS cups_per_polybag INTEGER",
        "ALTER TABLE packaging_profiles ADD COLUMN IF NOT EXISTS polybags_per_box INTEGER",
        "ALTER TABLE machines ADD COLUMN IF NOT EXISTS speed_bpm INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE machines ADD COLUMN IF NOT EXISTS current_mould_size VARCHAR(100)",
        "ALTER TABLE machines ADD COLUMN IF NOT EXISTS current_bottom_size VARCHAR(100)",
        "ALTER TABLE machine_templates ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'processing'",
        "ALTER TABLE machine_templates ADD COLUMN IF NOT EXISTS ai_confidence DOUBLE PRECISION",
        "ALTER TABLE machine_templates ADD COLUMN IF NOT EXISTS ai_review JSONB NOT NULL DEFAULT '{}'",
        "ALTER TABLE machine_templates DROP CONSTRAINT IF EXISTS ck_machine_templates_status",
        "ALTER TABLE machine_templates ADD CONSTRAINT ck_machine_templates_status CHECK (status IN ('processing', 'pending', 'approved', 'rejected'))",
        "CREATE INDEX IF NOT EXISTS ix_machine_templates_status ON machine_templates (status)",
        "CREATE INDEX IF NOT EXISTS ix_machine_templates_machine_type ON machine_templates (machine_type)",
        "CREATE INDEX IF NOT EXISTS ix_machine_templates_creator_id ON machine_templates (creator_id)",
        "CREATE INDEX IF NOT EXISTS ix_machine_templates_custom_fields_gin ON machine_templates USING GIN (custom_fields)",
        "ALTER TABLE raw_materials ADD COLUMN IF NOT EXISTS type VARCHAR(50)",
        "ALTER TABLE raw_materials ADD COLUMN IF NOT EXISTS size_ml INTEGER",
        "ALTER TABLE raw_materials ADD COLUMN IF NOT EXISTS gsm INTEGER",
        "ALTER TABLE raw_materials ADD COLUMN IF NOT EXISTS stock_quantity NUMERIC(14, 3) NOT NULL DEFAULT 0",
        "ALTER TABLE workers ADD COLUMN IF NOT EXISTS daily_salary NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE workers ADD COLUMN IF NOT EXISTS daily_wages NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE workers ADD COLUMN IF NOT EXISTS duty_hours DOUBLE PRECISION NOT NULL DEFAULT 8.0",
        "ALTER TABLE workers ADD COLUMN IF NOT EXISTS phone VARCHAR(50)",
        "ALTER TABLE workers ADD COLUMN IF NOT EXISTS daily_wage_rate NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "UPDATE workers SET daily_wage_rate = daily_wages WHERE daily_wage_rate = 0 AND daily_wages > 0",
        "UPDATE workers SET daily_wages = daily_salary WHERE daily_wages = 0 AND daily_salary > 0",
        "UPDATE workers SET duty_hours = shift_hours WHERE shift_hours IS NOT NULL",
        "ALTER TABLE workers ADD COLUMN IF NOT EXISTS shift_type VARCHAR(100)",
        (
            "CREATE TABLE IF NOT EXISTS blank_stock ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "blank_size_ml INTEGER NOT NULL, "
            "variety VARCHAR(100) NOT NULL DEFAULT 'Plain White', "
            "linked_bottom_size_mm INTEGER NOT NULL, "
            "total_qty_kg NUMERIC(14, 3) NOT NULL DEFAULT 0, "
            "updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS bottom_stock ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "bottom_size_mm INTEGER NOT NULL, "
            "variety VARCHAR(100) NOT NULL DEFAULT 'Plain White', "
            "total_qty_kg NUMERIC(14, 3) NOT NULL DEFAULT 0, "
            "updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS box_stock ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "packaging_size_name VARCHAR(100) NOT NULL, "
            "total_boxes INTEGER NOT NULL DEFAULT 0, "
            "updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS polybag_stock ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "packaging_size_name VARCHAR(100) NOT NULL, "
            "total_packets INTEGER NOT NULL DEFAULT 0, "
            "updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS final_product_stock ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "product_size_ml INTEGER NOT NULL, "
            "packaging_size_name VARCHAR(100) NOT NULL, "
            "current_quantity INTEGER NOT NULL DEFAULT 0, "
            "total_boxes INTEGER NOT NULL DEFAULT 0, "
            "loose_packets INTEGER NOT NULL DEFAULT 0, "
            "packets_per_box_limit INTEGER NOT NULL, "
            "updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS daily_productions ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "date DATE NOT NULL, "
            "worker_id INTEGER NOT NULL REFERENCES workers(id), "
            "machine_id INTEGER NOT NULL REFERENCES machines(id), "
            "product_size_ml INTEGER NOT NULL, "
            "packaging_size_name VARCHAR(100) NOT NULL, "
            "packets_per_box_limit INTEGER NOT NULL, "
            "total_boxes_made INTEGER NOT NULL DEFAULT 0, "
            "loose_packets_made INTEGER NOT NULL DEFAULT 0, "
            "boxes_from_loose INTEGER NOT NULL DEFAULT 0, "
            "blank_used_kg NUMERIC(14, 3) NOT NULL DEFAULT 0, "
            "bottom_used_kg NUMERIC(14, 3) NOT NULL DEFAULT 0, "
            "wastage_kg NUMERIC(14, 3) NOT NULL DEFAULT 0, "
            "wastage_status VARCHAR(50) NOT NULL DEFAULT 'NORMAL', "
            "total_raw_material_kg NUMERIC(14, 3) NOT NULL DEFAULT 0, "
            "raw_material_cost NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "labor_cost NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "electricity_cost NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "production_cost NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS daily_sales ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "date DATE NOT NULL, "
            "customer_id INTEGER NOT NULL REFERENCES customers(id), "
            "product_size_ml INTEGER NOT NULL, "
            "packaging_size_name VARCHAR(100) NOT NULL, "
            "boxes_sold INTEGER NOT NULL DEFAULT 0, "
            "loose_packets_sold INTEGER NOT NULL DEFAULT 0, "
            "rate_per_box NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "rate_per_packet NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "total_amount NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "amount_paid NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "customer_phone VARCHAR(50), "
            "total_bill NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "initial_payment NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS payments ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "customer_phone VARCHAR(50) NOT NULL, "
            "sale_id INTEGER NULL REFERENCES daily_sales(id), "
            "amount_paid NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "payment_mode VARCHAR(20) NOT NULL DEFAULT 'Cash', "
            "date DATE NOT NULL, "
            "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        "ALTER TABLE daily_sales ADD COLUMN IF NOT EXISTS customer_phone VARCHAR(50)",
        "ALTER TABLE daily_sales ADD COLUMN IF NOT EXISTS total_bill NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_sales ADD COLUMN IF NOT EXISTS initial_payment NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "UPDATE daily_sales SET total_bill = total_amount WHERE total_bill = 0 AND total_amount IS NOT NULL",
        "ALTER TABLE blank_stock DROP CONSTRAINT IF EXISTS ck_blank_stock_qty_non_negative",
        "ALTER TABLE bottom_stock DROP CONSTRAINT IF EXISTS ck_bottom_stock_qty_non_negative",
        "ALTER TABLE box_stock DROP CONSTRAINT IF EXISTS ck_box_stock_total_non_negative",
        "ALTER TABLE final_product_stock DROP CONSTRAINT IF EXISTS ck_final_product_boxes_non_negative",
        "ALTER TABLE final_product_stock ADD COLUMN IF NOT EXISTS current_quantity INTEGER NOT NULL DEFAULT 0",
        "UPDATE final_product_stock SET current_quantity = total_boxes WHERE current_quantity = 0 AND total_boxes IS NOT NULL",
        "ALTER TABLE blank_stock ADD COLUMN IF NOT EXISTS variety VARCHAR(100) NOT NULL DEFAULT 'Plain White'",
        "ALTER TABLE bottom_stock ADD COLUMN IF NOT EXISTS variety VARCHAR(100) NOT NULL DEFAULT 'Plain White'",
        "ALTER TABLE daily_productions ADD COLUMN IF NOT EXISTS wastage_kg NUMERIC(14, 3) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_productions ADD COLUMN IF NOT EXISTS wastage_status VARCHAR(50) NOT NULL DEFAULT 'NORMAL'",
        "ALTER TABLE daily_productions ADD COLUMN IF NOT EXISTS total_raw_material_kg NUMERIC(14, 3) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_productions ADD COLUMN IF NOT EXISTS raw_material_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_productions ADD COLUMN IF NOT EXISTS labor_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_productions ADD COLUMN IF NOT EXISTS electricity_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE daily_productions ADD COLUMN IF NOT EXISTS production_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE attendance_logs ALTER COLUMN employee_id DROP NOT NULL",
        "ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS worker_id INTEGER REFERENCES workers(id)",
        "ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'Absent'",
        "ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS production_qty NUMERIC(14, 3)",
        "ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS is_settled BOOLEAN NOT NULL DEFAULT false",
        "ALTER TABLE attendance_logs DROP CONSTRAINT IF EXISTS ck_attendance_logs_status",
        "ALTER TABLE attendance_logs ADD CONSTRAINT ck_attendance_logs_status CHECK (status IN ('Present', 'Absent', 'Half-day'))",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_attendance_logs_factory_date_worker ON attendance_logs (factory_id, date, worker_id) WHERE worker_id IS NOT NULL",
        "ALTER TABLE advance_payments ALTER COLUMN employee_id DROP NOT NULL",
        "ALTER TABLE advance_payments ADD COLUMN IF NOT EXISTS worker_id INTEGER REFERENCES workers(id)",
        "ALTER TABLE advance_payments ADD COLUMN IF NOT EXISTS is_settled BOOLEAN NOT NULL DEFAULT false",
        (
            "CREATE TABLE IF NOT EXISTS hisab_settlements ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "worker_id INTEGER NOT NULL REFERENCES workers(id), "
            "duty_from_date DATE NOT NULL, "
            "duty_to_date DATE NOT NULL, "
            "advance_cutoff_date DATE NOT NULL, "
            "total_duty_amount NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "total_advance_deducted NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "net_paid NUMERIC(14, 2) NOT NULL DEFAULT 0, "
            "created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ),
        (
            "CREATE TABLE IF NOT EXISTS worker_opening_attendance ("
            "id SERIAL PRIMARY KEY, "
            "factory_id INTEGER NOT NULL REFERENCES factories(id), "
            "worker_id INTEGER NOT NULL REFERENCES workers(id), "
            "period_start DATE NOT NULL, "
            "period_end DATE NOT NULL, "
            "present_days NUMERIC(6,1) NOT NULL DEFAULT 0, "
            "half_days NUMERIC(6,1) NOT NULL DEFAULT 0, "
            "absent_days NUMERIC(6,1) NOT NULL DEFAULT 0, "
            "paid_leave_days NUMERIC(6,1) NOT NULL DEFAULT 0, "
            "overtime_hours NUMERIC(8,2) NOT NULL DEFAULT 0, "
            "advance_paid NUMERIC(14,2) NOT NULL DEFAULT 0, "
            "deductions NUMERIC(14,2) NOT NULL DEFAULT 0, "
            "notes TEXT, "
            "created_by_user_id INTEGER NOT NULL REFERENCES users(id), "
            "created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(), "
            "updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(), "
            "CONSTRAINT chk_period CHECK (period_start <= period_end), "
            "CONSTRAINT chk_present_days CHECK (present_days >= 0), "
            "CONSTRAINT chk_half_days CHECK (half_days >= 0), "
            "CONSTRAINT chk_absent_days CHECK (absent_days >= 0), "
            "CONSTRAINT chk_paid_leave CHECK (paid_leave_days >= 0), "
            "CONSTRAINT chk_overtime CHECK (overtime_hours >= 0), "
            "CONSTRAINT chk_advance CHECK (advance_paid >= 0), "
            "CONSTRAINT chk_deductions CHECK (deductions >= 0), "
            "CONSTRAINT uq_opening_attendance_worker UNIQUE (factory_id, worker_id)"
            ")"
        ),
    ]
    default_factory_id_sql = f"(SELECT id FROM factories WHERE name = '{default_factory_name}')"
    for table_name in tenant_tables:
        statements.extend(
            [
                f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS factory_id INTEGER",
                f"UPDATE {table_name} SET factory_id = {default_factory_id_sql} WHERE factory_id IS NULL",
                f"ALTER TABLE {table_name} ALTER COLUMN factory_id SET NOT NULL",
                f"CREATE INDEX IF NOT EXISTS ix_{table_name}_factory_id ON {table_name} (factory_id)",
            ]
        )
    statements.extend(
        [
            "ALTER TABLE customers DROP CONSTRAINT IF EXISTS customers_name_key",
            "ALTER TABLE inventory DROP CONSTRAINT IF EXISTS inventory_item_name_key",
            "ALTER TABLE inventory ADD COLUMN IF NOT EXISTS category VARCHAR(50) NOT NULL DEFAULT 'Raw'",
            "ALTER TABLE inventory ADD COLUMN IF NOT EXISTS packaging_size VARCHAR(100)",
            "ALTER TABLE inventory ADD COLUMN IF NOT EXISTS pieces_per_packet INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE inventory ADD COLUMN IF NOT EXISTS packets_per_box INTEGER NOT NULL DEFAULT 0",
            "CREATE INDEX IF NOT EXISTS ix_inventory_category ON inventory (category)",
            "CREATE INDEX IF NOT EXISTS ix_inventory_packaging_size ON inventory (packaging_size)",
            "ALTER TABLE final_product_stock ADD COLUMN IF NOT EXISTS pieces_per_packet INTEGER NOT NULL DEFAULT 1",
            "DROP INDEX IF EXISTS uq_final_product_factory_product_pack",
            "ALTER TABLE packaging_profiles DROP CONSTRAINT IF EXISTS packaging_profiles_profile_name_key",
            "ALTER TABLE employees DROP CONSTRAINT IF EXISTS employees_name_key",
            "ALTER TABLE finished_goods_stock DROP CONSTRAINT IF EXISTS uq_finished_goods_stock_packaging_profile",
            "ALTER TABLE finished_goods_stock DROP CONSTRAINT IF EXISTS finished_goods_stock_packaging_profile_id_key",
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_factory_name "
                "ON customers (factory_id, name)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_customers_factory_name_phone "
                "ON customers (factory_id, name, phone_number)"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_inventory_factory_item_name "
                "ON inventory (factory_id, item_name)"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_materials_factory_material "
                "ON raw_materials (factory_id, name, material_type, COALESCE(size_name, ''))"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_packaging_profiles_factory_profile_name "
                "ON packaging_profiles (factory_id, profile_name)"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_employees_factory_name "
                "ON employees (factory_id, name)"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_machines_factory_name "
                "ON machines (factory_id, name)"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_factory_settings_factory "
                "ON factory_settings (factory_id)"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_workers_factory_name "
                "ON workers (factory_id, name)"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_material_yields_factory_spec "
                "ON material_yields (factory_id, material_type, size_ml, COALESCE(gsm, 0))"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_costing_master_factory "
                "ON costing_master (factory_id)"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_finished_goods_stock_factory_packaging_profile "
                "ON finished_goods_stock (factory_id, packaging_profile_id)"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_blank_stock_factory_size "
                "ON blank_stock (factory_id, blank_size_ml)"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_bottom_stock_factory_size "
                "ON bottom_stock (factory_id, bottom_size_mm)"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_box_stock_factory_size "
                "ON box_stock (factory_id, packaging_size_name)"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_polybag_stock_factory_size "
                "ON polybag_stock (factory_id, packaging_size_name)"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_final_product_factory_product_pack "
                "ON final_product_stock (factory_id, product_size_ml, packaging_size_name)"
            ),
            "CREATE INDEX IF NOT EXISTS ix_daily_productions_factory_id ON daily_productions (factory_id)",
            "CREATE INDEX IF NOT EXISTS ix_daily_sales_factory_id ON daily_sales (factory_id)",
            "CREATE INDEX IF NOT EXISTS ix_orders_factory_customer_date ON orders (factory_id, customer_id, order_date DESC)",
        ]
    )

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def get_packaging_profile(
    db: Session,
    factory_id: int,
    packing_profile_name: str,
    cup_size_ml: Optional[int],
) -> PackagingProfile:
    profile = (
        db.query(PackagingProfile)
        .filter(PackagingProfile.factory_id == factory_id)
        .filter(sql_func.lower(PackagingProfile.profile_name) == packing_profile_name.lower())
        .first()
    )

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Packaging profile not found: {packing_profile_name}",
        )

    if cup_size_ml is not None and profile.cup_size_ml != cup_size_ml:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Packaging profile {profile.profile_name} is for {profile.cup_size_ml}ml, "
                f"but parsed cup size was {cup_size_ml}ml"
            ),
        )

    return profile


def product_search_terms(product_name: Optional[str], cup_size_ml: Optional[int]) -> List[str]:
    terms: List[str] = []
    if product_name:
        terms.append(product_name.strip())
        size_match = re.search(r"\b(\d{2,4})\s*ml\b", product_name, flags=re.IGNORECASE)
        if size_match:
            terms.append(f"{size_match.group(1)}ml")
    if cup_size_ml:
        terms.append(f"{cup_size_ml}ml")
    return [term for term in dict.fromkeys(terms) if term]


def find_product_stock(
    db: Session,
    factory_id: int,
    product_name: Optional[str] = None,
    cup_size_ml: Optional[int] = None,
) -> Optional[Tuple[FinishedGoodsStock, PackagingProfile]]:
    query = (
        db.query(FinishedGoodsStock, PackagingProfile)
        .join(PackagingProfile, FinishedGoodsStock.packaging_profile_id == PackagingProfile.id)
        .filter(FinishedGoodsStock.factory_id == factory_id)
        .filter(PackagingProfile.factory_id == factory_id)
    )
    if cup_size_ml is not None:
        query = query.filter(PackagingProfile.cup_size_ml == cup_size_ml)

    terms = product_search_terms(product_name, cup_size_ml)
    if terms and cup_size_ml is None:
        name_filters = [
            sql_func.lower(PackagingProfile.profile_name).like(f"%{term.lower()}%")
            for term in terms
        ]
        if name_filters:
            query = query.filter(*name_filters[:1])

    return query.order_by(FinishedGoodsStock.updated_at.desc(), FinishedGoodsStock.id.asc()).first()


def find_packaging_profile_for_product(
    db: Session,
    factory_id: int,
    product_name: Optional[str] = None,
    cup_size_ml: Optional[int] = None,
) -> Optional[PackagingProfile]:
    query = db.query(PackagingProfile).filter(PackagingProfile.factory_id == factory_id)
    if cup_size_ml is not None:
        query = query.filter(PackagingProfile.cup_size_ml == cup_size_ml)

    terms = product_search_terms(product_name, cup_size_ml)
    if terms and cup_size_ml is None:
        query = query.filter(sql_func.lower(PackagingProfile.profile_name).like(f"%{terms[0].lower()}%"))

    return query.order_by(PackagingProfile.id.asc()).first()


def resolve_production_packaging_profile(
    db: Session,
    factory_id: int,
    data: ProductionIntentData,
) -> PackagingProfile:
    if data.packing_profile_name:
        return get_packaging_profile(db, factory_id, data.packing_profile_name, data.cup_size_ml)

    profile = find_packaging_profile_for_product(db, factory_id, data.product_name, data.cup_size_ml)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{data.product_name or data.cup_size_ml or 'Product'} ki packing details nahi mili. "
                "Kya main standard 100pcs/box maan lu ya aap naya profile banayenge?"
            ),
        )
    return profile


def deduct_inventory(inventory_item: Inventory, quantity_needed: Decimal, usage_label: str):
    available_quantity = to_quantity(inventory_item.quantity)
    if available_quantity < quantity_needed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Insufficient {usage_label}: {inventory_item.item_name}. "
                f"Required {quantity_needed}, available {available_quantity}"
            ),
        )

    inventory_item.quantity = available_quantity - quantity_needed


def get_raw_inventory(db: Session, factory_id: int, keyword: str, unit: str) -> Inventory:
    inventory_item = (
        db.query(Inventory)
        .filter(Inventory.factory_id == factory_id)
        .filter(Inventory.category == "Raw")
        .filter(Inventory.unit == unit)
        .filter(sql_func.lower(Inventory.item_name).like(f"%{keyword.lower()}%"))
        .order_by(Inventory.id.asc())
        .first()
    )

    if inventory_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Raw inventory item containing '{keyword}' with unit '{unit}' was not found",
        )

    return inventory_item


def get_or_create_finished_goods_stock(
    db: Session,
    factory_id: int,
    profile: PackagingProfile,
) -> FinishedGoodsStock:
    stock = (
        db.query(FinishedGoodsStock)
        .filter(FinishedGoodsStock.factory_id == factory_id)
        .filter(FinishedGoodsStock.packaging_profile_id == profile.id)
        .first()
    )
    if stock is not None:
        return stock

    stock = FinishedGoodsStock(
        factory_id=factory_id,
        cup_size_ml=profile.cup_size_ml,
        packaging_profile_id=profile.id,
        boxes_available=0,
    )
    db.add(stock)
    db.flush()
    return stock


def get_or_create_customer(db: Session, factory_id: int, customer_name: str) -> Customer:
    customer = (
        db.query(Customer)
        .filter(Customer.factory_id == factory_id)
        .filter(sql_func.lower(Customer.name) == customer_name.lower())
        .first()
    )
    if customer is not None:
        return customer

    customer = Customer(factory_id=factory_id, name=customer_name, balance_amount=Decimal("0.00"))
    db.add(customer)
    db.flush()
    return customer


STOREFRONT_TERMS_AND_CONDITIONS = (
    "All B2B orders are subject to factory approval. Advance orders receive the configured customer discount. "
    "Credit orders may be approved or rejected based on the customer's balance and credit terms. "
    "Pending orders reserve stock until the factory approves or rejects the order."
)

UPI_PAYMENT_DETAILS = {
    "bank_name": "Demo Cooperative Bank",
    "account_name": "AI ERP Paper Cup Factory",
    "account_number": "000111222333",
    "ifsc": "DEMO0001234",
    "upi_id": "paper-cup-factory@upi",
}


def dispatch_order_confirmation_webhook(payload: Dict[str, object]) -> None:
    webhook_url = os.getenv("N8N_ORDER_CONFIRMATION_WEBHOOK") or "http://n8n:5678/webhook/order-confirmation"
    body = json.dumps(payload, default=str).encode("utf-8")
    request = urlrequest.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(request, timeout=5) as response:
            response.read()
    except URLError:
        return


def get_store_customer(db: Session, store_token: str) -> Customer:
    customer = (
        db.query(Customer)
        .filter((Customer.portal_access_token == store_token) | (Customer.store_token == store_token))
        .first()
    )
    if customer is not None and customer.is_portal_approved:
        return customer

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied",
    )


def calculate_finished_goods_base_price(db: Session, stock: FinishedGoodsStock) -> Decimal:
    latest_sale = (
        db.query(SalesInvoice)
        .filter(SalesInvoice.factory_id == stock.factory_id)
        .filter(SalesInvoice.packaging_profile_id == stock.packaging_profile_id)
        .filter(SalesInvoice.boxes_sold > 0)
        .filter(SalesInvoice.total_amount > 0)
        .order_by(SalesInvoice.date.desc(), SalesInvoice.id.desc())
        .first()
    )
    if latest_sale is not None:
        return to_money(to_money(latest_sale.total_amount) / Decimal(latest_sale.boxes_sold))

    latest_production = (
        db.query(ProductionLog)
        .filter(ProductionLog.factory_id == stock.factory_id)
        .filter(ProductionLog.packaging_profile_id == stock.packaging_profile_id)
        .filter(ProductionLog.boxes_produced > 0)
        .filter(ProductionLog.total_production_cost > 0)
        .order_by(ProductionLog.date.desc(), ProductionLog.id.desc())
        .first()
    )
    if latest_production is not None:
        return to_money(to_money(latest_production.total_production_cost) / Decimal(latest_production.boxes_produced))

    return Decimal("0.00")


def get_availability_status(boxes_available: int) -> str:
    if boxes_available <= 0:
        return "Out of Stock"
    if boxes_available < 10:
        return "Low Stock"
    if boxes_available > 50:
        return "In Stock"
    return "In Stock"


def normalize_store_payment_method(payment_method: str) -> str:
    normalized_payment_method = payment_method.strip()
    aliases = {
        "normal_credit": "Normal_Credit",
        "credit": "Normal_Credit",
        "full_advance_upi": "Full_Advance_UPI",
        "upi": "Full_Advance_UPI",
        "full_advance_doorstep": "Full_Advance_Doorstep",
        "doorstep": "Full_Advance_Doorstep",
        "advance": "Full_Advance_Doorstep",
    }
    normalized_key = normalized_payment_method.lower().replace("-", "_").replace(" ", "_")
    normalized_payment_method = aliases.get(normalized_key, normalized_payment_method)
    if normalized_payment_method not in {"Normal_Credit", "Full_Advance_UPI", "Full_Advance_Doorstep"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="payment_method must be one of: Normal_Credit, Full_Advance_UPI, Full_Advance_Doorstep",
        )
    return normalized_payment_method


def get_employee_by_name(db: Session, factory_id: int, employee_name: str) -> Employee:
    employee = (
        db.query(Employee)
        .filter(Employee.factory_id == factory_id)
        .filter(sql_func.lower(Employee.name) == employee_name.lower())
        .first()
    )
    if employee is not None:
        return employee

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Employee not found: {employee_name}",
    )


def execute_production_entry(db: Session, factory_id: int, data: ProductionIntentData) -> BusinessExecutionResult:
    boxes_produced = require_positive_int(data.boxes_produced or data.quantity, "quantity")
    profile = resolve_production_packaging_profile(db, factory_id, data)

    if profile.box_inventory is None or profile.poly_inventory is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Packaging profile is missing linked box or poly inventory",
        )

    total_boxes_needed = boxes_produced
    total_polys_needed = boxes_produced * profile.polys_per_box

    box_quantity_needed = to_quantity(total_boxes_needed)
    poly_quantity_needed = to_quantity(total_polys_needed)
    deduct_inventory(profile.box_inventory, box_quantity_needed, "box packaging")
    deduct_inventory(profile.poly_inventory, poly_quantity_needed, "poly packaging")

    box_packing_cost = to_money(box_quantity_needed * to_money(profile.box_inventory.price_per_unit))
    poly_packing_cost = to_money(poly_quantity_needed * to_money(profile.poly_inventory.price_per_unit))
    total_packing_cost = to_money(box_packing_cost + poly_packing_cost)

    blank_used = data.blank_used or 0
    blank_waste = data.blank_waste or 0
    bottom_used = to_quantity(data.bottom_used)
    bottom_waste = to_quantity(data.bottom_waste)
    blank_consumed = to_quantity(blank_used + blank_waste)
    bottom_consumed = to_quantity(bottom_used + bottom_waste)

    blank_cost = Decimal("0.00")
    if blank_consumed > 0:
        blank_inventory = get_raw_inventory(db, factory_id, "blank", "pieces")
        deduct_inventory(blank_inventory, blank_consumed, "blank raw material")
        blank_cost = to_money(blank_consumed * to_money(blank_inventory.price_per_unit))

    bottom_cost = Decimal("0.00")
    if bottom_consumed > 0:
        bottom_inventory = get_raw_inventory(db, factory_id, "bottom", "kg")
        deduct_inventory(bottom_inventory, bottom_consumed, "bottom raw material")
        bottom_cost = to_money(bottom_consumed * to_money(bottom_inventory.price_per_unit))

    total_raw_material_cost = to_money(blank_cost + bottom_cost)
    total_production_cost = to_money(total_packing_cost + total_raw_material_cost)

    production_log = ProductionLog(
        factory_id=factory_id,
        date=date.today(),
        shift="AI",
        cup_size_ml=profile.cup_size_ml,
        packaging_profile_id=profile.id,
        blank_used_pcs=blank_used,
        bottom_used_kg=bottom_used,
        boxes_produced=boxes_produced,
        blank_waste_pcs=blank_waste,
        bottom_waste_kg=bottom_waste,
        box_packing_cost=box_packing_cost,
        poly_packing_cost=poly_packing_cost,
        total_packing_cost=total_packing_cost,
        blank_cost=blank_cost,
        bottom_cost=bottom_cost,
        total_raw_material_cost=total_raw_material_cost,
        total_production_cost=total_production_cost,
    )
    db.add(production_log)

    finished_stock = get_or_create_finished_goods_stock(db, factory_id, profile)
    finished_stock.boxes_available = (finished_stock.boxes_available or 0) + boxes_produced

    db.flush()
    return BusinessExecutionResult(
        status="success",
        message="Production entry posted",
        production_log_id=production_log.id,
        packaging_profile_id=profile.id,
        finished_goods_boxes_available=finished_stock.boxes_available,
        total_boxes_needed=total_boxes_needed,
        total_polys_needed=total_polys_needed,
        total_packing_cost=total_packing_cost,
        total_raw_material_cost=total_raw_material_cost,
        total_production_cost=total_production_cost,
    )


def execute_sales_entry(db: Session, factory_id: int, data: SalesIntentData) -> BusinessExecutionResult:
    customer_name = require_text(data.customer_name, "customer_name")
    boxes_sold = require_positive_int(data.boxes_sold or data.quantity, "quantity")

    profile = (
        get_packaging_profile(db, factory_id, data.packing_profile_name, data.cup_size_ml)
        if data.packing_profile_name
        else find_packaging_profile_for_product(db, factory_id, data.product_name, data.cup_size_ml)
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{data.product_name or data.cup_size_ml or 'Product'} ka profile nahi mila. "
                "Kaunsa product/size sale hua?"
            ),
        )
    finished_stock = get_or_create_finished_goods_stock(db, factory_id, profile)
    available_finished_boxes = finished_stock.boxes_available or 0
    if available_finished_boxes < boxes_sold:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Insufficient finished goods for {profile.profile_name}. "
                f"Required {boxes_sold}, available {available_finished_boxes}"
            ),
        )

    customer = get_or_create_customer(db, factory_id, customer_name)
    rate_per_box = to_money(data.rate_per_box) if data.rate_per_box and data.rate_per_box > 0 else calculate_finished_goods_base_price(db, finished_stock)
    total_amount = to_money(Decimal(boxes_sold) * rate_per_box)
    amount_paid = to_money(data.amount_received)
    new_balance = to_money(customer.balance_amount) + total_amount - amount_paid
    if new_balance < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="amount_received cannot exceed the customer's open balance plus this invoice total",
        )

    customer.balance_amount = new_balance
    finished_stock.boxes_available = available_finished_boxes - boxes_sold

    sales_invoice = SalesInvoice(
        factory_id=factory_id,
        customer_id=customer.id,
        date=date.today(),
        cup_size_ml=profile.cup_size_ml,
        packaging_profile_id=profile.id,
        boxes_sold=boxes_sold,
        total_amount=total_amount,
        amount_paid=amount_paid,
    )
    db.add(sales_invoice)
    db.flush()

    return BusinessExecutionResult(
        status="success",
        message="Sales entry posted",
        sales_invoice_id=sales_invoice.id,
        packaging_profile_id=profile.id,
        finished_goods_boxes_available=finished_stock.boxes_available,
        total_amount=total_amount,
        amount_paid=amount_paid,
        customer_balance_amount=customer.balance_amount,
    )


def execute_expense_entry(db: Session, factory_id: int, data: ExpenseIntentData) -> BusinessExecutionResult:
    description = require_text(data.description, "description")
    category = data.category.strip() if data.category else "General"
    amount = to_money(data.amount)
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="amount is required and must be greater than zero for expense_entry",
        )

    expense_log = ExpenseLog(
        factory_id=factory_id,
        date=date.today(),
        category=category,
        description=description,
        amount=amount,
        payment_method=data.payment_method,
    )
    db.add(expense_log)
    db.flush()

    return BusinessExecutionResult(
        status="success",
        message="Expense entry posted",
        expense_log_id=expense_log.id,
        expense_amount=amount,
    )


def execute_employee_entry(db: Session, factory_id: int, data: EmployeeIntentData) -> BusinessExecutionResult:
    employee_name = require_text(data.employee_name, "employee_name")
    employee = get_employee_by_name(db, factory_id, employee_name)

    overtime_hours = float(data.overtime_hours or 0)
    if overtime_hours < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="overtime_hours cannot be negative",
        )

    advance_amount = to_money(data.advance_given)
    if advance_amount < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="advance_given cannot be negative",
        )

    attendance_log: Optional[AttendanceLog] = None
    if data.is_present is not None or data.overtime_hours is not None:
        attendance_log = (
            db.query(AttendanceLog)
            .filter(AttendanceLog.factory_id == factory_id)
            .filter(AttendanceLog.employee_id == employee.id)
            .filter(AttendanceLog.date == date.today())
            .first()
        )
        is_present = data.is_present if data.is_present is not None else overtime_hours > 0
        if attendance_log is None:
            attendance_log = AttendanceLog(
                factory_id=factory_id,
                date=date.today(),
                employee_id=employee.id,
                is_present=is_present,
                overtime_hours=overtime_hours,
            )
            db.add(attendance_log)
        else:
            attendance_log.is_present = is_present
            attendance_log.overtime_hours = overtime_hours

    advance_payment: Optional[AdvancePayment] = None
    if advance_amount > 0:
        advance_payment = AdvancePayment(
            factory_id=factory_id,
            date=date.today(),
            employee_id=employee.id,
            amount=float(advance_amount),
        )
        db.add(advance_payment)

    if attendance_log is None and advance_payment is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least attendance, overtime, or advance details are required for employee_entry",
        )

    db.flush()
    return BusinessExecutionResult(
        status="success",
        message="Employee entry posted",
        employee_id=employee.id,
        attendance_log_id=attendance_log.id if attendance_log else None,
        advance_payment_id=advance_payment.id if advance_payment else None,
        advance_amount=advance_amount,
        overtime_hours=overtime_hours,
    )


def execute_general_qa(data: GeneralQAData) -> BusinessExecutionResult:
    answer = data.answer or "I can help with production, sales, expenses, inventory, and customer balances."
    return BusinessExecutionResult(
        status="success",
        message=answer,
    )


def execute_factory_intent(db: Session, factory_id: int, intent: FactoryIntent) -> BusinessExecutionResult:
    try:
        if intent.intent_type == FactoryIntentType.production_entry:
            if intent.production_data is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="production_data is required for production_entry",
                )
            result = execute_production_entry(db, factory_id, intent.production_data)
        elif intent.intent_type == FactoryIntentType.sales_entry:
            if intent.sales_data is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="sales_data is required for sales_entry",
                )
            result = execute_sales_entry(db, factory_id, intent.sales_data)
        elif intent.intent_type == FactoryIntentType.expense_entry:
            if intent.expense_data is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="expense_data is required for expense_entry",
                )
            result = execute_expense_entry(db, factory_id, intent.expense_data)
        elif intent.intent_type == FactoryIntentType.employee_entry:
            if intent.employee_data is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="employee_data is required for employee_entry",
                )
            result = execute_employee_entry(db, factory_id, intent.employee_data)
        else:
            result = execute_general_qa(intent.general_data or GeneralQAData())

        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute factory intent: {exc}",
        ) from exc


def build_success_reply(intent: FactoryIntent, result: BusinessExecutionResult, used_llm: bool) -> str:
    source_note = "" if used_llm else " Local parser mode is active because no LLM API key is configured."

    if intent.intent_type == FactoryIntentType.production_entry:
        return (
            f"Production saved. {result.finished_goods_boxes_available} boxes are now available for this packing profile. "
            f"Packing cost was {result.total_packing_cost}, total production cost was {result.total_production_cost}."
            f"{source_note}"
        )

    if intent.intent_type == FactoryIntentType.sales_entry:
        return (
            f"Sale saved. Invoice total is {result.total_amount}, received {result.amount_paid}, "
            f"and customer pending balance is {result.customer_balance_amount}."
            f"{source_note}"
        )

    if intent.intent_type == FactoryIntentType.expense_entry:
        return f"Expense saved for {result.expense_amount}.{source_note}"

    if intent.intent_type == FactoryIntentType.employee_entry:
        details = []
        if result.attendance_log_id is not None:
            details.append(f"attendance saved with {result.overtime_hours or 0} overtime hours")
        if result.advance_payment_id is not None:
            details.append(f"advance saved for {result.advance_amount}")
        return f"Employee entry saved: {', '.join(details)}.{source_note}"

    return result.message


def build_validation_reply(intent: Optional[FactoryIntent], detail: str) -> str:
    if intent and intent.intent_type == FactoryIntentType.production_entry:
        return f"I understood this as a production entry, but I need more valid production details: {detail}"
    if intent and intent.intent_type == FactoryIntentType.sales_entry:
        return f"I understood this as a sales entry, but I need more valid sales details: {detail}"
    if intent and intent.intent_type == FactoryIntentType.expense_entry:
        return f"I understood this as an expense entry, but I need more valid expense details: {detail}"
    if intent and intent.intent_type == FactoryIntentType.employee_entry:
        return f"I understood this as an employee entry, but I need more valid employee details: {detail}"
    return f"I could not confidently process that message: {detail}"


def sum_decimal(
    db: Session,
    factory_id: int,
    model,
    column,
    start_date: Optional[date],
    end_date: Optional[date],
) -> Decimal:
    query = (
        db.query(sql_func.coalesce(sql_func.sum(column), 0))
        .select_from(model)
        .filter(model.factory_id == factory_id)
    )
    if start_date is not None:
        query = query.filter(model.date >= start_date)
    if end_date is not None:
        query = query.filter(model.date <= end_date)
    return to_money(query.scalar())


def build_recent_7_days(db: Session, factory_id: int) -> List[DailyProductionSales]:
    today = date.today()
    start_day = today - timedelta(days=6)

    production_rows = (
        db.query(ProductionLog.date, sql_func.coalesce(sql_func.sum(ProductionLog.boxes_produced), 0))
        .filter(ProductionLog.factory_id == factory_id)
        .filter(ProductionLog.date >= start_day)
        .filter(ProductionLog.date <= today)
        .group_by(ProductionLog.date)
        .all()
    )
    sales_rows = (
        db.query(SalesInvoice.date, sql_func.coalesce(sql_func.sum(SalesInvoice.boxes_sold), 0))
        .filter(SalesInvoice.factory_id == factory_id)
        .filter(SalesInvoice.date >= start_day)
        .filter(SalesInvoice.date <= today)
        .group_by(SalesInvoice.date)
        .all()
    )

    production_by_date = {row[0]: int(row[1] or 0) for row in production_rows}
    sales_by_date = {row[0]: int(row[1] or 0) for row in sales_rows}

    return [
        DailyProductionSales(
            date=start_day + timedelta(days=offset),
            production_boxes=production_by_date.get(start_day + timedelta(days=offset), 0),
            sales_boxes=sales_by_date.get(start_day + timedelta(days=offset), 0),
        )
        for offset in range(7)
    ]


def calculate_wastage_mix(db: Session, factory_id: int) -> WastageMix:
    rows = (
        db.query(
            ProductionLog.boxes_produced,
            ProductionLog.blank_waste_pcs,
            ProductionLog.bottom_waste_kg,
            PackagingProfile.cups_per_poly,
            PackagingProfile.polys_per_box,
        )
        .join(PackagingProfile, ProductionLog.packaging_profile_id == PackagingProfile.id)
        .filter(ProductionLog.factory_id == factory_id)
        .filter(PackagingProfile.factory_id == factory_id)
        .all()
    )

    good_production_pcs = 0
    blank_waste_pcs = 0
    bottom_waste_kg = Decimal("0.000")

    for row in rows:
        boxes_produced = int(row[0] or 0)
        blank_waste_pcs += int(row[1] or 0)
        bottom_waste_kg += to_quantity(row[2])
        cups_per_box = int(row[3] or 0) * int(row[4] or 0)
        good_production_pcs += boxes_produced * cups_per_box

    return WastageMix(
        good_production_pcs=good_production_pcs,
        blank_waste_pcs=blank_waste_pcs,
        bottom_waste_kg=bottom_waste_kg,
    )


def calculate_wastage_percent(wastage_mix: WastageMix) -> Decimal:
    total_considered_pcs = Decimal(wastage_mix.good_production_pcs + wastage_mix.blank_waste_pcs)
    if total_considered_pcs == 0:
        return Decimal("0.00")

    return to_money((Decimal(wastage_mix.blank_waste_pcs) / total_considered_pcs) * Decimal("100"))


def build_product_catalog(db: Session, factory_id: int) -> str:
    rows = (
        db.query(PackagingProfile, FinishedGoodsStock)
        .outerjoin(FinishedGoodsStock, FinishedGoodsStock.packaging_profile_id == PackagingProfile.id)
        .filter(PackagingProfile.factory_id == factory_id)
        .order_by(PackagingProfile.cup_size_ml.asc(), PackagingProfile.profile_name.asc())
        .all()
    )
    if not rows:
        return "No finished goods or packaging profiles configured."

    return "\n".join(
        (
            f"- {profile.profile_name}: {profile.cup_size_ml}ml, "
            f"{stock.boxes_available if stock else 0} boxes in stock"
        )
        for profile, stock in rows
    )


def current_month_bounds() -> Tuple[date, date, date]:
    today = date.today()
    month_start = today.replace(day=1)
    if month_start.month == 12:
        next_month_start = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month_start = month_start.replace(month=month_start.month + 1)
    month_end = next_month_start - timedelta(days=1)
    return month_start, next_month_start, month_end


def execute_supervisor_tool(
    db: Session,
    factory_id: int,
    message: str,
    intent: FactoryIntent,
) -> Optional[AskAIResponse]:
    tool_name = intent.tool_name
    if tool_name is None:
        if intent.intent_type == FactoryIntentType.general_qa and "stock" in message.lower():
            tool_name = SupervisorToolName.check_inventory
        elif intent.intent_type == FactoryIntentType.production_entry:
            tool_name = SupervisorToolName.log_production
        elif intent.intent_type == FactoryIntentType.sales_entry:
            tool_name = SupervisorToolName.record_sale

    if tool_name == SupervisorToolName.check_inventory:
        return check_inventory_tool(db, factory_id, message, intent)
    if tool_name == SupervisorToolName.log_production:
        return log_production_tool(db, factory_id, intent)
    if tool_name == SupervisorToolName.record_sale:
        return record_sale_tool(db, factory_id, intent)
    return None


def check_inventory_tool(
    db: Session,
    factory_id: int,
    message: str,
    intent: FactoryIntent,
) -> AskAIResponse:
    product_name = tool_arg(intent, "product_name") or tool_arg(intent, "product") or message
    cup_size_ml = parse_optional_int(tool_arg(intent, "cup_size_ml")) or extract_cup_size_ml(product_name)
    stock_pair = find_product_stock(db, factory_id, product_name, cup_size_ml)
    if stock_pair is None:
        ai_reply = (
            f"Malik, {product_name.strip()} ka stock mujhe is factory me nahi mila. "
            "Aap product size/profile bata den, main dobara check kar dunga."
        )
        return supervisor_general_response(intent, ai_reply, status_text="needs_info")

    stock, profile = stock_pair
    ai_reply = f"Malik, {profile.profile_name} ka stock abhi {stock.boxes_available or 0} box hai."
    return supervisor_general_response(intent, ai_reply, status_text="success")


def log_production_tool(db: Session, factory_id: int, intent: FactoryIntent) -> AskAIResponse:
    data = intent.production_data
    if data is None:
        return supervisor_general_response(intent, "Kitne box production add karne hain?", status_text="needs_info")

    quantity = data.boxes_produced or data.quantity
    if not quantity:
        return supervisor_general_response(intent, "Got it. Kitne box add karne hain?", status_text="needs_info")

    profile = find_packaging_profile_for_product(db, factory_id, data.product_name, data.cup_size_ml)
    if data.packing_profile_name:
        try:
            profile = get_packaging_profile(db, factory_id, data.packing_profile_name, data.cup_size_ml)
        except HTTPException:
            profile = None
    if profile is None:
        product_label = data.product_name or (f"{data.cup_size_ml}ml" if data.cup_size_ml else "is product")
        ai_reply = (
            f"{product_label} ki packing details nahi mili, "
            "kya main standard 100pcs/box maan lu ya aap naya profile banayenge?"
        )
        return supervisor_general_response(intent, ai_reply, status_text="needs_info")

    result = execute_production_entry(db, factory_id, data)
    db.commit()
    ai_reply = (
        f"Done Malik. {quantity} box {profile.profile_name} production me add ho gaya. "
        f"Ab stock {result.finished_goods_boxes_available} box hai."
    )
    return supervisor_success_response(intent, result, ai_reply)


def record_sale_tool(db: Session, factory_id: int, intent: FactoryIntent) -> AskAIResponse:
    data = intent.sales_data
    if data is None:
        return supervisor_general_response(intent, "Sale record karne ke liye customer, product aur quantity bata dijiye.", status_text="needs_info")

    quantity = data.boxes_sold or data.quantity
    if not data.customer_name:
        return supervisor_general_response(intent, "Sale kis customer ko hui?", status_text="needs_info")
    if not quantity:
        return supervisor_general_response(intent, "Kitne box sale hue?", status_text="needs_info")

    profile = (
        get_packaging_profile(db, factory_id, data.packing_profile_name, data.cup_size_ml)
        if data.packing_profile_name
        else find_packaging_profile_for_product(db, factory_id, data.product_name, data.cup_size_ml)
    )
    if profile is None:
        product_label = data.product_name or (f"{data.cup_size_ml}ml" if data.cup_size_ml else "product")
        return supervisor_general_response(
            intent,
            f"{product_label} ka product profile nahi mila. Kaunsa size/product sale hua?",
            status_text="needs_info",
        )

    data.packing_profile_name = profile.profile_name
    data.cup_size_ml = profile.cup_size_ml
    data.boxes_sold = quantity
    result = execute_sales_entry(db, factory_id, data)
    db.commit()
    ai_reply = (
        f"Sale record ho gayi Malik. {quantity} box {profile.profile_name} {data.customer_name} ko gaya. "
        f"Remaining stock {result.finished_goods_boxes_available} box hai."
    )
    return supervisor_success_response(intent, result, ai_reply)


def supervisor_success_response(intent: FactoryIntent, result: BusinessExecutionResult, ai_reply: str) -> AskAIResponse:
    return AskAIResponse(
        ai_reply=ai_reply,
        action_taken=intent.intent_type,
        status=result.status,
        intent=intent,
        result=result,
    )


def supervisor_general_response(intent: FactoryIntent, ai_reply: str, status_text: str) -> AskAIResponse:
    return AskAIResponse(
        ai_reply=ai_reply,
        action_taken=FactoryIntentType.general_qa,
        status=status_text,
        intent=intent,
    )


def tool_arg(intent: FactoryIntent, key: str):
    return intent.tool_args.get(key) if intent.tool_args else None


def parse_optional_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def friendly_tool_error(detail: str) -> str:
    if "packing details nahi mili" in detail or "profile nahi mila" in detail:
        return detail
    if "Insufficient finished goods" in detail:
        return f"Malik, stock kam hai. {detail}"
    if "Insufficient" in detail:
        return f"Malik, material/stock kam hai. {detail}"
    if "quantity" in detail or "required" in detail:
        return f"Thoda aur detail chahiye: {detail}"
    return f"Is entry ko save karne se pehle ek detail clear karni hai: {detail}"


def normalize_external_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized_value = value.strip()
    return normalized_value or None


def ensure_external_id_available(
    db: Session,
    current_user_id: int,
    field_name: str,
    value: Optional[str],
) -> None:
    if value is None:
        return
    existing_user = db.query(User).filter(getattr(User, field_name) == value).first()
    if existing_user is not None and existing_user.id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{field_name} is already connected to another account",
        )


def get_user_by_external_sender(db: Session, platform: ExternalChatPlatform, sender_id: str) -> Optional[User]:
    normalized_sender_id = normalize_external_id(sender_id)
    if normalized_sender_id is None:
        return None
    if platform == ExternalChatPlatform.whatsapp:
        return db.query(User).filter(User.phone_number == normalized_sender_id).first()
    return db.query(User).filter(User.telegram_id == normalized_sender_id).first()


@app.on_event("startup")
def on_startup():
    ensure_auth_config()
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
    db = next(get_db())
    try:
        seed_default_users(db)
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/token", response_model=TokenResponse)
@app.post("/api/auth/token", response_model=TokenResponse)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    x_factory_id: Optional[int] = Header(default=None, alias="X-Factory-ID"),
    db: Session = Depends(get_db),
):
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

    return TokenResponse(
        access_token=create_access_token(user.username, user.role, user.factory_id),
        username=user.username,
        role=user.role,
        factory_id=user.factory_id,
    )


@app.get("/users/me", response_model=CurrentUserResponse)
def read_current_user(current_user: User = Depends(get_current_user)):
    return CurrentUserResponse(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        factory_id=current_user.factory_id,
        phone_number=current_user.phone_number,
        telegram_id=current_user.telegram_id,
    )


@app.get("/settings/integrations", response_model=IntegrationSettings)
def read_integration_settings(current_user: User = Depends(get_current_user)):
    return IntegrationSettings(
        phone_number=current_user.phone_number,
        telegram_id=current_user.telegram_id,
    )


@app.put("/settings/integrations", response_model=IntegrationSettings)
def update_integration_settings(
    settings: IntegrationSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    phone_number = normalize_external_id(settings.phone_number)
    telegram_id = normalize_external_id(settings.telegram_id)
    ensure_external_id_available(db, current_user.id, "phone_number", phone_number)
    ensure_external_id_available(db, current_user.id, "telegram_id", telegram_id)

    current_user.phone_number = phone_number
    normalized_phone = None
    if phone_number:
        normalized_phone = re.sub(r"\D", "", phone_number)
        for dial_code in ("+971", "+91", "+44", "+1"):
            if phone_number.startswith(dial_code):
                normalized_phone = re.sub(r"\D", "", phone_number[len(dial_code):])
                break
    current_user.phone_number_normalized = normalized_phone
    current_user.telegram_id = telegram_id
    db.commit()
    db.refresh(current_user)
    return IntegrationSettings(
        phone_number=current_user.phone_number,
        telegram_id=current_user.telegram_id,
    )


def process_factory_message(
    message: str,
    session_id: str,
    factory_id: int,
    db: Session,
    chat_history: Optional[List[Dict[str, str]]] = None,
    actor_role: Optional[str] = None,
) -> AskAIResponse:
    parsed_intent: Optional[FactoryIntent] = None
    parser_warning: Optional[str] = None
    product_catalog = build_product_catalog(db, factory_id)
    tool_context = build_ai_tool_context(db, factory_id)

    try:
        parsed_intent, used_llm = parse_factory_intent_with_agent(
            message=message,
            session_id=session_id,
            intent_model=FactoryIntent,
            fallback_parser=extract_factory_intent,
            product_catalog=product_catalog,
            chat_history=chat_history,
            tool_context=tool_context,
        )
    except Exception as exc:
        parsed_intent = extract_factory_intent(message)
        used_llm = False
        parser_warning = f"LLM parser failed; local parser fallback was used: {exc}"

    try:
        tool_response = execute_supervisor_tool(db, factory_id, message, parsed_intent)
        if tool_response is not None:
            save_agent_context(session_id, message, tool_response.ai_reply)
            return tool_response
    except HTTPException as exc:
        db.rollback()
        ai_reply = friendly_tool_error(str(exc.detail))
        save_agent_context(session_id, message, ai_reply)
        return AskAIResponse(
            ai_reply=ai_reply,
            action_taken=FactoryIntentType.general_qa,
            status="needs_info" if exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY else "validation_error",
            intent=parsed_intent,
            error=str(exc.detail),
        )

    try:
        result = execute_factory_intent(db, factory_id, parsed_intent)
    except HTTPException as exc:
        detail = str(exc.detail)
        ai_reply = build_validation_reply(parsed_intent, detail)
        save_agent_context(session_id, message, ai_reply)
        return AskAIResponse(
            ai_reply=ai_reply,
            action_taken=parsed_intent.intent_type,
            status="validation_error",
            intent=parsed_intent,
            error=detail,
        )

    ai_reply = build_success_reply(parsed_intent, result, used_llm)
    save_agent_context(session_id, message, ai_reply)
    return AskAIResponse(
        ai_reply=ai_reply,
        action_taken=parsed_intent.intent_type,
        status=result.status,
        intent=parsed_intent,
        result=result,
        error=parser_warning,
    )


@app.post("/ask-ai", response_model=AskAIResponse)
def ask_ai(
    payload: AskAIRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat_history = payload.chat_history or []
    if payload.system_prompt:
        chat_history = [{"role": "system", "content": payload.system_prompt}, *chat_history]

    response = process_factory_message(
        message=payload.message,
        session_id=payload.session_id,
        factory_id=current_user.factory_id,
        db=db,
        chat_history=chat_history,
        actor_role=current_user.role,
    )
    db.add(
        AppUsageLog(
            factory_id=current_user.factory_id,
            user_id=current_user.id,
            event_type="ai_supervisor_call",
            route_or_module="ai-supervisor",
            method="POST",
            meta={"action_taken": response.action_taken, "status": response.status},
        )
    )
    db.add(
        TokenUsageLog(
            factory_id=current_user.factory_id,
            user_id=current_user.id,
            provider=os.getenv("AI_PROVIDER") or "unknown",
            model=os.getenv("OPENAI_MODEL") or os.getenv("GROQ_MODEL"),
            feature_name="ai-supervisor",
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            meta={"note": "Provider token counts are not exposed in this flow yet."},
        )
    )
    db.commit()
    return response


@app.get("/api/ai/context")
def ai_context(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    factory_id = current_user.factory_id
    recent_cutoff = date.today() - timedelta(days=7)

    inventory_rows = [
        {
            "item_name": item.item_name,
            "category": item.category,
            "quantity": float(item.quantity or 0),
            "unit": item.unit,
            "price_per_unit": float(item.price_per_unit or 0),
        }
        for item in db.query(Inventory).filter(Inventory.factory_id == factory_id).order_by(Inventory.item_name.asc()).all()
    ]
    inventory_rows.extend(
        {
            "item_name": f"{stock.blank_size_ml}ml Blank",
            "category": "Blank",
            "quantity": float(stock.total_qty_kg or 0),
            "unit": "kg",
            "price_per_unit": 0,
        }
        for stock in db.query(BlankStock).filter(BlankStock.factory_id == factory_id).all()
    )
    inventory_rows.extend(
        {
            "item_name": f"{stock.bottom_size_mm}mm Bottom",
            "category": "Bottom",
            "quantity": float(stock.total_qty_kg or 0),
            "unit": "kg",
            "price_per_unit": 0,
        }
        for stock in db.query(BottomStock).filter(BottomStock.factory_id == factory_id).all()
    )
    inventory_rows.extend(
        {
            "item_name": stock.packaging_size_name,
            "category": "Box",
            "quantity": int(stock.total_boxes or 0),
            "unit": "boxes",
            "price_per_unit": 0,
        }
        for stock in db.query(BoxStock).filter(BoxStock.factory_id == factory_id).all()
    )
    inventory_rows.extend(
        {
            "item_name": f"{stock.product_size_ml}ml {stock.packaging_size_name}",
            "category": "Final Product",
            "quantity": int(stock.total_boxes or 0),
            "loose_packets": int(stock.loose_packets or 0),
            "unit": "boxes",
            "price_per_unit": 0,
        }
        for stock in db.query(FinalProductStock).filter(FinalProductStock.factory_id == factory_id).all()
    )

    machines = [
        {
            "id": machine.id,
            "machine_number": machine.machine_number or machine.machine_sequence_number or machine.name,
            "machine_type": machine.machine_type,
            "cup_size_ml": machine.mould_size_ml or machine.cup_size_ml,
            "bottom_size_mm": machine.bottom_size_mm,
            "speed_per_minute": machine.speed_per_minute,
        }
        for machine in db.query(Machine).filter(Machine.factory_id == factory_id).order_by(Machine.id.asc()).all()
    ]

    raw_material_metrics = [
        {
            "material_type": metric.material_type,
            "size_ml_or_mm": metric.size_ml_or_mm,
            "weight_per_sack_kg": float(metric.weight_per_sack_kg or 0),
            "pieces_per_sack": metric.pieces_per_sack,
            "pieces_per_kg": (
                float(metric.pieces_per_sack) / float(metric.weight_per_sack_kg)
                if metric.weight_per_sack_kg
                else 0
            ),
        }
        for metric in db.query(RawMaterialMetrics).filter(RawMaterialMetrics.factory_id == factory_id).all()
    ]

    production_rows = (
        db.query(DailyProduction)
        .filter(DailyProduction.factory_id == factory_id)
        .filter(DailyProduction.date >= recent_cutoff)
        .order_by(DailyProduction.date.desc(), DailyProduction.id.desc())
        .limit(20)
        .all()
    )

    return {
        "factory_id": factory_id,
        "system_prompt": (
            "You are a Factory Supervisor AI. You have access to real-time inventory "
            "and production data. Use it to give precise numbers."
        ),
        "current_stock": inventory_rows,
        "machines": machines,
        "raw_material_metrics": raw_material_metrics,
        "recent_production": [
            {
                "date": row.date.isoformat(),
                "machine_id": row.machine_id,
                "worker_id": row.worker_id,
                "product_size_ml": row.product_size_ml,
                "packaging_size_name": row.packaging_size_name,
                "total_boxes_made": row.total_boxes_made,
                "loose_packets_made": row.loose_packets_made,
                "boxes_from_loose": row.boxes_from_loose,
                "blank_used_kg": float(row.blank_used_kg or 0),
                "bottom_used_kg": float(row.bottom_used_kg or 0),
            }
            for row in production_rows
        ],
        "recent_production_totals": {
            "boxes_made": sum(row.total_boxes_made or 0 for row in production_rows),
            "loose_packets_made": sum(row.loose_packets_made or 0 for row in production_rows),
            "blank_used_kg": float(sum(Decimal(row.blank_used_kg or 0) for row in production_rows)),
            "bottom_used_kg": float(sum(Decimal(row.bottom_used_kg or 0) for row in production_rows)),
        },
    }


@app.get("/api/debug/verify-stocks")
def verify_stocks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    factory_id = current_user.factory_id
    return {
        "factory_id": factory_id,
        "blank_stock": [
            {
                "blank_size_ml": stock.blank_size_ml,
                "linked_bottom_size_mm": stock.linked_bottom_size_mm,
                "total_qty_kg": float(stock.total_qty_kg or 0),
            }
            for stock in db.query(BlankStock).filter(BlankStock.factory_id == factory_id).order_by(BlankStock.blank_size_ml.asc()).all()
        ],
        "bottom_stock": [
            {
                "bottom_size_mm": stock.bottom_size_mm,
                "total_qty_kg": float(stock.total_qty_kg or 0),
            }
            for stock in db.query(BottomStock).filter(BottomStock.factory_id == factory_id).order_by(BottomStock.bottom_size_mm.asc()).all()
        ],
        "box_stock": [
            {
                "packaging_size_name": stock.packaging_size_name,
                "total_boxes": int(stock.total_boxes or 0),
            }
            for stock in db.query(BoxStock).filter(BoxStock.factory_id == factory_id).order_by(BoxStock.packaging_size_name.asc()).all()
        ],
        "final_product_stock": [
            {
                "product_size_ml": stock.product_size_ml,
                "packaging_size_name": stock.packaging_size_name,
                "total_boxes": int(stock.total_boxes or 0),
                "loose_packets": int(stock.loose_packets or 0),
                "packets_per_box_limit": stock.packets_per_box_limit,
            }
            for stock in db.query(FinalProductStock).filter(FinalProductStock.factory_id == factory_id).order_by(FinalProductStock.product_size_ml.asc()).all()
        ],
        "customer_balances": [
            {
                "id": customer.id,
                "name": customer.name,
                "phone": customer.phone or customer.contact_number,
                "previous_due": float(customer.previous_due or 0),
                "total_due": float(customer.total_due or customer.balance_amount or 0),
            }
            for customer in db.query(Customer).filter(Customer.factory_id == factory_id).order_by(Customer.name.asc()).all()
        ],
    }


@app.post("/webhook/external-chat", response_model=ExternalChatResponse)
def external_chat_webhook(payload: ExternalChatRequest, db: Session = Depends(get_db)):
    user = get_user_by_external_sender(db, payload.platform, payload.sender_id)
    if user is None:
        return ExternalChatResponse(
            reply="Aapka number registered nahi hai. Kripya dashboard se connect karein.",
            status="not_registered",
            action_taken=FactoryIntentType.general_qa.value,
        )

    session_id = f"external:{payload.platform.value}:{payload.sender_id}"
    ai_response = process_factory_message(
        message=payload.message,
        session_id=session_id,
        factory_id=user.factory_id,
        db=db,
        actor_role=user.role,
    )
    return ExternalChatResponse(
        reply=ai_response.ai_reply,
        status=ai_response.status,
        action_taken=ai_response.action_taken.value
        if isinstance(ai_response.action_taken, FactoryIntentType)
        else str(ai_response.action_taken),
    )


@app.post("/api/webhook/whatsapp", response_model=AskAIResponse)
async def whatsapp_voice_webhook(
    audio: UploadFile = File(...),
    session_id: str = Form(default="whatsapp"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transcribed_text = await transcribe_audio_upload(audio)
    return process_factory_message(transcribed_text, session_id, current_user.factory_id, db)


@app.get("/report/profit-loss", response_model=ProfitLossReport)
def profit_loss_report(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    factory_id = current_user.factory_id
    revenue = sum_decimal(db, factory_id, SalesInvoice, SalesInvoice.total_amount, start_date, end_date)
    cash_received = sum_decimal(db, factory_id, SalesInvoice, SalesInvoice.amount_paid, start_date, end_date)
    total_packing_cost = sum_decimal(db, factory_id, ProductionLog, ProductionLog.total_packing_cost, start_date, end_date)
    total_expenses = sum_decimal(db, factory_id, ExpenseLog, ExpenseLog.amount, start_date, end_date)
    total_raw_material_cost = sum_decimal(
        db,
        factory_id,
        ProductionLog,
        ProductionLog.total_raw_material_cost,
        start_date,
        end_date,
    )
    total_production_cost = sum_decimal(
        db,
        factory_id,
        ProductionLog,
        ProductionLog.total_production_cost,
        start_date,
        end_date,
    )

    return ProfitLossReport(
        revenue=revenue,
        cash_received=cash_received,
        outstanding_receivables=to_money(revenue - cash_received),
        total_packing_cost=total_packing_cost,
        total_raw_material_cost=total_raw_material_cost,
        total_production_cost=total_production_cost,
        total_expenses=total_expenses,
        net_profit=to_money(revenue - total_production_cost - total_expenses),
    )


@app.get("/api/dashboard-stats", response_model=DashboardStats)
def dashboard_stats(
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        factory_id = current_user.factory_id
        today = date.today()
        month_start = today.replace(day=1)
        monthly_revenue = sum_decimal(db, factory_id, SalesInvoice, SalesInvoice.total_amount, month_start, today)
        monthly_production_cost = sum_decimal(
            db,
            factory_id,
            ProductionLog,
            ProductionLog.total_production_cost,
            month_start,
            today,
        )
        monthly_expenses = sum_decimal(db, factory_id, ExpenseLog, ExpenseLog.amount, month_start, today)
        total_pending_recoveries = to_money(
            db.query(sql_func.coalesce(sql_func.sum(Customer.balance_amount), 0))
            .filter(Customer.factory_id == factory_id)
            .scalar()
        )
        total_boxes_in_stock = int(
            db.query(sql_func.coalesce(sql_func.sum(FinishedGoodsStock.boxes_available), 0))
            .filter(FinishedGoodsStock.factory_id == factory_id)
            .scalar()
            or 0
        )
        wastage_mix = calculate_wastage_mix(db, factory_id)

        return DashboardStats(
            monthly_net_profit=to_money(monthly_revenue - monthly_production_cost - monthly_expenses),
            total_pending_recoveries=total_pending_recoveries,
            total_boxes_in_stock=total_boxes_in_stock,
            overall_wastage_percent=calculate_wastage_percent(wastage_mix),
            recent_7_days=build_recent_7_days(db, factory_id),
            wastage_mix=wastage_mix,
        )
    except Exception:
        today = date.today()
        recent_7_days = [
            DailyProductionSales(
                date=today - timedelta(days=offset),
                production_boxes=0,
                sales_boxes=0,
            )
            for offset in range(6, -1, -1)
        ]
        return DashboardStats(
            monthly_net_profit=Decimal("0.00"),
            total_pending_recoveries=Decimal("0.00"),
            total_boxes_in_stock=0,
            overall_wastage_percent=Decimal("0.00"),
            recent_7_days=recent_7_days,
            wastage_mix=WastageMix(
                good_production_pcs=0,
                blank_waste_pcs=0,
                bottom_waste_kg=Decimal("0.000"),
            ),
    )


@app.get("/api/onboarding/workers")
def list_onboarding_workers_main(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workers = (
        db.query(Worker)
        .filter(Worker.factory_id == current_user.factory_id)
        .order_by(Worker.name.asc())
        .all()
    )
    if workers:
        return [
            {
                "id": worker.id,
                "name": worker.name,
                "phone": None,
                "shift_type": worker.shift_type,
                "shift_timing": worker.shift_timing,
                "daily_wages": worker.daily_wages,
                "duty_hours": worker.duty_hours,
            }
            for worker in workers
        ]

    employees = (
        db.query(Employee)
        .filter(Employee.factory_id == current_user.factory_id)
        .order_by(Employee.name.asc())
        .all()
    )
    return [
        {
            "id": employee.id,
            "name": employee.name,
            "phone": None,
            "shift_type": employee.role,
            "shift_timing": None,
            "daily_wages": employee.daily_wage,
            "duty_hours": 8,
        }
        for employee in employees
    ]


@app.get("/api/onboarding/machines")
def list_onboarding_machines_main(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    machines = (
        db.query(Machine)
        .filter(Machine.factory_id == current_user.factory_id)
        .order_by(Machine.machine_number.asc().nullslast(), Machine.name.asc())
        .all()
    )
    return [
        {
            "id": machine.id,
            "machine_type": machine.machine_type,
            "machine_number": machine.machine_number or machine.machine_sequence_number or machine.name,
            "mould_size_ml": machine.mould_size_ml or machine.cup_size_ml,
            "bottom_size_mm": machine.bottom_size_mm,
            "speed_per_minute": machine.speed_per_minute,
        }
        for machine in machines
    ]


@app.get("/api/onboarding/materials")
def list_onboarding_materials_main(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    factory_id = current_user.factory_id
    return {
        "raw_material_metrics": (
            db.query(RawMaterialMetrics)
            .filter(RawMaterialMetrics.factory_id == factory_id)
            .order_by(RawMaterialMetrics.material_type.asc(), RawMaterialMetrics.size_ml_or_mm.asc())
            .all()
        ),
        "packaging_metrics": (
            db.query(PackagingMetrics)
            .filter(PackagingMetrics.factory_id == factory_id)
            .order_by(PackagingMetrics.cup_size_ml.asc())
            .all()
        ),
    }


@app.get("/api/inventory")
def list_inventory_api_alias(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return inventory.list_live_stock(current_user=current_user, db=db)


@app.get("/report/customer-balance", response_model=List[CustomerBalanceRow])
def customer_balance_report(
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        factory_id = current_user.factory_id
        rows = (
            db.query(
                Customer.name,
                sql_func.coalesce(sql_func.sum(SalesInvoice.total_amount), 0),
                Customer.balance_amount,
            )
            .outerjoin(SalesInvoice, SalesInvoice.customer_id == Customer.id)
            .filter(Customer.factory_id == factory_id)
            .group_by(Customer.id, Customer.name, Customer.balance_amount)
            .order_by(Customer.balance_amount.desc(), Customer.name.asc())
            .all()
        )

        return [
            CustomerBalanceRow(
                customer_name=row[0],
                total_billed=to_money(row[1]),
                pending_amount=to_money(row[2]),
            )
            for row in rows
        ]
    except Exception:
        return []


@app.get(
    "/api/n8n/pending-payments",
    response_model=List[PendingPaymentRow],
)
def n8n_pending_payments(
    factory_id: int = Depends(get_n8n_factory_id),
    db: Session = Depends(get_db),
):
    customers = (
        db.query(Customer)
        .filter(Customer.factory_id == factory_id)
        .filter(Customer.balance_amount > 0)
        .order_by(Customer.balance_amount.desc(), Customer.name.asc())
        .all()
    )

    return [
        PendingPaymentRow(
            name=customer.name,
            contact_number=customer.contact_number,
            pending_amount=to_money(customer.balance_amount),
        )
        for customer in customers
    ]


@app.get(
    "/api/n8n/verified-customers",
    response_model=List[VerifiedStoreCustomerRow],
)
def n8n_verified_customers(
    factory_id: int = Depends(get_n8n_factory_id),
    db: Session = Depends(get_db),
):
    customers = (
        db.query(Customer)
        .filter(Customer.factory_id == factory_id)
        .filter(Customer.store_token.isnot(None))
        .filter(Customer.store_token != "")
        .order_by(Customer.name.asc())
        .all()
    )

    return [
        VerifiedStoreCustomerRow(
            name=customer.name,
            contact_number=customer.contact_number,
            store_token=customer.store_token,
        )
        for customer in customers
        if customer.store_token
    ]


@app.get("/api/inventory/low-stock", response_model=List[LowStockInventoryRow])
def low_stock_inventory(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    low_stock_items = (
        db.query(Inventory)
        .filter(Inventory.factory_id == current_user.factory_id)
        .filter(Inventory.category == "Raw")
        .filter(Inventory.unit == "kg")
        .filter(Inventory.quantity < LOW_STOCK_THRESHOLD_KG)
        .order_by(Inventory.quantity.asc(), Inventory.item_name.asc())
        .all()
    )

    return [
        LowStockInventoryRow(
            id=item.id,
            item_name=item.item_name,
            category=item.category,
            unit=item.unit,
            quantity=to_quantity(item.quantity),
            supplier_whatsapp_number=SUPPLIER_WHATSAPP_NUMBER,
        )
        for item in low_stock_items
    ]


@app.get("/api/admin/live-activity", response_model=List[LiveActivityRow])
def admin_live_activity(
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(CustomerActivity, Customer)
        .join(Customer, CustomerActivity.customer_id == Customer.id)
        .filter(CustomerActivity.factory_id == current_user.factory_id)
        .filter(Customer.factory_id == current_user.factory_id)
        .order_by(CustomerActivity.created_at.desc(), CustomerActivity.id.desc())
        .limit(20)
        .all()
    )

    return [
        LiveActivityRow(
            id=activity.id,
            customer_id=customer.id,
            customer_name=customer.name,
            activity_type=activity.activity_type,
            created_at=activity.created_at,
        )
        for activity, customer in rows
    ]


@app.get("/report/production-log", response_model=List[ProductionLogRow])
def production_log_report(
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        bounded_limit = min(max(limit, 1), 500)
        rows = (
            db.query(ProductionLog, PackagingProfile)
            .join(PackagingProfile, ProductionLog.packaging_profile_id == PackagingProfile.id)
            .filter(ProductionLog.factory_id == current_user.factory_id)
            .filter(PackagingProfile.factory_id == current_user.factory_id)
            .order_by(ProductionLog.date.desc(), ProductionLog.id.desc())
            .limit(bounded_limit)
            .all()
        )

        report_rows = []
        for production_log, packaging_profile in rows:
            cups_per_box = packaging_profile.cups_per_poly * packaging_profile.polys_per_box
            estimated_good_cups = production_log.boxes_produced * cups_per_box
            blank_waste = production_log.blank_waste_pcs or 0
            total_considered = estimated_good_cups + blank_waste
            blank_wastage_percent = Decimal("0.00")
            if total_considered > 0:
                blank_wastage_percent = to_money((Decimal(blank_waste) / Decimal(total_considered)) * Decimal("100"))

            report_rows.append(
                ProductionLogRow(
                    id=production_log.id,
                    date=production_log.date,
                    shift=production_log.shift,
                    cup_size_ml=production_log.cup_size_ml,
                    packaging_profile_name=packaging_profile.profile_name,
                    boxes_produced=production_log.boxes_produced,
                    estimated_good_cups=estimated_good_cups,
                    blank_waste_pcs=blank_waste,
                    bottom_waste_kg=to_quantity(production_log.bottom_waste_kg),
                    blank_wastage_percent=blank_wastage_percent,
                    total_packing_cost=to_money(production_log.total_packing_cost),
                    total_production_cost=to_money(production_log.total_production_cost),
                )
            )

        return report_rows if report_rows else []
    except Exception:
        return []


@app.get("/report/live-inventory", response_model=LiveInventoryReport)
def live_inventory_report(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raw_materials = (
        db.query(Inventory)
        .filter(Inventory.factory_id == current_user.factory_id)
        .filter(Inventory.category == "Raw")
        .order_by(Inventory.item_name.asc())
        .all()
    )
    packaging_materials = (
        db.query(Inventory)
        .filter(Inventory.factory_id == current_user.factory_id)
        .filter(Inventory.category == "Packaging")
        .order_by(Inventory.item_name.asc())
        .all()
    )
    finished_goods = (
        db.query(FinishedGoodsStock, PackagingProfile)
        .join(PackagingProfile, FinishedGoodsStock.packaging_profile_id == PackagingProfile.id)
        .filter(FinishedGoodsStock.factory_id == current_user.factory_id)
        .filter(PackagingProfile.factory_id == current_user.factory_id)
        .order_by(PackagingProfile.cup_size_ml.asc(), PackagingProfile.profile_name.asc())
        .all()
    )

    return LiveInventoryReport(
        raw_materials=[
            InventoryRow(
                id=item.id,
                item_name=item.item_name,
                category=item.category,
                unit=item.unit,
                quantity=to_quantity(item.quantity),
                price_per_unit=to_money(item.price_per_unit),
            )
            for item in raw_materials
        ],
        packaging_materials=[
            InventoryRow(
                id=item.id,
                item_name=item.item_name,
                category=item.category,
                unit=item.unit,
                quantity=to_quantity(item.quantity),
                price_per_unit=to_money(item.price_per_unit),
            )
            for item in packaging_materials
        ],
        finished_goods=[
            FinishedGoodsRow(
                id=stock.id,
                cup_size_ml=stock.cup_size_ml,
                packaging_profile_name=profile.profile_name,
                boxes_available=stock.boxes_available,
                updated_at=stock.updated_at,
            )
            for stock, profile in finished_goods
        ],
    )


@app.get("/api/store/{store_token}", response_model=StorefrontResponse)
def get_storefront(store_token: str, db: Session = Depends(get_db)):
    return get_customer_storefront(store_token, db)


@app.get("/api/storefront/{store_token}", response_model=StorefrontResponse)
def get_secure_storefront(store_token: str, db: Session = Depends(get_db)):
    return get_customer_storefront(store_token, db)


def get_customer_storefront(store_token: str, db: Session) -> StorefrontResponse:
    customer = get_store_customer(db, store_token)
    db.add(
        CustomerActivity(
            factory_id=customer.factory_id,
            customer_id=customer.id,
            activity_type="Viewed Store",
        )
    )
    db.commit()

    available_stocks = (
        db.query(FinishedGoodsStock)
        .join(PackagingProfile, FinishedGoodsStock.packaging_profile_id == PackagingProfile.id)
        .filter(FinishedGoodsStock.factory_id == customer.factory_id)
        .filter(PackagingProfile.factory_id == customer.factory_id)
        .filter(FinishedGoodsStock.boxes_available > 0)
        .order_by(PackagingProfile.cup_size_ml.asc(), PackagingProfile.profile_name.asc())
        .all()
    )

    return StorefrontResponse(
        customer_id=customer.id,
        customer_name=customer.name,
        contact_number=customer.contact_number,
        advance_discount_pct=float(customer.advance_discount_pct or 0),
        terms_and_conditions=STOREFRONT_TERMS_AND_CONDITIONS,
        products=[
            StorefrontProduct(
                product_id=stock.id,
                cup_size_ml=stock.cup_size_ml,
                packaging_profile_name=stock.packaging_profile.profile_name,
                availability_status=get_availability_status(stock.boxes_available),
                base_price=calculate_finished_goods_base_price(db, stock),
                image_url=stock.packaging_profile.image_url,
                print_design_name=stock.packaging_profile.print_design_name,
            )
            for stock in available_stocks
        ],
    )


@app.post("/api/store/{store_token}/checkout", response_model=StoreCheckoutResponse)
def checkout_storefront(
    store_token: str,
    payload: StoreCheckoutRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    return process_storefront_order(store_token, payload, background_tasks, db)


@app.post("/api/storefront/{store_token}/order", response_model=StoreCheckoutResponse)
def create_storefront_order(
    store_token: str,
    payload: StoreCheckoutRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    return process_storefront_order(store_token, payload, background_tasks, db)


def process_storefront_order(
    store_token: str,
    payload: StoreCheckoutRequest,
    background_tasks: BackgroundTasks,
    db: Session,
) -> StoreCheckoutResponse:
    customer = get_store_customer(db, store_token)
    payment_method = normalize_store_payment_method(payload.payment_method)
    if not payload.terms_accepted:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="terms_accepted must be true to place a storefront order",
        )

    requested_quantities: Dict[int, int] = {}
    for item in payload.items:
        requested_quantities[item.product_id] = requested_quantities.get(item.product_id, 0) + item.quantity

    try:
        locked_stocks = (
            db.query(FinishedGoodsStock)
            .filter(FinishedGoodsStock.factory_id == customer.factory_id)
            .filter(FinishedGoodsStock.id.in_(requested_quantities.keys()))
            .with_for_update()
            .all()
        )
        stocks_by_id = {stock.id: stock for stock in locked_stocks}
        missing_product_ids = sorted(set(requested_quantities.keys()) - set(stocks_by_id.keys()))
        if missing_product_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Products not found: {missing_product_ids}",
            )

        discount_pct = Decimal("0.00")
        if payment_method in {"Full_Advance_UPI", "Full_Advance_Doorstep"}:
            discount_pct = to_money(customer.advance_discount_pct)

        order = Order(
            factory_id=customer.factory_id,
            customer_id=customer.id,
            status="Pending",
            payment_method=payment_method,
            total_amount=Decimal("0.00"),
            terms_accepted=True,
            is_discount_revoked=False,
        )
        db.add(order)
        db.flush()

        response_items: List[StoreCheckoutItemResponse] = []
        base_total_amount = Decimal("0.00")
        total_amount = Decimal("0.00")
        previous_balance = to_money(customer.balance_amount)
        for product_id, requested_quantity in requested_quantities.items():
            stock = stocks_by_id[product_id]
            available_quantity = stock.boxes_available or 0
            if requested_quantity > available_quantity:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Insufficient stock for {stock.packaging_profile.profile_name}. "
                        f"Requested {requested_quantity}, available {available_quantity}"
                    ),
                )

            base_rate = calculate_finished_goods_base_price(db, stock)
            if base_rate <= 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Base price is not available for product_id {product_id}",
                )

            final_rate = base_rate
            if payment_method in {"Full_Advance_UPI", "Full_Advance_Doorstep"}:
                final_rate = to_money(base_rate * (Decimal("100.00") - discount_pct) / Decimal("100.00"))

            base_line_total = to_money(base_rate * Decimal(requested_quantity))
            line_total = to_money(final_rate * Decimal(requested_quantity))
            stock.boxes_available = available_quantity - requested_quantity
            db.add(
                OrderItem(
                    factory_id=customer.factory_id,
                    order_id=order.id,
                    product_id=product_id,
                    quantity=requested_quantity,
                    base_rate=base_rate,
                    final_rate=final_rate,
                )
            )
            base_total_amount = to_money(base_total_amount + base_line_total)
            total_amount = to_money(total_amount + line_total)
            response_items.append(
                StoreCheckoutItemResponse(
                    product_id=product_id,
                    packaging_profile_name=stock.packaging_profile.profile_name,
                    quantity=requested_quantity,
                    base_rate=base_rate,
                    final_rate=final_rate,
                    line_total=line_total,
                )
            )

        order.total_amount = total_amount
        new_total_balance = to_money(previous_balance + total_amount)
        customer.balance_amount = new_total_balance
        customer.pending_balance = new_total_balance
        customer.pending_dues = float(new_total_balance)
        customer.last_balance_update = datetime.utcnow()
        db.commit()

        discount_amount = to_money(base_total_amount - total_amount)
        webhook_payload = {
            "customer_name": customer.name,
            "whatsapp_number": customer.contact_number,
            "order_details": ", ".join(
                f"{item.quantity} Boxes of {item.packaging_profile_name}"
                for item in response_items
            ),
            "order_value": float(total_amount),
            "previous_balance": float(previous_balance),
            "new_total_balance": float(new_total_balance),
        }
        background_tasks.add_task(dispatch_order_confirmation_webhook, webhook_payload)

        return StoreCheckoutResponse(
            message="Order placed successfully and stock reserved for approval",
            order_id=order.id,
            status=order.status,
            payment_method=order.payment_method,
            discount_pct=discount_pct,
            discount_amount=discount_amount,
            total_amount=total_amount,
            previous_balance=previous_balance,
            new_total_balance=new_total_balance,
            upi_payment_details=UPI_PAYMENT_DETAILS if payment_method == "Full_Advance_UPI" else None,
            items=response_items,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to place storefront order: {exc}",
        ) from exc


@app.post("/api/admin/orders/{order_id}/revoke-discount", response_model=RevokeDiscountResponse)
def revoke_order_discount(
    order_id: int,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        order = (
            db.query(Order)
            .filter(Order.factory_id == current_user.factory_id)
            .filter(Order.id == order_id)
            .with_for_update()
            .first()
        )
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order not found: {order_id}",
            )

        if order.payment_method != "Full_Advance_Doorstep":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Discount can only be revoked for Full_Advance_Doorstep orders",
            )

        if order.is_discount_revoked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Discount has already been revoked for this order",
            )

        customer = (
            db.query(Customer)
            .filter(Customer.factory_id == current_user.factory_id)
            .filter(Customer.id == order.customer_id)
            .with_for_update()
            .first()
        )
        if customer is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer not found for order: {order_id}",
            )

        base_total_amount = Decimal("0.00")
        for item in order.items:
            base_total_amount = to_money(base_total_amount + (to_money(item.base_rate) * Decimal(item.quantity)))

        previous_total_amount = to_money(order.total_amount)
        discount_revoked_amount = to_money(base_total_amount - previous_total_amount)
        if discount_revoked_amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No discount amount is available to revoke for this order",
            )

        order.total_amount = base_total_amount
        order.is_discount_revoked = True
        customer.balance_amount = to_money(customer.balance_amount) + discount_revoked_amount

        db.commit()
        return RevokeDiscountResponse(
            message="Doorstep advance discount revoked and added to customer balance",
            order_id=order.id,
            customer_id=customer.id,
            payment_method=order.payment_method,
            previous_total_amount=previous_total_amount,
            recalculated_total_amount=base_total_amount,
            discount_revoked_amount=discount_revoked_amount,
            customer_balance_amount=to_money(customer.balance_amount),
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke order discount: {exc}",
        ) from exc


@app.get("/api/employee-report/{employee_id}", response_model=EmployeeReport)
def employee_report(
    employee_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    employee = (
        db.query(Employee)
        .filter(Employee.factory_id == current_user.factory_id)
        .filter(Employee.id == employee_id)
        .first()
    )
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee not found: {employee_id}",
        )

    month_start, next_month_start, month_end = current_month_bounds()
    attendance_filters = (
        AttendanceLog.employee_id == employee.id,
        AttendanceLog.date >= month_start,
        AttendanceLog.date < next_month_start,
    )
    advance_filters = (
        AdvancePayment.employee_id == employee.id,
        AdvancePayment.date >= month_start,
        AdvancePayment.date < next_month_start,
    )

    days_present = int(
        db.query(sql_func.count(AttendanceLog.id))
        .filter(AttendanceLog.factory_id == current_user.factory_id)
        .filter(*attendance_filters)
        .filter(AttendanceLog.is_present.is_(True))
        .scalar()
        or 0
    )
    total_overtime_hours = float(
        db.query(sql_func.coalesce(sql_func.sum(AttendanceLog.overtime_hours), 0))
        .filter(AttendanceLog.factory_id == current_user.factory_id)
        .filter(*attendance_filters)
        .scalar()
        or 0
    )
    total_advance = to_money(
        db.query(sql_func.coalesce(sql_func.sum(AdvancePayment.amount), 0))
        .filter(AdvancePayment.factory_id == current_user.factory_id)
        .filter(*advance_filters)
        .scalar()
    )

    daily_wage = to_money(employee.daily_wage)
    overtime_rate = to_money(daily_wage / Decimal("8"))
    gross_salary = to_money(
        (Decimal(days_present) * daily_wage)
        + (Decimal(str(total_overtime_hours)) * overtime_rate)
    )

    return EmployeeReport(
        employee_id=employee.id,
        employee_name=employee.name,
        role=employee.role,
        month_start=month_start,
        month_end=month_end,
        days_present=days_present,
        total_overtime_hours=total_overtime_hours,
        daily_wage=daily_wage,
        overtime_rate=overtime_rate,
        gross_salary=gross_salary,
        total_advance=total_advance,
        net_payable=to_money(gross_salary - total_advance),
    )


@app.get("/inventory", response_model=List[InventoryResponse])
def list_inventory(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(FactoryInventory)
        .filter(FactoryInventory.factory_id == current_user.factory_id)
        .order_by(FactoryInventory.updated_at.desc(), FactoryInventory.id.desc())
        .all()
    )


@app.post(
    "/inventory",
    response_model=InventoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_inventory_item(
    item: InventoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inventory_item = FactoryInventory(
        factory_id=current_user.factory_id,
        raw_material_name=item.raw_material_name.strip(),
        quantity=item.quantity,
    )

    if not inventory_item.raw_material_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="raw_material_name cannot be blank",
        )

    db.add(inventory_item)
    db.commit()
    db.refresh(inventory_item)
    return inventory_item

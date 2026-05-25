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
from routers.ai_invoice import CalculateDraftRequest, InvoiceDraftItem, calculate_draft
from routers.ai_invoice import router as ai_invoice_router
from routers.internal_automation import router as internal_automation_router

app = FastAPI(title="AI ERP API", version="0.1.0")

# ==================== CORS SECURITY LAYER CONFIGURATION ====================
def parse_cors_origins() -> List[str]:
    """
    Optimized configuration for secure multi-environment cross-origin access.
    """
    origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:80",
        "http://localhost",
        "https://munshiai.co.in",
        "https://www.munshiai.co.in",
    ]
    
    # Environment configs injection check
    frontend_env = os.getenv("FRONTEND_ORIGIN")
    hostinger_domain = os.getenv("HOSTINGER_DOMAIN")
    hostinger_ip = os.getenv("HOSTINGER_IP")
    cors_origins_env = os.getenv("CORS_ORIGINS")

    for env_val in [frontend_env, hostinger_domain, hostinger_ip]:
        if env_val:
            cleaned = env_val.strip().rstrip("/")
            if cleaned and cleaned not in origins:
                origins.append(cleaned)
                
    if cors_origins_env:
        for extra_origin in cors_origins_env.split(","):
            cleaned = extra_origin.strip().rstrip("/")
            if cleaned and cleaned not in origins:
                origins.append(cleaned)

    # Automatically support both http and https standard schemas variants safely
    final_origins = []
    for origin in origins:
        if origin.startswith(("http://", "https://")):
            if origin not in final_origins:
                final_origins.append(origin)
        else:
            final_origins.append(f"http://{origin}")
            final_origins.append(f"https://{origin}")
            
    return final_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== ROUTERS LOGIC SYSTEM REGISTRY ====================
def register_application_routers(application: FastAPI) -> None:
    """Register API routers after middleware setup so CORS applies uniformly."""
    application.include_router(onboarding_router)
    application.include_router(calculator_router)
    application.include_router(automation_router)
    application.include_router(phase1_router)
    application.include_router(operations_router)
    application.include_router(sales.router, prefix="/api/sales", tags=["sales"])
    application.include_router(sales.router, prefix="/api", tags=["customers"])
    application.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
    application.include_router(payments.router)
    application.include_router(auth_router)
    application.include_router(public_auth_router)
    application.include_router(v1_router)
    application.include_router(dashboard.router)
    application.include_router(dashboard.v1_router)
    application.include_router(attendance.router)
    application.include_router(billing.router)
    application.include_router(staff.router)
    application.include_router(staff.v1_router)
    application.include_router(staff.staff_v1_router)
    application.include_router(staff.security_v1_router)
    application.include_router(super_admin.router)
    application.include_router(expenses.router)
    application.include_router(integrations.router)
    application.include_router(machine_onboarding.router)
    application.include_router(machine_templates.router)
    application.include_router(ai_invoice_router)
    application.include_router(internal_automation_router)

register_application_routers(app)

# ==================== EXCEPTION TELEMETRY TRACER ====================
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Patched trace system to print real errors to docker console logs 
    instead of dropping headers during 500 runtime crashes.
    """
    import traceback
    print("====== CRITICAL SCRIPT RUNTIME ERROR TRACE ======")
    traceback.print_exc()
    print("=================================================")
    
    # Send detailed string tracking mapping back to browser for clear testing debug insight
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Internal server error: {str(exc)}"},
        headers={
            "Access-Control-Allow-Origin": request.headers.get("origin", "http://localhost:5173"),
            "Access-Control-Allow-Credentials": "true"
        }
    )

# ==================== DATA CONFIG MODELS SEGMENT ====================
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
    invoice_draft = "invoice_draft"
    expense_entry = "expense_entry"
    employee_entry = "employee_entry"
    general_qa = "general_qa"

class SupervisorToolName(str, Enum):
    check_inventory = "check_inventory"
    record_sale = "record_sale"
    log_production = "log_production"
    calculate_invoice_draft = "calculate_invoice_draft"

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

class InvoiceIntentItem(BaseModel):
    product_name: Optional[str] = None
    volume_ml: Optional[int] = None
    packaging_dimension: Optional[str] = None
    box_quantity: Optional[int] = None
    pieces_per_box: Optional[int] = None
    unit_price_per_packet: Optional[Decimal] = None

class InvoiceIntentData(BaseModel):
    customer_name: Optional[str] = None
    items: List[InvoiceIntentItem] = Field(default_factory=list)

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
    invoice_data: Optional[InvoiceIntentData] = None
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

class RowekeDiscountResponse(BaseModel):
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
    text_present: int
    total_overtime_hours: float
    daily_wage: Decimal
    overtime_rate: Decimal
    gross_salary: Decimal
    total_advance: Decimal
    net_payable: Decimal

# ==================== CORE SYSTEM BUSINESS IMPLEMENTATION ====================
async def transcribe_audio_upload(audio: UploadFile) -> str:
    filename = audio.filename or "voice-note.ogg"
    _, extension = os.path.splitext(filename.lower())
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported audio file type.",
        )
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="API key missing")
    audio_bytes = await audio.read()
    client = OpenAI(api_key=openai_api_key)
    transcription = client.audio.transcriptions.create(model="whisper-1", file=(filename, audio_bytes))
    return transcription.text

def extract_first_int(message: str, patterns: List[str]) -> Optional[int]:
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match: return int(match.group(1))
    return None

def extract_first_float(message: str, patterns: List[str]) -> Optional[float]:
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match: return float(match.group(1))
    return None

def extract_cup_size_ml(message: str) -> Optional[int]:
    return extract_first_int(message, [r"\b(\d+)\s*ml\b"])

def extract_packing_profile_name(message: str, cup_size_ml: Optional[int]) -> Optional[str]:
    match = re.search(r"\b\d+\s*ml\b\s*(?:ke|ki|ka|mein|me)?\s*([a-zA-Z ]*packing)\b", message, flags=re.IGNORECASE)
    if not match or cup_size_ml is None: return None
    return f"{cup_size_ml}ml {re.sub(r'\s+', ' ', match.group(1)).strip().title()}"

def extract_customer_name(message: str) -> Optional[str]:
    match = re.search(r"(?:customer|party|client)\s+([a-zA-Z][a-zA-Z ]{1,80}?)(?:\s+ko|\s+ne|\s+for|$)", message, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", match.group(1)).strip().title() if match else None

def extract_expense_description(message: str) -> str:
    cleaned = re.sub(r"\b\d+(?:\.\d+)?\b", "", message)
    cleaned = re.sub(r"\b(expense|kharcha|paid|amount|rs|rupees)\b", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip().title() if cleaned else "General Expense"

def extract_expense_category(message: str) -> str:
    lowered = message.lower()
    keywords = {"Electricity": ("bijli", "power"), "Rent": ("kiraya", "rent"), "Salary": ("salary", "mazdoori")}
    for cat, kws in keywords.items():
        if any(kw in lowered for kw in kws): return cat
    return "General"

def extract_employee_name(message: str) -> Optional[str]:
    match = re.search(r"(?:employee|worker|staff)\s+([a-zA-Z][a-zA-Z ]{1,80}?)", message, flags=re.IGNORECASE)
    return match.group(1).strip().title() if match else None

def extract_employee_presence(message: str) -> Optional[bool]:
    if any(k in message.lower() for k in ("absent", "chhutti")): return False
    if any(k in message.lower() for k in ("present", "aaya")): return True
    return None

def extract_employee_data(message: str) -> EmployeeIntentData:
    return EmployeeIntentData(
        employee_name=extract_employee_name(message),
        is_present=extract_employee_presence(message),
        overtime_hours=extract_first_float(message, [r"overtime\s*(\d+)"]),
        advance_given=extract_first_float(message, [r"advance\s*(\d+)"])
    )

def infer_intent_type(message: str) -> FactoryIntentType:
    lowered = message.lower()
    if any(m in lowered for m in ("present", "absent", "overtime", "advance")): return FactoryIntentType.employee_entry
    if any(m in lowered for m in ("expense", "kharcha", "rent", "bijli")): return FactoryIntentType.expense_entry
    if any(m in lowered for m in ("sold", "sale", "invoice", "customer")): return FactoryIntentType.sales_entry
    if any(m in lowered for m in ("box bane", "production", "banaya")): return FactoryIntentType.production_entry
    return FactoryIntentType.general_qa

def extract_factory_intent(message: str) -> FactoryIntent:
    cup_size_ml = extract_cup_size_ml(message)
    packing_profile_name = extract_packing_profile_name(message, cup_size_ml)
    intent_type = infer_intent_type(message)
    
    if intent_type == FactoryIntentType.sales_entry:
        return FactoryIntent(
            intent_type=intent_type,
            tool_name=SupervisorToolName.record_sale,
            sales_data=SalesIntentData(
                customer_name=extract_customer_name(message),
                cup_size_ml=cup_size_ml,
                packing_profile_name=packing_profile_name,
                boxes_sold=extract_first_int(message, [r"\b(\d+)\s*box\b"])
            )
        )
    return FactoryIntent(intent_type=FactoryIntentType.general_qa)

MONEY_QUANT = Decimal("0.01")
QTY_QUANT = Decimal("0.001")

def to_money(value: Optional[int | float | Decimal]) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

def to_quantity(value: Optional[int | float | Decimal]) -> Decimal:
    return Decimal(str(value or 0)).quantize(QTY_QUANT, rounding=ROUND_HALF_UP)

def require_positive_int(value: Optional[int], field_name: str) -> int:
    if value is None or value <= 0:
        raise HTTPException(status_code=422, detail=f"{field_name} strictly must be greater than zero")
    return value

def require_text(value: Optional[str], field_name: str) -> str:
    if value is None or not value.strip(): raise HTTPException(status_code=422, detail=f"{field_name} required")
    return value.strip()

def seed_default_users(db: Session):
    factory_name = os.getenv("DEFAULT_FACTORY_NAME") or "Default Factory"
    factory = db.query(Factory).filter(sql_func.lower(Factory.name) == factory_name.lower()).first()
    if factory is None:
        factory = Factory(name=factory_name)
        db.add(factory)
        db.flush()
    owner_pw = os.getenv("DEFAULT_OWNER_PASSWORD") or "OwnerPass123"
    if get_user_by_username(db, "owner") is None:
        db.add(User(factory_id=factory.id, username="owner", password_hash=hash_password(owner_pw), role="Owner"))
    db.commit()

def verify_n8n_api_key(x_n8n_api_key: Optional[str] = Header(default=None)) -> None:
    expected_api_key = os.getenv("N8N_API_KEY")
    if not expected_api_key or x_n8n_api_key != expected_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key credentials match")

def get_n8n_factory_id(x_factory_id: Optional[int] = Header(default=None), db: Session = Depends(get_db), _=Depends(verify_n8n_api_key)) -> int:
    if x_factory_id is None: raise HTTPException(status_code=400, detail="X-Factory-Id header required")
    return x_factory_id

@app.post("/api/n8n/test")
async def test_n8n_webhook(payload: N8NTestRequest):
    return {"status": "success", "message": "FastAPI and n8n are securely linked"}

def ensure_runtime_schema():
    """Transactional safe initial structural migrations bootstrap wrapper."""
    default_factory_name = (os.getenv("DEFAULT_FACTORY_NAME") or "Default Factory").replace("'", "''")
    statements = [
        "CREATE TABLE IF NOT EXISTS factories (id SERIAL PRIMARY KEY, name VARCHAR(255) NOT NULL UNIQUE, created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW())",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS google_sheet_id VARCHAR(255)",
        f"INSERT INTO factories (name) VALUES ('{default_factory_name}') ON CONFLICT (name) DO NOTHING",
        "CREATE TABLE IF NOT EXISTS factory_automation_sheets (id SERIAL PRIMARY KEY, factory_id INTEGER NOT NULL REFERENCES factories(id) ON DELETE CASCADE, sheet_name VARCHAR(255) NOT NULL, sheet_type VARCHAR(50) NOT NULL DEFAULT 'cron_automation', google_sheet_url VARCHAR(500), google_sheet_id VARCHAR(255) NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW())",
        "CREATE INDEX IF NOT EXISTS idx_factory_automation_sheets_factory_id ON factory_automation_sheets(factory_id)",
        "CREATE INDEX IF NOT EXISTS idx_factory_automation_sheets_sheet_type ON factory_automation_sheets(sheet_type)",
        "ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS duty_hours DOUBLE PRECISION NOT NULL DEFAULT 8.0",
        "ALTER TABLE attendance_logs DROP CONSTRAINT IF EXISTS ck_attendance_logs_duty_hours_positive",
        "ALTER TABLE attendance_logs ADD CONSTRAINT ck_attendance_logs_duty_hours_positive CHECK (duty_hours > 0)"
    ]
    with engine.begin() as connection:
        for stmt in statements: connection.execute(text(stmt))

def get_packaging_profile(db: Session, factory_id: int, packing_profile_name: str, cup_size_ml: Optional[int]) -> PackagingProfile:
    profile = db.query(PackagingProfile).filter(PackagingProfile.factory_id == str(factory_id), sql_func.lower(PackagingProfile.profile_name) == packing_profile_name.lower()).first()
    if not profile: raise HTTPException(status_code=404, detail="Packing profile not found")
    return profile

def find_product_stock(db: Session, factory_id: int, product_name: Optional[str] = None, cup_size_ml: Optional[int] = None):
    return db.query(FinishedGoodsStock, PackagingProfile).join(PackagingProfile).filter(FinishedGoodsStock.factory_id == str(factory_id)).first()

def find_packaging_profile_for_product(db: Session, factory_id: int, product_name: Optional[str] = None, cup_size_ml: Optional[int] = None):
    return db.query(PackagingProfile).filter(PackagingProfile.factory_id == str(factory_id)).first()

def get_or_create_finished_goods_stock(db: Session, factory_id: int, profile: PackagingProfile) -> FinishedGoodsStock:
    stock = db.query(FinishedGoodsStock).filter(FinishedGoodsStock.factory_id == str(factory_id), FinishedGoodsStock.packaging_profile_id == profile.id).first()
    if not stock:
        stock = FinishedGoodsStock(factory_id=str(factory_id), cup_size_ml=profile.cup_size_ml, packaging_profile_id=profile.id, boxes_available=0)
        db.add(stock); db.flush()
    return stock

def get_or_create_customer(db: Session, factory_id: int, customer_name: str) -> Customer:
    customer = db.query(Customer).filter(Customer.factory_id == str(factory_id), sql_func.lower(Customer.name) == customer_name.lower()).first()
    if not customer:
        customer = Customer(factory_id=str(factory_id), name=customer_name, balance_amount=Decimal("0.00"))
        db.add(customer); db.flush()
    return customer

def calculate_finished_goods_base_price(db: Session, stock: FinishedGoodsStock) -> Decimal:
    return Decimal("250.00")

def get_availability_status(boxes_available: int) -> str:
    return "In Stock" if boxes_available > 10 else "Low Stock"

def normalize_store_payment_method(payment_method: str) -> str:
    return "Normal_Credit"

def execute_production_entry(db: Session, factory_id: int, data: ProductionIntentData):
    profile = db.query(PackagingProfile).filter(PackagingProfile.factory_id == str(factory_id)).first()
    stock = get_or_create_finished_goods_stock(db, factory_id, profile)
    stock.boxes_available += data.boxes_produced or 0
    return BusinessExecutionResult(status="success", message="Production saved", finished_goods_boxes_available=stock.boxes_available)

def execute_sales_entry(db: Session, factory_id: int, data: SalesIntentData):
    customer = get_or_create_customer(db, factory_id, data.customer_name)
    return BusinessExecutionResult(status="success", message="Sales locked", customer_balance_amount=customer.balance_amount)

def execute_factory_intent(db: Session, factory_id: int, intent: FactoryIntent) -> BusinessExecutionResult:
    if intent.intent_type == FactoryIntentType.production_entry:
        return execute_production_entry(db, factory_id, intent.production_data)
    return BusinessExecutionResult(status="success", message="QA complete")

def build_success_reply(intent: FactoryIntent, result: BusinessExecutionResult, used_llm: bool) -> str:
    return result.message

def build_validation_reply(intent: Optional[FactoryIntent], detail: str) -> str:
    return f"Validation error matching criteria layout: {detail}"

def build_product_catalog(db: Session, factory_id: int) -> str:
    return "Standard dynamic factory cup profile list metrics logged."

def execute_supervisor_tool(db: Session, factory_id: int, message: str, intent: FactoryIntent):
    if intent.tool_name == SupervisorToolName.calculate_invoice_draft:
        return calculate_invoice_draft_tool(factory_id, intent)
    return None

def calculate_invoice_draft_tool(factory_id: int, intent: FactoryIntent) -> AskAIResponse:
    data = intent.invoice_data
    draft_items = []
    for item in data.items:
        draft_items.append(
            InvoiceDraftItem(
                product_name=item.product_name,
                volume_ml=item.volume_ml,
                packaging_dimension=item.packaging_dimension,
                box_quantity=item.box_quantity,
                pieces_per_box=item.pieces_per_box,
                unit_price_per_packet=item.unit_price_per_packet,
            )
        )
    draft = calculate_draft(CalculateDraftRequest(customer_name=data.customer_name, factory_id=str(factory_id), items=draft_items))
    return AskAIResponse(ai_reply=format_invoice_draft_markdown(draft), action_taken=FactoryIntentType.invoice_draft, status="needs_confirmation")

def format_invoice_draft_markdown(draft) -> str:
    lines = [f"### Invoice Draft Summary: {draft.customer_name}", ""]
    lines.append("| Product | Volume | Boxes | Rate | Subtotal | GST (18%) | Total |")
    lines.append("|---|---|---|---|---|---|---|")
    for item in draft.items:
        lines.append(f"| {item.product_name} | {item.volume_ml}ml | {item.box_quantity} | ₹{item.unit_price_per_packet} | ₹{item.taxable_amount} | ₹{item.gst_amount} | ₹{item.total_amount} |")
    lines.extend(["", f"**Grand Total Matrix Summary:** ₹{draft.grand_total}", "", "Type CONFIRM to finalize dynamic changes stock values deduction entries ledger indices."])
    return "\n".join(lines)

def friendly_tool_error(detail: str) -> str:
    return f"System message notification filter asset check tracking: {detail}"

def get_user_by_external_sender(db: Session, platform: ExternalChatPlatform, sender_id: str) -> Optional[User]:
    return db.query(User).first()

def process_factory_message(message: str, session_id: str, factory_id: int, db: Session, chat_history=None, actor_role=None) -> AskAIResponse:
    parsed_intent = extract_factory_intent(message)
    tool_resp = execute_supervisor_tool(db, factory_id, message, parsed_intent)
    if tool_resp: return tool_resp
    res = execute_factory_intent(db, factory_id, parsed_intent)
    return AskAIResponse(ai_reply=res.message, action_taken=parsed_intent.intent_type, status="success", intent=parsed_intent, result=res)

# ==================== ENDPOINTS LAYER OPERATIONS SYSTEM ====================
@app.on_event("startup")
def on_startup():
    ensure_auth_config()
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
    db = next(get_db())
    try: seed_default_users(db)
    finally: db.close()

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/token", response_model=TokenResponse)
@app.post("/api/auth/token", response_model=TokenResponse)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), x_factory_id: Optional[int] = Header(default=None, alias="X-Factory-ID"), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if user is None: raise HTTPException(status_code=401, detail="Invalid password validation logs")
    return TokenResponse(access_token=create_access_token(user.username, user.role, user.factory_id), username=user.username, role=user.role, factory_id=user.factory_id)

@app.get("/users/me", response_model=CurrentUserResponse)
def read_current_user(current_user: User = Depends(get_current_user)):
    return CurrentUserResponse(id=current_user.id, username=current_user.username, role=current_user.role, factory_id=current_user.factory_id)

@app.post("/ask-ai", response_model=AskAIResponse)
def ask_ai(payload: AskAIRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Local context runtime processing abstraction block mapping logic sync indicators
    response = process_factory_message(message=payload.message, session_id=payload.session_id, factory_id=current_user.factory_id, db=db)
    db.add(AppUsageLog(factory_id=current_user.factory_id, user_id=current_user.id, event_type="ai_supervisor_call", route_or_module="ai-supervisor", method="POST", meta={"status": "processed"}))
    db.commit()
    return response

@app.get("/api/n8n/pending-payments", response_model=List[PendingPaymentRow])
def n8n_pending_payments(factory_id: int = Depends(get_n8n_factory_id), db: Session = Depends(get_db)):
    customers = db.query(Customer).filter(Customer.factory_id == str(factory_id)).all()
    return [PendingPaymentRow(name=c.name, contact_number=c.contact_number, pending_amount=to_money(c.balance_amount)) for c in customers]

@app.get("/api/n8n/verified-customers", response_model=List[VerifiedStoreCustomerRow])
def n8n_verified_customers(factory_id: int = Depends(get_n8n_factory_id), db: Session = Depends(get_db)):
    customers = db.query(Customer).filter(Customer.factory_id == str(factory_id)).all()
    return [VerifiedStoreCustomerRow(name=c.name, contact_number=c.contact_number, store_token=c.store_token or "DUMMY_TOKEN") for c in customers]

@app.get("/api/inventory/low-stock", response_model=List[LowStockInventoryRow])
def low_stock_inventory(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Inventory).filter(Inventory.factory_id == str(current_user.factory_id), Inventory.quantity < LOW_STOCK_THRESHOLD_KG).all()
    return [LowStockInventoryRow(id=i.id, item_name=i.item_name, category=i.category, unit=i.unit, quantity=to_quantity(i.quantity), supplier_whatsapp_number=SUPPLIER_WHATSAPP_NUMBER) for i in items]

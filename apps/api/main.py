from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
import hmac
import os
import re
from typing import Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
try:
    from langchain.memory import ConversationBufferMemory
except ImportError:  # LangChain 1.x compatibility
    try:
        from langchain_classic.memory import ConversationBufferMemory
    except ImportError:
        class ConversationBufferMemory:
            def __init__(self, memory_key: str, input_key: str, output_key: str):
                self.memory_key = memory_key
                self.input_key = input_key
                self.output_key = output_key
                self.buffer: List[Tuple[str, str]] = []

            def load_memory_variables(self, _inputs):
                chat_history = "\n".join(
                    f"Human: {human_message}\nAI: {ai_message}"
                    for human_message, ai_message in self.buffer[-10:]
                )
                return {self.memory_key: chat_history}

            def save_context(self, inputs, outputs):
                self.buffer.append(
                    (
                        str(inputs.get(self.input_key, "")),
                        str(outputs.get(self.output_key, "")),
                    )
                )

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from openai import OpenAI, OpenAIError
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func as sql_func, text
from sqlalchemy.orm import Session

from db import Base, engine, get_db
from models import (
    AdvancePayment,
    AttendanceLog,
    Customer,
    CustomerActivity,
    Employee,
    ExpenseLog,
    FactoryInventory,
    FinishedGoodsStock,
    Inventory,
    Order,
    OrderItem,
    PackagingProfile,
    ProductionLog,
    SalesInvoice,
    User,
)

try:
    from langchain_groq import ChatGroq
except ImportError:
    ChatGroq = None

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None


app = FastAPI(title="AI ERP API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InventoryCreate(BaseModel):
    raw_material_name: str = Field(..., min_length=1, max_length=255)
    quantity: int = Field(..., ge=0)


class InventoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    raw_material_name: str
    quantity: int
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class CurrentUserResponse(BaseModel):
    id: int
    username: str
    role: str


class FactoryIntentType(str, Enum):
    production_entry = "production_entry"
    sales_entry = "sales_entry"
    expense_entry = "expense_entry"
    employee_entry = "employee_entry"
    general_qa = "general_qa"


class ProductionIntentData(BaseModel):
    cup_size_ml: Optional[int] = None
    packing_profile_name: Optional[str] = None
    blank_used: Optional[int] = None
    bottom_used: Optional[float] = None
    boxes_produced: Optional[int] = None
    blank_waste: Optional[int] = None
    bottom_waste: Optional[float] = None


class SalesIntentData(BaseModel):
    customer_name: Optional[str] = None
    cup_size_ml: Optional[int] = None
    packing_profile_name: Optional[str] = None
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
    production_data: Optional[ProductionIntentData] = None
    sales_data: Optional[SalesIntentData] = None
    expense_data: Optional[ExpenseIntentData] = None
    employee_data: Optional[EmployeeIntentData] = None
    general_data: Optional[GeneralQAData] = None


class AskAIRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str = Field(default="default", min_length=1, max_length=100)


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
    category: str
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
    category: str
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
    boxes_available: int
    base_price: Decimal


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


factory_intent_parser = PydanticOutputParser(pydantic_object=FactoryIntent)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES") or "480")

factory_intent_prompt = PromptTemplate(
    template=(
        "You are a production ERP extraction assistant for a paper cup factory.\n"
        "Use the chat history for context, but only extract the newest user message.\n"
        "Classify the newest user message as one of: production_entry, sales_entry, expense_entry, employee_entry, general_qa.\n"
        "For database actions, extract only explicit facts. Use null for missing fields.\n"
        "For general_qa, answer briefly in simple Hinglish/English in general_data.answer.\n"
        'Important packing rule: If user says "Aaj 100 box bane 65ml ke Premium Packing me", '
        'extract "65ml Premium Packing" as the packing_profile_name.\n\n'
        'Employee rule: If the user says "Raju was present today, did 2 hours overtime, and took 500 advance", '
        "extract employee_name=Raju, is_present=true, overtime_hours=2, and advance_given=500 into employee_data.\n\n"
        "Chat history:\n{chat_history}\n\n"
        "{format_instructions}\n\n"
        "Newest user message: {user_message}"
    ),
    input_variables=["chat_history", "user_message"],
    partial_variables={
        "format_instructions": factory_intent_parser.get_format_instructions(),
    },
)

SESSION_MEMORIES: Dict[str, ConversationBufferMemory] = {}


def get_session_memory(session_id: str) -> ConversationBufferMemory:
    if session_id not in SESSION_MEMORIES:
        SESSION_MEMORIES[session_id] = ConversationBufferMemory(
            memory_key="chat_history",
            input_key="user_message",
            output_key="ai_reply",
        )
    return SESSION_MEMORIES[session_id]


def initialize_llm():
    groq_api_key = os.getenv("GROQ_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if groq_api_key and ChatGroq is not None:
        return ChatGroq(
            model=os.getenv("GROQ_MODEL") or "llama-3.1-8b-instant",
            temperature=0,
            api_key=groq_api_key,
        )

    if openai_api_key and ChatOpenAI is not None:
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL") or "gpt-4o-mini",
            temperature=0,
            api_key=openai_api_key,
        )

    return None


def parse_factory_intent_with_chain(message: str, session_id: str) -> Tuple[FactoryIntent, bool]:
    memory = get_session_memory(session_id)
    chat_history = memory.load_memory_variables({}).get("chat_history", "")
    llm = initialize_llm()

    if llm is None:
        return extract_factory_intent(message), False

    chain = factory_intent_prompt | llm | factory_intent_parser
    intent = chain.invoke(
        {
            "chat_history": chat_history,
            "user_message": message,
        }
    )
    return intent, True


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
    sales_markers = ("sold", "sale", "invoice", "becha", "beche", "bika", "customer", "payment", "paid", "received")
    expense_markers = ("expense", "kharcha", "rent", "salary", "bijli", "electricity", "repair", "maintenance")
    employee_markers = ("present", "absent", "overtime", " ot ", "advance", "employee", "worker", "staff")
    production_markers = ("box bane", "produced", "production", "blank", "bottom", "waste")

    if any(marker in lowered for marker in employee_markers):
        return FactoryIntentType.employee_entry
    if any(marker in lowered for marker in expense_markers):
        return FactoryIntentType.expense_entry
    if any(marker in lowered for marker in sales_markers):
        return FactoryIntentType.sales_entry
    if any(marker in lowered for marker in production_markers) or re.search(r"\b\d+\s*(?:box|boxes)\b", lowered):
        return FactoryIntentType.production_entry
    if "?" in message or any(word in lowered for word in ("what", "how", "kitna", "kya", "show", "report", "balance")):
        return FactoryIntentType.general_qa
    return FactoryIntentType.production_entry


def extract_factory_intent(message: str) -> FactoryIntent:
    cup_size_ml = extract_cup_size_ml(message)
    packing_profile_name = extract_packing_profile_name(message, cup_size_ml)
    intent_type = infer_intent_type(message)

    if intent_type == FactoryIntentType.sales_entry:
        sales_data = SalesIntentData(
            customer_name=extract_customer_name(message),
            cup_size_ml=cup_size_ml,
            packing_profile_name=packing_profile_name,
            boxes_sold=extract_first_int(message, [r"\b(\d+)\s*(?:box|boxes)\b"]),
            rate_per_box=extract_first_float(message, [r"(?:rate|rate_per_box)\s*(?:is|=|:)?\s*(\d+(?:\.\d+)?)"]),
            amount_received=extract_first_float(
                message,
                [r"(?:received|paid|amount_received|payment)\s*(?:is|=|:)?\s*(\d+(?:\.\d+)?)"],
            ),
        )
        return FactoryIntent(intent_type=intent_type, sales_data=sales_data)

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
        return FactoryIntent(intent_type=intent_type, general_data=general_data)

    production_data = ProductionIntentData(
        cup_size_ml=cup_size_ml,
        packing_profile_name=packing_profile_name,
        blank_used=extract_first_int(message, [r"(?:blank|blanks)\s*(?:used)?\s*(\d+)"]),
        bottom_used=extract_first_float(message, [r"(?:bottom)\s*(?:used)?\s*(\d+(?:\.\d+)?)\s*kg?"]),
        boxes_produced=extract_first_int(message, [r"\b(\d+)\s*(?:box|boxes)\b"]),
        blank_waste=extract_first_int(message, [r"(?:blank|blanks)\s*waste\s*(\d+)"]),
        bottom_waste=extract_first_float(message, [r"(?:bottom)\s*waste\s*(\d+(?:\.\d+)?)\s*kg?"]),
    )
    return FactoryIntent(intent_type=intent_type, production_data=production_data)


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


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(username: str, role: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "role": role,
        "exp": expires_at,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return (
        db.query(User)
        .filter(sql_func.lower(User.username) == username.lower())
        .first()
    )


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = get_user_by_username(db, username)
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        if not isinstance(username, str) or not username:
            raise credentials_error
    except JWTError as exc:
        raise credentials_error from exc

    user = get_user_by_username(db, username)
    if user is None:
        raise credentials_error
    return user


def require_owner(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "Owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner role is required",
        )
    return current_user


def seed_default_users(db: Session):
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
            db.add(User(username=username, password_hash=hash_password(password), role=role))
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


def ensure_runtime_schema():
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(50) NOT NULL DEFAULT 'Operator'",
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role",
        "ALTER TABLE users ADD CONSTRAINT ck_users_role CHECK (role IN ('Owner', 'Operator'))",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS contact_number VARCHAR(50)",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS store_token VARCHAR(255)",
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS advance_discount_pct DOUBLE PRECISION NOT NULL DEFAULT 5.0",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_store_token ON customers (store_token) WHERE store_token IS NOT NULL",
        (
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'orders' AND column_name = 'payment_type') "
            "AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'orders' AND column_name = 'payment_method') "
            "THEN ALTER TABLE orders RENAME COLUMN payment_type TO payment_method; "
            "END IF; END $$"
        ),
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_discount_revoked BOOLEAN NOT NULL DEFAULT false",
        "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS base_rate NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders_payment_type",
        "ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders_payment_method",
        "UPDATE orders SET payment_method = 'Full_Advance_Doorstep' WHERE payment_method = 'Advance'",
        "UPDATE orders SET payment_method = 'Normal_Credit' WHERE payment_method = 'Credit'",
        "UPDATE order_items SET base_rate = final_rate WHERE base_rate = 0",
        (
            "ALTER TABLE orders ADD CONSTRAINT ck_orders_payment_method "
            "CHECK (payment_method IN ('Normal_Credit', 'Full_Advance_UPI', 'Full_Advance_Doorstep'))"
        ),
        "ALTER TABLE order_items DROP CONSTRAINT IF EXISTS ck_order_items_base_rate_non_negative",
        (
            "ALTER TABLE order_items ADD CONSTRAINT ck_order_items_base_rate_non_negative "
            "CHECK (base_rate >= 0)"
        ),
        "ALTER TABLE production_logs ADD COLUMN IF NOT EXISTS box_packing_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE production_logs ADD COLUMN IF NOT EXISTS poly_packing_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE production_logs ADD COLUMN IF NOT EXISTS total_packing_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE production_logs ADD COLUMN IF NOT EXISTS blank_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE production_logs ADD COLUMN IF NOT EXISTS bottom_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE production_logs ADD COLUMN IF NOT EXISTS total_raw_material_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
        "ALTER TABLE production_logs ADD COLUMN IF NOT EXISTS total_production_cost NUMERIC(14, 2) NOT NULL DEFAULT 0",
    ]

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def get_packaging_profile(
    db: Session,
    packing_profile_name: str,
    cup_size_ml: Optional[int],
) -> PackagingProfile:
    profile = (
        db.query(PackagingProfile)
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


def get_raw_inventory(db: Session, keyword: str, unit: str) -> Inventory:
    inventory_item = (
        db.query(Inventory)
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


def get_or_create_finished_goods_stock(db: Session, profile: PackagingProfile) -> FinishedGoodsStock:
    stock = (
        db.query(FinishedGoodsStock)
        .filter(FinishedGoodsStock.packaging_profile_id == profile.id)
        .first()
    )
    if stock is not None:
        return stock

    stock = FinishedGoodsStock(
        cup_size_ml=profile.cup_size_ml,
        packaging_profile_id=profile.id,
        boxes_available=0,
    )
    db.add(stock)
    db.flush()
    return stock


def get_or_create_customer(db: Session, customer_name: str) -> Customer:
    customer = (
        db.query(Customer)
        .filter(sql_func.lower(Customer.name) == customer_name.lower())
        .first()
    )
    if customer is not None:
        return customer

    customer = Customer(name=customer_name, balance_amount=Decimal("0.00"))
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


def get_store_customer(db: Session, store_token: str) -> Customer:
    customer = (
        db.query(Customer)
        .filter(Customer.store_token == store_token)
        .first()
    )
    if customer is not None:
        return customer

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Storefront not found",
    )


def calculate_finished_goods_base_price(db: Session, stock: FinishedGoodsStock) -> Decimal:
    latest_sale = (
        db.query(SalesInvoice)
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
        .filter(ProductionLog.packaging_profile_id == stock.packaging_profile_id)
        .filter(ProductionLog.boxes_produced > 0)
        .filter(ProductionLog.total_production_cost > 0)
        .order_by(ProductionLog.date.desc(), ProductionLog.id.desc())
        .first()
    )
    if latest_production is not None:
        return to_money(to_money(latest_production.total_production_cost) / Decimal(latest_production.boxes_produced))

    return Decimal("0.00")


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


def get_employee_by_name(db: Session, employee_name: str) -> Employee:
    employee = (
        db.query(Employee)
        .filter(sql_func.lower(Employee.name) == employee_name.lower())
        .first()
    )
    if employee is not None:
        return employee

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Employee not found: {employee_name}",
    )


def execute_production_entry(db: Session, data: ProductionIntentData) -> BusinessExecutionResult:
    packing_profile_name = require_text(data.packing_profile_name, "packing_profile_name")
    boxes_produced = require_positive_int(data.boxes_produced, "boxes_produced")
    profile = get_packaging_profile(db, packing_profile_name, data.cup_size_ml)

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
        blank_inventory = get_raw_inventory(db, "blank", "pieces")
        deduct_inventory(blank_inventory, blank_consumed, "blank raw material")
        blank_cost = to_money(blank_consumed * to_money(blank_inventory.price_per_unit))

    bottom_cost = Decimal("0.00")
    if bottom_consumed > 0:
        bottom_inventory = get_raw_inventory(db, "bottom", "kg")
        deduct_inventory(bottom_inventory, bottom_consumed, "bottom raw material")
        bottom_cost = to_money(bottom_consumed * to_money(bottom_inventory.price_per_unit))

    total_raw_material_cost = to_money(blank_cost + bottom_cost)
    total_production_cost = to_money(total_packing_cost + total_raw_material_cost)

    production_log = ProductionLog(
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

    finished_stock = get_or_create_finished_goods_stock(db, profile)
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


def execute_sales_entry(db: Session, data: SalesIntentData) -> BusinessExecutionResult:
    customer_name = require_text(data.customer_name, "customer_name")
    packing_profile_name = require_text(data.packing_profile_name, "packing_profile_name")
    boxes_sold = require_positive_int(data.boxes_sold, "boxes_sold")
    if data.rate_per_box is None or data.rate_per_box <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="rate_per_box is required and must be greater than zero",
        )

    profile = get_packaging_profile(db, packing_profile_name, data.cup_size_ml)
    finished_stock = get_or_create_finished_goods_stock(db, profile)
    available_finished_boxes = finished_stock.boxes_available or 0
    if available_finished_boxes < boxes_sold:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Insufficient finished goods for {profile.profile_name}. "
                f"Required {boxes_sold}, available {available_finished_boxes}"
            ),
        )

    customer = get_or_create_customer(db, customer_name)
    total_amount = to_money(Decimal(boxes_sold) * to_money(data.rate_per_box))
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


def execute_expense_entry(db: Session, data: ExpenseIntentData) -> BusinessExecutionResult:
    description = require_text(data.description, "description")
    category = data.category.strip() if data.category else "General"
    amount = to_money(data.amount)
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="amount is required and must be greater than zero for expense_entry",
        )

    expense_log = ExpenseLog(
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


def execute_employee_entry(db: Session, data: EmployeeIntentData) -> BusinessExecutionResult:
    employee_name = require_text(data.employee_name, "employee_name")
    employee = get_employee_by_name(db, employee_name)

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
            .filter(AttendanceLog.employee_id == employee.id)
            .filter(AttendanceLog.date == date.today())
            .first()
        )
        is_present = data.is_present if data.is_present is not None else overtime_hours > 0
        if attendance_log is None:
            attendance_log = AttendanceLog(
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


def execute_factory_intent(db: Session, intent: FactoryIntent) -> BusinessExecutionResult:
    try:
        if intent.intent_type == FactoryIntentType.production_entry:
            if intent.production_data is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="production_data is required for production_entry",
                )
            result = execute_production_entry(db, intent.production_data)
        elif intent.intent_type == FactoryIntentType.sales_entry:
            if intent.sales_data is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="sales_data is required for sales_entry",
                )
            result = execute_sales_entry(db, intent.sales_data)
        elif intent.intent_type == FactoryIntentType.expense_entry:
            if intent.expense_data is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="expense_data is required for expense_entry",
                )
            result = execute_expense_entry(db, intent.expense_data)
        elif intent.intent_type == FactoryIntentType.employee_entry:
            if intent.employee_data is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="employee_data is required for employee_entry",
                )
            result = execute_employee_entry(db, intent.employee_data)
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
    model,
    column,
    start_date: Optional[date],
    end_date: Optional[date],
) -> Decimal:
    query = db.query(sql_func.coalesce(sql_func.sum(column), 0)).select_from(model)
    if start_date is not None:
        query = query.filter(model.date >= start_date)
    if end_date is not None:
        query = query.filter(model.date <= end_date)
    return to_money(query.scalar())


def build_recent_7_days(db: Session) -> List[DailyProductionSales]:
    today = date.today()
    start_day = today - timedelta(days=6)

    production_rows = (
        db.query(ProductionLog.date, sql_func.coalesce(sql_func.sum(ProductionLog.boxes_produced), 0))
        .filter(ProductionLog.date >= start_day)
        .filter(ProductionLog.date <= today)
        .group_by(ProductionLog.date)
        .all()
    )
    sales_rows = (
        db.query(SalesInvoice.date, sql_func.coalesce(sql_func.sum(SalesInvoice.boxes_sold), 0))
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


def calculate_wastage_mix(db: Session) -> WastageMix:
    rows = (
        db.query(
            ProductionLog.boxes_produced,
            ProductionLog.blank_waste_pcs,
            ProductionLog.bottom_waste_kg,
            PackagingProfile.cups_per_poly,
            PackagingProfile.polys_per_box,
        )
        .join(PackagingProfile, ProductionLog.packaging_profile_id == PackagingProfile.id)
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


def current_month_bounds() -> Tuple[date, date, date]:
    today = date.today()
    month_start = today.replace(day=1)
    if month_start.month == 12:
        next_month_start = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month_start = month_start.replace(month=month_start.month + 1)
    month_end = next_month_start - timedelta(days=1)
    return month_start, next_month_start, month_end


@app.on_event("startup")
def on_startup():
    if not JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY environment variable is required")

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
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=create_access_token(user.username, user.role),
        username=user.username,
        role=user.role,
    )


@app.get("/users/me", response_model=CurrentUserResponse)
def read_current_user(current_user: User = Depends(get_current_user)):
    return CurrentUserResponse(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
    )


def process_factory_message(message: str, session_id: str, db: Session) -> AskAIResponse:
    memory = get_session_memory(session_id)
    parsed_intent: Optional[FactoryIntent] = None
    parser_warning: Optional[str] = None

    try:
        parsed_intent, used_llm = parse_factory_intent_with_chain(message, session_id)
    except Exception as exc:
        parsed_intent = extract_factory_intent(message)
        used_llm = False
        parser_warning = f"LLM parser failed; local parser fallback was used: {exc}"

    try:
        result = execute_factory_intent(db, parsed_intent)
    except HTTPException as exc:
        detail = str(exc.detail)
        ai_reply = build_validation_reply(parsed_intent, detail)
        memory.save_context({"user_message": message}, {"ai_reply": ai_reply})
        return AskAIResponse(
            ai_reply=ai_reply,
            action_taken=parsed_intent.intent_type,
            status="validation_error",
            intent=parsed_intent,
            error=detail,
        )

    ai_reply = build_success_reply(parsed_intent, result, used_llm)
    memory.save_context({"user_message": message}, {"ai_reply": ai_reply})
    return AskAIResponse(
        ai_reply=ai_reply,
        action_taken=parsed_intent.intent_type,
        status=result.status,
        intent=parsed_intent,
        result=result,
        error=parser_warning,
    )


@app.post("/ask-ai", response_model=AskAIResponse)
def ask_ai(payload: AskAIRequest, db: Session = Depends(get_db)):
    return process_factory_message(payload.message, payload.session_id, db)


@app.post("/api/webhook/whatsapp", response_model=AskAIResponse)
async def whatsapp_voice_webhook(
    audio: UploadFile = File(...),
    session_id: str = Form(default="whatsapp"),
    db: Session = Depends(get_db),
):
    transcribed_text = await transcribe_audio_upload(audio)
    return process_factory_message(transcribed_text, session_id, db)


@app.get("/report/profit-loss", response_model=ProfitLossReport)
def profit_loss_report(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    revenue = sum_decimal(db, SalesInvoice, SalesInvoice.total_amount, start_date, end_date)
    cash_received = sum_decimal(db, SalesInvoice, SalesInvoice.amount_paid, start_date, end_date)
    total_packing_cost = sum_decimal(db, ProductionLog, ProductionLog.total_packing_cost, start_date, end_date)
    total_expenses = sum_decimal(db, ExpenseLog, ExpenseLog.amount, start_date, end_date)
    total_raw_material_cost = sum_decimal(
        db,
        ProductionLog,
        ProductionLog.total_raw_material_cost,
        start_date,
        end_date,
    )
    total_production_cost = sum_decimal(
        db,
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
def dashboard_stats(db: Session = Depends(get_db)):
    today = date.today()
    month_start = today.replace(day=1)
    monthly_revenue = sum_decimal(db, SalesInvoice, SalesInvoice.total_amount, month_start, today)
    monthly_production_cost = sum_decimal(
        db,
        ProductionLog,
        ProductionLog.total_production_cost,
        month_start,
        today,
    )
    monthly_expenses = sum_decimal(db, ExpenseLog, ExpenseLog.amount, month_start, today)
    total_pending_recoveries = to_money(
        db.query(sql_func.coalesce(sql_func.sum(Customer.balance_amount), 0)).scalar()
    )
    total_boxes_in_stock = int(
        db.query(sql_func.coalesce(sql_func.sum(FinishedGoodsStock.boxes_available), 0)).scalar() or 0
    )
    wastage_mix = calculate_wastage_mix(db)

    return DashboardStats(
        monthly_net_profit=to_money(monthly_revenue - monthly_production_cost - monthly_expenses),
        total_pending_recoveries=total_pending_recoveries,
        total_boxes_in_stock=total_boxes_in_stock,
        overall_wastage_percent=calculate_wastage_percent(wastage_mix),
        recent_7_days=build_recent_7_days(db),
        wastage_mix=wastage_mix,
    )


@app.get("/report/customer-balance", response_model=List[CustomerBalanceRow])
def customer_balance_report(db: Session = Depends(get_db)):
    rows = (
        db.query(
            Customer.name,
            sql_func.coalesce(sql_func.sum(SalesInvoice.total_amount), 0),
            Customer.balance_amount,
        )
        .outerjoin(SalesInvoice, SalesInvoice.customer_id == Customer.id)
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


@app.get(
    "/api/n8n/pending-payments",
    response_model=List[PendingPaymentRow],
    dependencies=[Depends(verify_n8n_api_key)],
)
def n8n_pending_payments(db: Session = Depends(get_db)):
    customers = (
        db.query(Customer)
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
    dependencies=[Depends(verify_n8n_api_key)],
)
def n8n_verified_customers(db: Session = Depends(get_db)):
    customers = (
        db.query(Customer)
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
def low_stock_inventory(db: Session = Depends(get_db)):
    low_stock_items = (
        db.query(Inventory)
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
def production_log_report(limit: int = 100, db: Session = Depends(get_db)):
    bounded_limit = min(max(limit, 1), 500)
    rows = (
        db.query(ProductionLog, PackagingProfile)
        .join(PackagingProfile, ProductionLog.packaging_profile_id == PackagingProfile.id)
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

    return report_rows


@app.get("/report/live-inventory", response_model=LiveInventoryReport)
def live_inventory_report(db: Session = Depends(get_db)):
    raw_materials = (
        db.query(Inventory)
        .filter(Inventory.category == "Raw")
        .order_by(Inventory.item_name.asc())
        .all()
    )
    packaging_materials = (
        db.query(Inventory)
        .filter(Inventory.category == "Packaging")
        .order_by(Inventory.item_name.asc())
        .all()
    )
    finished_goods = (
        db.query(FinishedGoodsStock, PackagingProfile)
        .join(PackagingProfile, FinishedGoodsStock.packaging_profile_id == PackagingProfile.id)
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
    customer = get_store_customer(db, store_token)
    db.add(CustomerActivity(customer_id=customer.id, activity_type="Viewed Store"))
    db.commit()

    available_stocks = (
        db.query(FinishedGoodsStock)
        .join(PackagingProfile, FinishedGoodsStock.packaging_profile_id == PackagingProfile.id)
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
                boxes_available=stock.boxes_available,
                base_price=calculate_finished_goods_base_price(db, stock),
            )
            for stock in available_stocks
        ],
    )


@app.post("/api/store/{store_token}/checkout", response_model=StoreCheckoutResponse)
def checkout_storefront(
    store_token: str,
    payload: StoreCheckoutRequest,
    db: Session = Depends(get_db),
):
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
        db.commit()
        discount_amount = to_money(base_total_amount - total_amount)
        return StoreCheckoutResponse(
            message="Order placed successfully and stock reserved for approval",
            order_id=order.id,
            status=order.status,
            payment_method=order.payment_method,
            discount_pct=discount_pct,
            discount_amount=discount_amount,
            total_amount=total_amount,
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
def employee_report(employee_id: int, db: Session = Depends(get_db)):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
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
        .filter(*attendance_filters)
        .filter(AttendanceLog.is_present.is_(True))
        .scalar()
        or 0
    )
    total_overtime_hours = float(
        db.query(sql_func.coalesce(sql_func.sum(AttendanceLog.overtime_hours), 0))
        .filter(*attendance_filters)
        .scalar()
        or 0
    )
    total_advance = to_money(
        db.query(sql_func.coalesce(sql_func.sum(AdvancePayment.amount), 0))
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
def list_inventory(db: Session = Depends(get_db)):
    return (
        db.query(FactoryInventory)
        .order_by(FactoryInventory.updated_at.desc(), FactoryInventory.id.desc())
        .all()
    )


@app.post(
    "/inventory",
    response_model=InventoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_inventory_item(item: InventoryCreate, db: Session = Depends(get_db)):
    inventory_item = FactoryInventory(
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

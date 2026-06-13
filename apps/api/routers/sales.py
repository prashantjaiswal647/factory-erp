from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
import logging
import os
import re
import zipfile

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, field_validator, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import String, cast, or_, func as sql_func, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload


from dependencies import OWNER_ROLES, SALES_ROLES, check_permissions
from db import get_db
from models import BoxStock, Customer, DailySale, Factory, FactoryAutomationSheet, FinalProductStock, FinishedGoodsStock, InvoiceDeliveryLog, InvoiceDocument, Order, OrderItem, Payment, RecycledInvoice, TelegramUserBinding, User, ActivityLog, OutstandingBill, PaymentCollection, PackagingProfile, FactorySettings
from routers.payments import customer_phone, send_n8n_whatsapp_event
from schemas import CustomerCreate, CustomerResponse, DailySaleCreate, DailySaleResponse
from services.accounting import create_outstanding_bill, sync_customer_balance_from_bills, active_customer_outstanding, apply_payment_to_outstanding_bills
from services.activity_logger import log_activity
from services.invoice_pdf import build_invoice_pdf_bytes
from services.n8n_sync import sync_data_to_n8n_bg
from services.telegram_action_alerts import (
    notify_customer_created,
    notify_outstanding_threshold_crossed,
    notify_sale_created,
)
from telegram_crypto import decrypt_token


router = APIRouter()
MONEY_QUANT = Decimal("0.01")
logger = logging.getLogger(__name__)
GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
ALLOWED_GST_RATES = {0.0, 0.1, 0.25, 1.0, 1.5, 3.0, 5.0, 6.0, 7.5, 12.0, 18.0, 28.0}


def to_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def factory_id_text(factory_id) -> str:
    return str(factory_id).strip()


def factory_id_filter(column, factory_id):
    return cast(column, String) == factory_id_text(factory_id)


def json_safe(value):
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def require_sold_quantity(boxes_sold: int, loose_packets_sold: int) -> None:
    if boxes_sold <= 0 and loose_packets_sold <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one sold quantity is required")


def effective_rate_per_box(item) -> Decimal:
    rate_per_box = to_money(item.rate_per_box)
    if rate_per_box > 0:
        return rate_per_box
    return to_money(to_money(item.rate_per_packet) * Decimal(item.packets_per_box or 0))


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def gst_state_code(value: str | None) -> str | None:
    cleaned = clean_optional_text(value)
    if not cleaned or len(cleaned) < 2:
        return None
    return cleaned[:2].upper()


def validate_gst_invoice(invoice_type: str, buyer_gstin: str | None, tax_rates: list[float]) -> None:
    if invoice_type != "tax_invoice":
        return
    cleaned_gstin = (buyer_gstin or "").strip().upper()
    if cleaned_gstin and not GSTIN_PATTERN.fullmatch(cleaned_gstin):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid buyer GSTIN format")
    for rate in tax_rates:
        normalized = round(float(rate or 0), 2)
        if normalized not in ALLOWED_GST_RATES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unsupported GST rate: {normalized:g}%")


def same_place_text(left: str | None, right: str | None) -> bool:
    left_clean = (left or "").strip().lower()
    right_clean = (right or "").strip().lower()
    return bool(left_clean and right_clean and (left_clean in right_clean or right_clean in left_clean))


def is_intra_state_supply(factory: Factory | None, buyer_gstin: str | None, place_of_supply: str | None) -> bool:
    factory_gstin_code = gst_state_code(getattr(factory, "gst_number", None))
    buyer_gstin_code = gst_state_code(buyer_gstin)
    if factory_gstin_code and buyer_gstin_code:
        return factory_gstin_code == buyer_gstin_code

    supply_code = gst_state_code(place_of_supply)
    if factory_gstin_code and supply_code and supply_code[:2].isdigit():
        return factory_gstin_code == supply_code

    factory_place = getattr(factory, "address_place", None) or getattr(factory, "address", None)
    if place_of_supply and factory_place:
        return same_place_text(place_of_supply, factory_place)

    return True


def _invoice_counter_attr(invoice_type: str | None) -> str:
    """Map invoice_type string to the Factory column name for that counter."""
    if invoice_type == "tax_invoice":
        return "next_tax_invoice_number"
    if invoice_type in ("bill_of_supply",):
        return "next_bill_of_supply_number"
    if invoice_type in ("BILL_OF_SUPPLY_SIMPLE", "bill_of_supply_simple"):
        return "next_bill_of_supply_simple_number"
    return "next_bill_of_supply_number"


def _settings_counter_attr(invoice_type: str | None) -> str:
    if invoice_type == "tax_invoice":
        return "tax_invoice_start_seq"
    if invoice_type in ("BILL_OF_SUPPLY_SIMPLE", "bill_of_supply_simple"):
        return "bill_of_supply_simple_start_seq"
    return "bill_of_supply_start_seq"


def get_or_create_factory_settings(db: Session, factory_id: int, for_update: bool = False) -> FactorySettings:
    query = db.query(FactorySettings).filter(FactorySettings.factory_id == int(factory_id))
    if for_update:
        query = query.with_for_update()
    settings = query.first()
    if settings is None:
        settings = FactorySettings(factory_id=int(factory_id))
        db.add(settings)
        db.flush()
    return settings


def allocate_invoice_number(db: Session, factory: Factory | None, invoice_type: str | None = None) -> str:
    if factory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Factory not found")

    recycled_entry = (
        db.query(RecycledInvoice)
        .filter(RecycledInvoice.factory_id == factory.id)
        .order_by(RecycledInvoice.recycled_number.asc())
        .with_for_update()
        .first()
    )
    if recycled_entry is not None:
        invoice_counter = recycled_entry.recycled_number
        db.delete(recycled_entry)
        db.flush()
    else:
        attr = _invoice_counter_attr(invoice_type)
        settings_attr = _settings_counter_attr(invoice_type)
        settings = get_or_create_factory_settings(db, factory.id, for_update=True)
        invoice_counter = getattr(settings, settings_attr, None) or getattr(factory, attr, None) or 1
        setattr(settings, settings_attr, int(invoice_counter) + 1)
        setattr(factory, attr, int(invoice_counter) + 1)

    prefix = clean_optional_text(getattr(factory, "invoice_prefix", None)) or "INV-"
    return f"{prefix}{invoice_counter}"


def preview_invoice_number(db: Session, factory: Factory | None, invoice_type: str | None = None) -> str:
    if factory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Factory not found")

    recycled_entry = (
        db.query(RecycledInvoice)
        .filter(RecycledInvoice.factory_id == factory.id)
        .order_by(RecycledInvoice.recycled_number.asc())
        .first()
    )
    prefix = clean_optional_text(getattr(factory, "invoice_prefix", None)) or "INV-"
    if recycled_entry is not None:
        return f"{prefix}{recycled_entry.recycled_number}"
    attr = _invoice_counter_attr(invoice_type)
    settings_attr = _settings_counter_attr(invoice_type)
    settings = db.query(FactorySettings).filter(FactorySettings.factory_id == int(factory.id)).first()
    counter = (
        getattr(settings, settings_attr, None)
        if settings is not None
        else getattr(factory, attr, None)
    ) or getattr(factory, attr, None) or 1
    return f"{prefix}{counter}"


@router.get("/next-invoice-number")
def get_next_invoice_number(
    invoice_type: str | None = None,
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    factory = db.query(Factory).filter(Factory.id == current_user.factory_id).first()
    invoice_number = preview_invoice_number(db, factory, invoice_type)
    return {"invoice_number": invoice_number}


def sync_next_invoice_setting(db: Session, factory: Factory | None, used_invoice_number: str | None, invoice_type: str | None = None) -> None:
    if factory is None:
        return
    invoice_number = clean_optional_text(used_invoice_number)
    if not invoice_number:
        return

    import re
    match = re.match(r"^(.*?)(\d+)$", invoice_number)
    if not match:
        return

    prefix, numeric_part = match.groups()
    next_counter = int(numeric_part) + 1
    factory.invoice_prefix = prefix
    attr = _invoice_counter_attr(invoice_type)
    settings_attr = _settings_counter_attr(invoice_type)
    settings = get_or_create_factory_settings(db, factory.id, for_update=True)
    setattr(settings, settings_attr, max(next_counter, getattr(settings, settings_attr, 1) or 1))
    setattr(factory, attr, max(next_counter, getattr(factory, attr, 1) or 1))




def resolve_factory_google_sheet_id(db: Session, factory_id: str) -> str | None:
    factory = db.query(Factory).filter(factory_id_filter(Factory.id, factory_id)).first()
    if factory is not None and factory.google_sheet_id:
        return factory.google_sheet_id

    sheet = (
        db.query(FactoryAutomationSheet)
        .filter(factory_id_filter(FactoryAutomationSheet.factory_id, factory_id))
        .filter(FactoryAutomationSheet.is_active.is_(True))
        .order_by(FactoryAutomationSheet.updated_at.desc(), FactoryAutomationSheet.created_at.desc())
        .first()
    )
    return sheet.google_sheet_id if sheet else None


def build_order_invoice_payload(db: Session, factory_id: str, order: Order) -> dict:
    line_items = [
        {
            "product_size_ml": item.product_size_ml,
            "variety": (item.variety or "").strip(),
            "packaging_size_name": (item.packaging_size_name or "").strip(),
            "boxes_sold": item.boxes_sold or 0,
            "loose_packets_sold": item.loose_packets_sold or 0,
            "rate_per_box": effective_rate_per_box(item),
            "rate_per_packet": to_money(item.rate_per_packet),
            "line_total": to_money(item.final_rate),
        }
        for item in order.items
    ]
    return {
        "event": "invoice.created",
        "factory_id": factory_id,
        "google_spreadsheet_id": resolve_factory_google_sheet_id(db, factory_id),
        "target_sheet_name": f"Factory_{factory_id}_Sales",
        "sync_type": "sales",
        "action": "insert",
        "document_policy": {
            "legal_invoice_type": "bill_of_supply",
            "legal_invoice_number": str(order.id),
            "rough_bill_enabled": True,
            "rough_bill_number": f"RB-{order.id}",
            "rough_bill_label": "Customer Understanding Bill",
            "rough_bill_disclaimer": "Internal customer understanding and rate settlement document. Not a government tax invoice.",
        },
        "invoice": {
            "invoice_id": order.id,
            "sale_ids": [order.id],
            "invoice_date": order.order_date.date() if order.order_date else datetime.now(timezone.utc).date(),
            "customer_id": order.customer_id,
            "customer_name": order.customer.name if order.customer else "",
            "customer_phone": customer_display_phone(order.customer) if order.customer else "",
            "payment_method": order.payment_method,
            "bill_total": to_money(order.total_amount),
            "amount_paid": to_money(order.amount_paid),
            "previous_due": Decimal("0.00"),
            "customer_total_due": to_money(order.customer.total_due or order.customer.balance_amount or 0) if order.customer else Decimal("0.00"),
            "status": order.status,
        },
        "items": line_items,
    }


def payment_status_for(total_amount: Decimal, amount_paid: Decimal) -> str:
    paid = to_money(amount_paid)
    total = to_money(total_amount)
    if paid <= 0:
        return "Unpaid"
    if paid >= total:
        return "Paid"
    return "Half-Paid"


def find_final_stock_for_sale(db: Session, factory_id, item, *, lock: bool = False) -> FinalProductStock | None:
    query = db.query(FinalProductStock).filter(factory_id_filter(FinalProductStock.factory_id, factory_id))
    product_id = getattr(item, "product_id", None)
    if product_id:
        query = query.filter(FinalProductStock.id == product_id)
    else:
        packaging_size = (getattr(item, "packaging_size", None) or item.packaging_size_name or "").strip()
        query = (
            query
            .filter(FinalProductStock.product_size_ml == item.product_size_ml)
            .filter(sql_func.lower(FinalProductStock.variety) == (item.variety or "").strip().lower())
            .filter(sql_func.lower(FinalProductStock.packaging_size_name) == packaging_size.lower())
        )
    if lock:
        query = query.with_for_update()
    return query.first()


def ensure_variation_stock_available(stock: FinalProductStock, boxes_sold: int, loose_packets_sold: int) -> tuple[int, int, int]:
    packets_per_box = stock.packets_per_box_limit or 1
    available_packets = (stock.total_boxes or 0) * packets_per_box + (stock.loose_packets or 0)
    requested_packets = (boxes_sold or 0) * packets_per_box + (loose_packets_sold or 0)
    if available_packets < requested_packets:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot complete sale. Variation stock is insufficient.")
    return packets_per_box, available_packets, requested_packets

class CustomerBalanceResponse(BaseModel):
    customer_id: int
    customer_name: str
    previous_due: float
    total_due: float


class CustomerSearchResponse(BaseModel):
    id: int
    name: str
    email: str | None = None
    place: str
    phone_number: str
    gst_number: str | None = None
    company_name: str | None = None
    previous_due: Decimal = Decimal("0.00")
    opening_outstanding: Decimal = Decimal("0.00")
    current_outstanding: Decimal = Decimal("0.00")
    opening_outstanding_remaining: Decimal = Decimal("0.00")
    invoice_outstanding_remaining: Decimal = Decimal("0.00")
    manual_adjustment_remaining: Decimal = Decimal("0.00")
    opening_outstanding_note: str | None = None
    opening_outstanding_date: date | None = None
    advance_balance: Decimal = Decimal("0.00")
    advance_balance_note: str | None = None
    advance_balance_date: date | None = None


class BillCustomerOption(BaseModel):
    id: int
    name: str
    phone_number: str
    place: str = ""
    telegram_id: str | None = None


class BillOrderOption(BaseModel):
    id: int
    order_date: str
    status: str
    total_amount: str
    payment_method: str


class BillNotificationRequest(BaseModel):
    order_id: int
    customer_id: int


class BillNotificationResponse(BaseModel):
    message: str
    order_id: int
    customer_id: int
    owner_channel: str
    customer_channel: str
    bill_summary: str


class SalesOrderCreateResponse(BaseModel):
    order_id: int
    sale_ids: list[int]
    customer_id: int
    bill_total: Decimal
    amount_paid: Decimal
    customer_total_due: Decimal
    status: str


class PendingSaleItemResponse(BaseModel):
    product_size_ml: int | None = None
    variety: str | None = None
    packaging_size_name: str | None = None
    boxes_sold: int
    loose_packets_sold: int
    rate_per_box: Decimal
    rate_per_packet: Decimal


class PendingSaleResponse(BaseModel):
    order_id: int
    customer_id: int
    customer_name: str
    customer_phone: str
    total_amount: Decimal
    status: str
    order_date: str
    items: list[PendingSaleItemResponse]


class BillPaymentLogResponse(BaseModel):
    id: int
    amount_allocated: Decimal
    payment_date: str
    received_by_name: str | None = None
    received_by_role: str | None = None


class OutstandingBillResponse(BaseModel):
    bill_id: int | None = None
    order_id: int | None = None
    order_date: str
    bill_amount: Decimal
    amount_paid: Decimal
    remaining_balance: Decimal
    status: str
    source_type: str = "invoice"
    source_label: str = "Invoice"
    stock_impact: bool = False
    note: str | None = None
    payments: list[BillPaymentLogResponse] = []


class OutstandingCustomerBillsResponse(BaseModel):
    customer_id: int
    customer_name: str
    customer_phone: str
    place: str = ""
    total_bill_amount: Decimal
    total_paid: Decimal
    current_pending_balance: Decimal
    opening_outstanding: Decimal = Decimal("0.00")
    advance_balance: Decimal = Decimal("0.00")
    opening_outstanding_remaining: Decimal = Decimal("0.00")
    invoice_outstanding_remaining: Decimal = Decimal("0.00")
    manual_adjustment_remaining: Decimal = Decimal("0.00")
    bills: list[OutstandingBillResponse]


class SalesOutstandingResponse(BaseModel):
    grand_total_outstanding: Decimal
    source_totals: dict[str, Decimal] = {}
    customers: list[OutstandingCustomerBillsResponse]


class PendingDueResponse(BaseModel):
    customer_name: str
    customer_phone: str
    invoice_id: int
    date: str
    total_amount: Decimal
    pending_amount: Decimal
    payment_status: str


class SalesOrderActionResponse(BaseModel):
    message: str
    order_id: int | None = None
    status: str


class InvoicePaymentSummary(BaseModel):
    payment_date: str
    amount_paid: Decimal
    payment_mode: str


class InvoiceDocumentSummary(BaseModel):
    id: int
    invoice_number: str
    invoice_date: str
    customer_id: int | None = None
    customer_name: str
    customer_phone: str | None = None
    customer_email: str | None = None
    payment_method: str
    bill_total: Decimal
    amount_paid: Decimal
    customer_total_due: Decimal
    status: str
    pdf_generated_count: int
    created_at: str
    payments: list[InvoicePaymentSummary] = []
    payment_collections: list[InvoicePaymentSummary] = []


class InvoiceDashboardResponse(BaseModel):
    total_invoices: int
    total_billed: Decimal
    total_paid: Decimal
    total_due: Decimal
    invoices: list[InvoiceDocumentSummary]


class InvoiceFromSaleRequest(BaseModel):
    invoice_type: str = "tax_invoice"
    tax_rate: float = 18.0
    payment_method: str = "Cash"
    notes: str | None = None


class InvoiceFromSaleResponse(BaseModel):
    invoice_id: int
    invoice_number: str
    pdf_url: str


class InvoiceTelegramDeliveryRequest(BaseModel):
    destination: str = "customer"


class InvoiceEmailDeliveryRequest(BaseModel):
    email: EmailStr | None = None


class InvoiceDeleteRequest(BaseModel):
    confirmation: str
    action: str | None = "reverse"  # "reverse", "archive", or "cancel"


class InvoiceHardDeleteRequest(BaseModel):
    reason: str
    confirm_invoice_number: str
    confirm_test_invoice: bool
    reverse_payments: bool = True


class InvoiceDeliveryResponse(BaseModel):
    status: str
    channel: str
    destination: str


class InvoiceDeliveryHistoryItem(BaseModel):
    id: int
    channel: str
    destination_masked: str | None = None
    status: str
    error_message: str | None = None
    created_at: str


def build_invoice_details(payload: DailySaleCreate) -> str:
    details = []
    for item in payload.items:
        parts = [f"{item.product_size_ml}ml", item.variety]
        quantities = []
        if item.boxes_sold:
            quantities.append(f"{item.boxes_sold} Boxes")
        if item.loose_packets_sold:
            quantities.append(f"{item.loose_packets_sold} Loose Packets")
        details.append(f"{' '.join(parts)} - {', '.join(quantities)}")
    return "; ".join(details)


def pending_payment_dues(db: Session, factory_id: int) -> list[PendingDueResponse]:
    rows = (
        db.query(Order, Customer)
        .join(Customer, Order.customer_id == Customer.id)
        .filter(factory_id_filter(Order.factory_id, factory_id))
        .filter(factory_id_filter(Customer.factory_id, factory_id))
        .filter(Order.payment_status.in_(["Unpaid", "Half-Paid"]))
        .filter(Order.pending_amount > 0)
        .order_by(Order.order_date.asc(), Order.id.asc())
        .all()
    )
    return [
        PendingDueResponse(
            customer_name=customer.name,
            customer_phone=customer_display_phone(customer),
            invoice_id=order.id,
            date=order.order_date.isoformat() if order.order_date else "",
            total_amount=to_money(order.total_amount),
            pending_amount=to_money(order.pending_amount),
            payment_status=order.payment_status or "Unpaid",
        )
        for order, customer in rows
    ]


def customer_display_phone(customer: Customer) -> str:
    return customer.phone_number or customer.phone or customer.contact_number or ""


def format_bill_summary(order: Order, customer: Customer) -> str:
    lines = [
        "Bill / Invoice Summary",
        f"Order ID: {order.id}",
        f"Date: {order.order_date.strftime('%Y-%m-%d %H:%M') if order.order_date else ''}",
        f"Customer: {customer.name}",
        f"Phone: {customer_display_phone(customer)}",
        f"Payment Method: {order.payment_method}",
        f"Status: {order.status}",
        "",
        "Items:",
    ]
    for index, item in enumerate(order.items, start=1):
        product = item.product
        profile = product.packaging_profile if product is not None else None
        product_name = profile.profile_name if profile is not None else item.packaging_size_name or f"Product #{item.product_id}"
        cup_size_value = profile.cup_size_ml if profile is not None else item.product_size_ml
        cup_size = f"{cup_size_value}ml " if cup_size_value is not None else ""
        line_total = to_money(item.final_rate) * Decimal(item.quantity)
        lines.append(
            f"{index}. {cup_size}{product_name} - Qty: {item.quantity}, Rate: Rs {to_money(item.final_rate)}, Total: Rs {to_money(line_total)}"
        )
    lines.extend(["", f"Grand Total: Rs {to_money(order.total_amount)}"])
    return "\n".join(lines)


async def post_notification(url: str, payload: dict[str, str]) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json=payload)


async def send_telegram_message(chat_id: str, text: str) -> str:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if token:
        await post_notification(f"https://api.telegram.org/bot{token}/sendMessage", {"chat_id": chat_id, "text": text})
        return "telegram"

    mock_url = (os.getenv("MOCK_TELEGRAM_API_URL") or os.getenv("TELEGRAM_API_URL") or "").strip()
    if mock_url:
        await post_notification(mock_url, {"chat_id": chat_id, "text": text})
    return "telegram-mock"


async def send_whatsapp_message(phone_number: str, text: str) -> str:
    webhook_url = (os.getenv("WHATSAPP_API_URL") or os.getenv("N8N_WHATSAPP_WEBHOOK") or "").strip()
    if webhook_url:
        await post_notification(webhook_url, {"phone_number": phone_number, "message": text})
    return "whatsapp-mock" if not webhook_url else "whatsapp"


async def send_bill_to_destination(telegram_id: str | None, phone_number: str, text: str) -> str:
    if telegram_id:
        try:
            return await send_telegram_message(telegram_id, text)
        except httpx.RequestError:
            if not phone_number:
                return "telegram-failed"
    if phone_number:
        try:
            return await send_whatsapp_message(phone_number, text)
        except httpx.RequestError:
            return "whatsapp-failed"
    return "not-configured"


async def send_order_whatsapp_bill(customer_phone: str, message: str) -> None:
    webhook_url = (os.getenv("WHATSAPP_API_URL") or os.getenv("N8N_WHATSAPP_WEBHOOK") or "").strip()
    if not webhook_url:
        return
    await post_notification(webhook_url, {"phone_number": customer_phone, "message": message})


def build_confirmed_bill_message(customer_name: str, factory_name: str, amount: Decimal) -> str:
    return f"Hello {customer_name}, your bill for {factory_name} is confirmed. Total Amount: ₹{to_money(amount)}. Thank you!"


def factory_display_name(current_user: User) -> str:
    if current_user.factory is None:
        return "Factory"
    return current_user.factory.factory_name or current_user.factory.name or "Factory"


def is_email_address(value: str | None) -> bool:
    if not value:
        return False
    candidate = value.strip()
    return "@" in candidate and "." in candidate.rsplit("@", 1)[-1]


def resolve_user_email(user: User | None) -> str | None:
    if user is None:
        return None
    explicit_email = getattr(user, "email", None)
    if is_email_address(explicit_email):
        return explicit_email.strip()
    if is_email_address(user.username):
        return user.username.strip()
    return None


def create_invoice_document(
    *,
    db: Session,
    factory_id: str,
    current_user: User,
    customer: Customer | None,
    invoice_payload: dict,
    order_id: int | None = None,
) -> InvoiceDocument:
    invoice = invoice_payload.get("invoice", {})
    invoice_number = str(invoice.get("invoice_id") or invoice_payload.get("invoice_number") or datetime.now(timezone.utc).timestamp())
    document = InvoiceDocument(
        factory_id=factory_id,
        customer_id=customer.id if customer is not None else invoice.get("customer_id"),
        order_id=order_id,
        invoice_number=invoice_number,
        invoice_date=invoice.get("invoice_date") or datetime.now(timezone.utc).date(),
        customer_name=invoice.get("customer_name") or (customer.name if customer is not None else ""),
        customer_phone=invoice.get("customer_phone") or (customer_display_phone(customer) if customer is not None else ""),
        payment_method=invoice.get("payment_method") or "Cash",
        bill_total=to_money(invoice.get("bill_total")),
        amount_paid=to_money(invoice.get("amount_paid")),
        customer_total_due=to_money(invoice.get("customer_total_due")),
        status=invoice.get("status") or "created",
        buyer_gstin=invoice_payload.get("buyer_gstin"),
        hsn_code=invoice_payload.get("hsn_code"),
        transport_mode=invoice_payload.get("transport_mode"),
        vehicle_number=invoice_payload.get("vehicle_number"),
        state_code=invoice_payload.get("state_code"),
        place_of_supply=invoice_payload.get("place_of_supply"),
        tax_rate=invoice_payload.get("tax_rate"),
        total_taxable_value=invoice_payload.get("total_taxable_value") or 0.0,
        total_cgst=invoice_payload.get("total_cgst") or 0.0,
        total_sgst=invoice_payload.get("total_sgst") or 0.0,
        total_igst=invoice_payload.get("total_igst") or 0.0,
        payload_json=json_safe(invoice_payload),
        created_by_user_id=current_user.id,
    )
    db.add(document)
    db.flush()
    if document.customer_id is not None:
        create_outstanding_bill(
            db,
            factory_id=factory_id,
            customer_id=document.customer_id,
            order_id=order_id,
            invoice_document_id=document.id,
            source_type="invoice",
            tracking_number=f"INV-{document.invoice_number}",
            bill_date=document.invoice_date,
            bill_amount=document.bill_total,
            amount_paid=document.amount_paid,
        )
    return document


def should_alert_owner_for_sale(role: str | None) -> bool:
    return (role or "").strip().lower() in {"worker", "operator", "supervisor"}


def build_sales_order_pdf(
    *,
    order_id: int,
    factory_id: int,
    entered_by: str,
    customer_name: str,
    customer_phone: str,
    order_date: str,
    items: list[dict[str, object]],
    total_amount: Decimal,
    amount_paid: Decimal,
    balance_amount: Decimal,
) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("New Sales Entry Alert", styles["Title"]),
        Spacer(1, 12),
        Paragraph(f"<b>Order ID:</b> {order_id}", styles["Normal"]),
        Paragraph(f"<b>Factory ID:</b> {factory_id}", styles["Normal"]),
        Paragraph(f"<b>Entered By:</b> {entered_by}", styles["Normal"]),
        Paragraph(f"<b>Date:</b> {order_date}", styles["Normal"]),
        Spacer(1, 12),
        Paragraph(f"<b>Customer:</b> {customer_name}", styles["Normal"]),
        Paragraph(f"<b>Customer Phone:</b> {customer_phone or 'N/A'}", styles["Normal"]),
        Spacer(1, 16),
    ]

    table_rows = [["#", "Product", "Boxes", "Rate/Packet", "Rate/Box", "Line Total"]]
    for index, item in enumerate(items, start=1):
        product = f"{item.get('product_size_ml') or ''}ml {item.get('variety') or ''} {item.get('packaging_size_name') or ''}".strip()
        boxes = item.get("boxes_sold") or 0
        rate_box = to_money(item.get("rate_per_box"))
        rate_packet = to_money(item.get("rate_per_packet"))
        line_total = to_money(item.get("line_total"))
        table_rows.append([str(index), product, str(boxes), f"Rs {rate_packet}", f"Rs {rate_box}", f"Rs {line_total}"])

    table = Table(table_rows, colWidths=[24, 190, 52, 78, 78, 82])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d4d4d8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ]
        )
    )
    story.extend(
        [
            table,
            Spacer(1, 16),
            Paragraph(f"<b>Bill Total:</b> Rs {to_money(total_amount)}", styles["Normal"]),
            Paragraph(f"<b>Amount Paid:</b> Rs {to_money(amount_paid)}", styles["Normal"]),
            Paragraph(f"<b>Balance:</b> Rs {to_money(balance_amount)}", styles["Normal"]),
        ]
    )
    document.build(story)
    return buffer.getvalue()


def build_mail_config() -> ConnectionConfig | None:
    smtp_user = (os.getenv("SMTP_USER") or os.getenv("MAIL_USERNAME") or "").strip()
    smtp_password = (os.getenv("SMTP_PASSWORD") or os.getenv("MAIL_PASSWORD") or "").strip()
    smtp_from = (os.getenv("SMTP_FROM") or os.getenv("MAIL_FROM") or smtp_user).strip()
    smtp_server = (os.getenv("SMTP_HOST") or os.getenv("MAIL_SERVER") or "").strip()
    smtp_port = int(os.getenv("SMTP_PORT") or os.getenv("MAIL_PORT") or "587")
    if not smtp_user or not smtp_password or not smtp_from or not smtp_server:
        return None
    return ConnectionConfig(
        MAIL_USERNAME=smtp_user,
        MAIL_PASSWORD=smtp_password,
        MAIL_FROM=smtp_from,
        MAIL_PORT=smtp_port,
        MAIL_SERVER=smtp_server,
        MAIL_STARTTLS=(os.getenv("SMTP_STARTTLS") or "true").lower() == "true",
        MAIL_SSL_TLS=(os.getenv("SMTP_SSL_TLS") or "false").lower() == "true",
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True,
    )


async def send_owner_sale_alert_email(
    *,
    owner_email: str,
    subject: str,
    body: str,
    pdf_bytes: bytes,
    filename: str,
) -> None:
    mail_config = build_mail_config()
    if mail_config is None:
        logger.info("Owner sale alert email skipped because SMTP configuration is incomplete")
        return

    attachment = {
    "file": BytesIO(pdf_bytes),
    "filename": filename,
    "content_type": "application/pdf"
    }
    message = MessageSchema(
        subject=subject,
        recipients=[owner_email],
        body=body,
        subtype=MessageType.plain,
        attachments=[attachment],
    )
    await FastMail(mail_config).send_message(message)


@router.post("/invoice", response_model=DailySaleResponse, status_code=status.HTTP_201_CREATED)
@router.post("/add", response_model=DailySaleResponse, status_code=status.HTTP_201_CREATED)
def add_sale_invoice(
    payload: DailySaleCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = factory_id_text(current_user.factory_id)
    logger.info(
        "sales_invoice_request factory_id=%s customer_id=%s product_ids=%s item_count=%s",
        factory_id, payload.customer_id, [item.product_id for item in payload.items], len(payload.items),
    )
    validate_gst_invoice(
        payload.legal_invoice_type,
        payload.buyer_gstin,
        [float(getattr(item, "tax_rate", 0) or 0) for item in payload.items],
    )

    try:
        factory = db.query(Factory).filter(Factory.id == current_user.factory_id).with_for_update().first()
        if factory is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Factory not found")
        invoice_num = clean_optional_text(payload.legal_invoice_number) or allocate_invoice_number(db, factory, payload.legal_invoice_type)

        customer = (
            db.query(Customer)
            .filter(factory_id_filter(Customer.factory_id, factory_id))
            .filter(Customer.id == payload.customer_id)
            .with_for_update()
            .first()
        )
        if customer is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

        previous_remaining_balance = active_customer_outstanding(db, current_user.factory_id, customer.id)
        advance_available = to_money(customer.advance_balance)
        normalized_customer_phone = customer_phone(customer)
        sale_ids: list[int] = []
        current_bill_amount = Decimal("0.00")
        total_taxable_value = Decimal("0.00")
        total_cgst = Decimal("0.00")
        total_sgst = Decimal("0.00")
        total_igst = Decimal("0.00")
        max_tax_rate = 0.0
        line_items: list[dict[str, object]] = []
        stock_sync_items: list[object] = []
        is_intra = is_intra_state_supply(factory, payload.buyer_gstin, payload.place_of_supply)
        factory_has_finished_goods = db.query(FinalProductStock.id).filter(
            factory_id_filter(FinalProductStock.factory_id, factory_id)
        ).first() is not None

        for item in payload.items:
            require_sold_quantity(item.boxes_sold, item.loose_packets_sold)
            is_manual_item_mode = (
                payload.legal_invoice_type in ("BILL_OF_SUPPLY_SIMPLE", "bill_of_supply_simple")
                or not factory_has_finished_goods
            )
            if item.product_id is None and not is_manual_item_mode:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Each invoice item must be selected from Finished Goods stock",
                )
            stock = find_final_stock_for_sale(db, factory_id, item, lock=True) if item.product_id else None
            logger.info(
                "sales_invoice_stock_lookup factory_id=%s customer_id=%s product_id=%s found=%s",
                factory_id, customer.id, item.product_id, stock is not None,
            )
            if stock is None and not is_manual_item_mode:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Finished Goods item {item.product_id} was not found")
            if stock is None:
                stock_sync_items.append(None)
            else:
                if (
                    stock.product_size_ml != item.product_size_ml
                    or stock.variety.strip().lower() != item.variety.strip().lower()
                    or stock.packaging_size_name.strip().lower() != item.packaging_size_name.strip().lower()
                ):
                    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected product details do not match Finished Goods stock")
            if stock is not None:
                from routers.inventory import calculate_live_sku_stock
                live_boxes, live_loose = calculate_live_sku_stock(
                    db=db,
                    factory_id=str(factory_id),
                    product_size_ml=stock.product_size_ml,
                    variety=stock.variety,
                    packaging_size_name=stock.packaging_size_name,
                    onboarding_boxes=stock.total_boxes or 0,
                    onboarding_loose=stock.loose_packets or 0,
                    packets_per_box_limit=stock.packets_per_box_limit or 1,
                )
                available_packets = live_boxes * (stock.packets_per_box_limit or 1) + live_loose
                sold_packets = item.boxes_sold * (stock.packets_per_box_limit or 1) + item.loose_packets_sold
                logger.info(
                    "sales_invoice_stock_before product_id=%s live_boxes=%s live_loose=%s requested_boxes=%s requested_loose=%s",
                    stock.id, live_boxes, live_loose, item.boxes_sold, item.loose_packets_sold,
                )
                if available_packets < sold_packets:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Insufficient stock for {stock.product_size_ml}ml {stock.variety} - {stock.packaging_size_name}. Available: {live_boxes} boxes and {live_loose} loose packets.",
                    )
                stock_sync_items.append(item)

            # Preserve onboarding totals in stock.total_boxes. Dynamic sync helper recalculates current_quantity.

            item_rate_per_box = effective_rate_per_box(item)
            item_taxable = to_money(Decimal(item.boxes_sold) * item_rate_per_box)
            total_taxable_value += item_taxable

            # Determine tax rates
            item_tax_rate = getattr(item, "tax_rate", 0.0) or 0.0
            max_tax_rate = max(max_tax_rate, float(item_tax_rate or 0.0))
            if payload.legal_invoice_type == "tax_invoice" and item_tax_rate > 0:
                if is_intra:
                    cgst_rate = item_tax_rate / 2.0
                    sgst_rate = item_tax_rate / 2.0
                    igst_rate = 0.0
                else:
                    cgst_rate = 0.0
                    sgst_rate = 0.0
                    igst_rate = item_tax_rate
                
                cgst_amt = to_money(item_taxable * Decimal(str(cgst_rate / 100.0)))
                sgst_amt = to_money(item_taxable * Decimal(str(sgst_rate / 100.0)))
                igst_amt = to_money(item_taxable * Decimal(str(igst_rate / 100.0)))
            else:
                cgst_rate = sgst_rate = igst_rate = 0.0
                cgst_amt = sgst_amt = igst_amt = Decimal("0.00")

            total_cgst += cgst_amt
            total_sgst += sgst_amt
            total_igst += igst_amt

            line_total = item_taxable + cgst_amt + sgst_amt + igst_amt

            sale = DailySale(
                factory_id=factory_id,
                date=payload.date,
                customer_id=customer.id,
                customer_phone=normalized_customer_phone,
                product_size_ml=item.product_size_ml,
                variety=item.variety.strip(),
                packaging_size_name=item.packaging_size_name.strip(),
                boxes_sold=item.boxes_sold,
                loose_packets_sold=item.loose_packets_sold,
                rate_per_box=to_money(item.rate_per_box),
                rate_per_packet=to_money(item.rate_per_packet),
                total_amount=line_total,
                total_bill=line_total,
                amount_paid=Decimal("0.00"),
                initial_payment=Decimal("0.00"),
            )
            db.add(sale)
            db.flush()
            sale_ids.append(sale.id)

            line_items.append(
                {
                    "product_size_ml": item.product_size_ml,
                    "variety": item.variety.strip(),
                    "packaging_size_name": item.packaging_size_name.strip(),
                    "boxes_sold": item.boxes_sold,
                    "loose_packets_sold": item.loose_packets_sold,
                    "rate_per_box": item_rate_per_box,
                    "rate_per_packet": to_money(item.rate_per_packet),
                    "line_total": item_taxable,
                    "hsn_code": getattr(item, "hsn_code", None),
                    "description": getattr(item, "description", None),
                    "tax_rate": item_tax_rate,
                    "cgst_rate": cgst_rate,
                    "sgst_rate": sgst_rate,
                    "igst_rate": igst_rate,
                    "cgst_amount": float(cgst_amt),
                    "sgst_amount": float(sgst_amt),
                    "igst_amount": float(igst_amt),
                }
            )

        if payload.legal_invoice_type == "tax_invoice":
            current_bill_amount = to_money(total_taxable_value + total_cgst + total_sgst + total_igst)
        else:
            current_bill_amount = to_money(total_taxable_value)

        customer_due_after_payment = to_money(previous_remaining_balance + current_bill_amount)

        # Recalculate dynamic live stock balance and sync caches for all sold SKUs
        from routers.inventory import recalculate_and_sync_sku_stock
        for item in stock_sync_items:
            if item is None:
                continue
            recalculate_and_sync_sku_stock(
                db=db,
                factory_id=str(factory_id),
                product_size_ml=item.product_size_ml,
                variety=item.variety,
                packaging_size_name=item.packaging_size_name,
            )

        activity = ActivityLog(
            factory_id=int(factory_id),
            event_type="payment",
            description=f"Generated sales invoice #{invoice_num} for customer {customer.name}: Bill total ₹{current_bill_amount:,.2f}, Paid ₹{payload.amount_paid:,.2f}"
        )
        db.add(activity)

        db.flush()

        google_spreadsheet_id = resolve_factory_google_sheet_id(db, factory_id)
        invoice_payload = {
            "event": "invoice.created",
            "factory_id": factory_id,
            "google_spreadsheet_id": google_spreadsheet_id,
            "target_sheet_name": f"Factory_{factory_id}_Sales",
            "sync_type": "sales",
            "action": "insert",
            "document_policy": {
                "legal_invoice_type": payload.legal_invoice_type,
                "legal_invoice_number": invoice_num,
                "rough_bill_enabled": payload.rough_bill_enabled,
                "rough_bill_number": payload.rough_bill_number or f"RB-{invoice_num}",
                "rough_bill_label": "Customer Understanding Bill",
                "rough_bill_disclaimer": "Internal customer understanding and rate settlement document. Not a government tax invoice.",
            },
            "invoice": {
                "invoice_id": invoice_num,
                "invoice_type": payload.legal_invoice_type,
                "sale_ids": sale_ids,
                "invoice_date": payload.date,
                "customer_id": customer.id,
                "customer_name": customer.name,
                "customer_phone": normalized_customer_phone,
                "payment_method": "Cash",
                "bill_total": current_bill_amount,
                "amount_paid": Decimal("0.00"),
                "previous_due": previous_remaining_balance,
                "advance_available": advance_available,
                "advance_adjusted": Decimal("0.00"),
                "total_before_advance": to_money(previous_remaining_balance + current_bill_amount),
                "remaining_payable": customer_due_after_payment,
                "customer_total_due": customer_due_after_payment,
                "status": "created",
            },
            "items": line_items,
            "buyer_gstin": clean_optional_text(payload.buyer_gstin),
            "transport_mode": clean_optional_text(payload.transport_mode),
            "vehicle_number": clean_optional_text(payload.vehicle_number),
            "state_code": gst_state_code(payload.buyer_gstin) or gst_state_code(payload.place_of_supply),
            "place_of_supply": clean_optional_text(payload.place_of_supply),
            "tax_rate": max_tax_rate if payload.legal_invoice_type == "tax_invoice" else None,
            "total_taxable_value": float(total_taxable_value),
            "total_cgst": float(total_cgst),
            "total_sgst": float(total_sgst),
            "total_igst": float(total_igst),
            "tax_breakup": {
                "is_intra_state": is_intra,
                "mode": "CGST_SGST" if is_intra else "IGST",
            },
        }

        invoice_document = create_invoice_document(
            db=db,
            factory_id=factory_id,
            current_user=current_user,
            customer=customer,
            invoice_payload=invoice_payload,
        )
        invoice_bill = db.query(OutstandingBill).filter(
            OutstandingBill.factory_id == current_user.factory_id,
            OutstandingBill.invoice_document_id == invoice_document.id,
        ).one()
        logger.info(
            "sales_invoice_ledger_created factory_id=%s customer_id=%s invoice_id=%s bill_id=%s source_type=%s invoice_total=%s",
            factory_id, customer.id, invoice_document.id, invoice_bill.id, invoice_bill.source_type, current_bill_amount,
        )

        advance_adjusted = min(advance_available, customer_due_after_payment)
        if advance_adjusted > 0:
            apply_payment_to_outstanding_bills(
                db,
                factory_id=current_user.factory_id,
                customer_id=customer.id,
                amount=advance_adjusted,
                payment_mode="UPI",
                collection_date=payload.date,
                created_by_user_id=current_user.id,
            )
            customer.advance_balance = to_money(advance_available - advance_adjusted)

        cash_payment = to_money(payload.amount_paid)
        if cash_payment > 0:
            payable_after_advance = active_customer_outstanding(db, current_user.factory_id, customer.id)
            if cash_payment > payable_after_advance:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment amount exceeds total payable amount")
            payment = Payment(
                factory_id=factory_id,
                customer_phone=normalized_customer_phone,
                sale_id=sale_ids[0] if sale_ids else None,
                amount_paid=cash_payment,
                payment_mode="Cash",
                date=payload.date,
            )
            db.add(payment)
            db.flush()
            apply_payment_to_outstanding_bills(
                db,
                factory_id=current_user.factory_id,
                customer_id=customer.id,
                amount=cash_payment,
                payment_mode="Cash",
                collection_date=payload.date,
                payment_id=payment.id,
                created_by_user_id=current_user.id,
            )

        db.flush()
        customer_due_after_payment = sync_customer_balance_from_bills(db, current_user.factory_id, customer)
        customer.previous_due = previous_remaining_balance
        invoice_document.amount_paid = to_money(invoice_bill.amount_paid)
        invoice_document.customer_total_due = to_money(invoice_bill.balance_amount)
        invoice_payload["invoice"]["advance_adjusted"] = advance_adjusted
        invoice_payload["invoice"]["remaining_payable"] = customer_due_after_payment
        invoice_payload["invoice"]["customer_total_due"] = invoice_document.customer_total_due
        invoice_payload["invoice"]["amount_paid"] = invoice_document.amount_paid
        invoice_document.payload_json = json_safe(invoice_payload)
        if sale_ids:
            first_sale = db.query(DailySale).filter(DailySale.id == sale_ids[0]).first()
            first_sale.amount_paid = cash_payment
            first_sale.initial_payment = cash_payment

        sync_next_invoice_setting(db, factory, invoice_num, payload.legal_invoice_type)
        db.commit()

        background_tasks.add_task(
            log_activity,
            db,
            int(current_user.factory_id),
            current_user.id,
            current_user.full_name or current_user.username,
            current_user.role,
            "SALE_RECORDED",
            f"Sale of \u20B9{current_bill_amount:,.2f} to {customer.name}",
            "sale",
            invoice_document.id,
            {"invoice_number": invoice_num, "customer_id": customer.id, "sale_ids": sale_ids},
        )

        background_tasks.add_task(
            sync_data_to_n8n_bg,
            factory_id=str(factory_id),
            sync_type="sales",
            action="insert",
            data=payload,
        )

        background_tasks.add_task(
            send_n8n_whatsapp_event,
            {
                "event": "NEW_SALE",
                "customer_name": customer.name,
                "phone": normalized_customer_phone,
                "bill_amount": str(current_bill_amount),
                "total_balance": str(customer_due_after_payment),
                "items": build_invoice_details(payload),
            },
        )

        # P4.5 D1: action alert to Owner (best-effort, never raises)
        notify_sale_created(
            db,
            factory=factory,
            actor=current_user,
            customer_name=customer.name,
            amount_paise=int(to_money(payload.amount_paid) * 100),
        )
        # P4.5 D1: high-risk customer alert (best-effort, never raises)
        notify_outstanding_threshold_crossed(
            db,
            factory=factory,
            actor=current_user,
            customer_name=customer.name,
            new_total_paise=int(to_money(customer_due_after_payment) * 100),
        )

        return DailySaleResponse(
            sale_ids=sale_ids,
            customer_id=customer.id,
            bill_total=current_bill_amount,
            amount_paid=to_money(payload.amount_paid),
            customer_total_due=customer_due_after_payment,
            invoice_document_id=invoice_document.id,
        )
    except HTTPException:
        db.rollback()
        raise
    except (IntegrityError, OperationalError, SQLAlchemyError) as exc:
        db.rollback()
        logger.exception("Sale invoice database operation failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice could not be saved because its customer, stock, or invoice number is no longer valid. Refresh and try again.",
        ) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Sale invoice creation failed")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice request could not be processed") from exc


@router.post("/order", response_model=SalesOrderCreateResponse, status_code=status.HTTP_201_CREATED)
def create_sales_order(
    payload: DailySaleCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = factory_id_text(current_user.factory_id)
    customer = (
        db.query(Customer)
        .filter(factory_id_filter(Customer.factory_id, factory_id))
        .filter(Customer.id == payload.customer_id)
        .first()
    )
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    total_amount = Decimal("0.00")
    email_items: list[dict[str, object]] = []
    order = Order(
        factory_id=factory_id,
        customer_id=customer.id,
        status="pending_owner",
        payment_method="Normal_Credit",
        terms_accepted=True,
        total_amount=Decimal("0.00"),
        amount_paid=to_money(payload.amount_paid),
        balance_amount=Decimal("0.00"),
        payment_status="Unpaid",
        pending_amount=Decimal("0.00"),
    )
    db.add(order)
    db.flush()

    for item in payload.items:
        require_sold_quantity(item.boxes_sold, item.loose_packets_sold)
        stock = find_final_stock_for_sale(db, factory_id, item)
        if stock is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Stock variation not found for {item.product_size_ml}ml {item.variety} {item.packaging_size_name}",
            )
        ensure_variation_stock_available(stock, item.boxes_sold, item.loose_packets_sold)
        item_rate_per_box = effective_rate_per_box(item)
        line_total = to_money(Decimal(item.boxes_sold) * item_rate_per_box)
        email_items.append(
            {
                "product_size_ml": item.product_size_ml,
                "variety": item.variety.strip(),
                "packaging_size_name": item.packaging_size_name.strip(),
                "boxes_sold": item.boxes_sold,
                "loose_packets_sold": item.loose_packets_sold,
                "rate_per_box": item_rate_per_box,
                "rate_per_packet": to_money(item.rate_per_packet),
                "line_total": line_total,
            }
        )
        total_amount = to_money(total_amount + line_total)
        quantity = max(item.boxes_sold + item.loose_packets_sold, 1)
        db.add(
            OrderItem(
                factory_id=factory_id,
                order_id=order.id,
                product_id=None,
                quantity=quantity,
                base_rate=item_rate_per_box,
                final_rate=line_total,
                product_size_ml=stock.product_size_ml,
                variety=stock.variety.strip(),
                packaging_size_name=stock.packaging_size_name.strip(),
                boxes_sold=item.boxes_sold,
                loose_packets_sold=item.loose_packets_sold,
                rate_per_box=item_rate_per_box,
                rate_per_packet=to_money(item.rate_per_packet),
            )
        )

    order.total_amount = total_amount
    order.balance_amount = max(to_money(total_amount - to_money(payload.amount_paid)), Decimal("0.00"))
    order.pending_amount = order.balance_amount
    order.payment_status = payment_status_for(total_amount, to_money(payload.amount_paid))
    db.commit()
    db.refresh(order)
    background_tasks.add_task(
        sync_data_to_n8n_bg,
        factory_id=str(factory_id),
        sync_type="sales",
        action="insert",
        data=payload,
    )

    if should_alert_owner_for_sale(current_user.role):
        owner = (
            db.query(User)
            .filter(factory_id_filter(User.factory_id, factory_id))
            .filter(User.role == "Owner")
            .order_by(User.id.asc())
            .first()
        )
        owner_email = resolve_user_email(owner)
        if owner_email:
            entered_by = current_user.full_name or current_user.username
            order_date = order.order_date.strftime("%Y-%m-%d %H:%M") if order.order_date else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            pdf_bytes = build_sales_order_pdf(
                order_id=order.id,
                factory_id=factory_id,
                entered_by=entered_by,
                customer_name=customer.name,
                customer_phone=customer_display_phone(customer),
                order_date=order_date,
                items=email_items,
                total_amount=total_amount,
                amount_paid=to_money(payload.amount_paid),
                balance_amount=to_money(order.balance_amount),
            )
            subject = f"⚠️ ALERT: New Sales Entry - {customer.name}"
            body = (
                f"A new sale entry was created by {entered_by} for {customer.name}.\n\n"
                f"Order ID: {order.id}\n"
                f"Bill Total: Rs {to_money(total_amount)}\n"
                f"Amount Paid: Rs {to_money(payload.amount_paid)}\n"
                f"Balance: Rs {to_money(order.balance_amount)}\n\n"
                "The detailed sale entry PDF is attached."
            )
            background_tasks.add_task(
                send_owner_sale_alert_email,
                owner_email=owner_email,
                subject=subject,
                body=body,
                pdf_bytes=pdf_bytes,
                filename=f"sale-entry-{order.id}.pdf",
            )
        else:
            logger.info("Owner sale alert email skipped: no owner email found for factory_id=%s", factory_id)

    return SalesOrderCreateResponse(
        order_id=order.id,
        sale_ids=[order.id],
        customer_id=customer.id,
        bill_total=total_amount,
        amount_paid=to_money(payload.amount_paid),
        customer_total_due=to_money(customer.total_due or customer.balance_amount or 0),
        status=order.status,
    )


@router.post("/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_sales_customer(
    payload: CustomerCreate,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    opening_due = max(
        to_money(payload.opening_balance),
        to_money(payload.legacy_dues),
        to_money(payload.previous_due),
        to_money(payload.total_due),
        to_money(payload.opening_outstanding),
    )
    advance_val = to_money(payload.advance_balance)
    
    if opening_due < 0:
        raise HTTPException(status_code=400, detail="Opening outstanding cannot be negative.")
    if advance_val < 0:
        raise HTTPException(status_code=400, detail="Advance balance cannot be negative.")
    if opening_due > 0 and advance_val > 0:
        raise HTTPException(status_code=400, detail="A customer cannot have both opening outstanding and advance balance positive.")

    phone_number = payload.phone_number.strip()
    try:
        with db.begin_nested() if db.in_transaction() else db.begin():
            factory = db.query(Factory).filter(Factory.id == current_user.factory_id).first()
            if not factory:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Factory not found")
            existing = (
                db.query(Customer)
                .filter(factory_id_filter(Customer.factory_id, current_user.factory_id))
                .filter(Customer.phone_number == phone_number)
                .first()
            )
            if existing is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Customer phone number already exists")

            customer = Customer(
                factory_id=factory_id_text(current_user.factory_id),
                name=payload.name.strip(),
                email=str(payload.email).lower() if payload.email else None,
                phone_number=phone_number,
                place=payload.place.strip(),
                gst_number=payload.gst_number.strip() if payload.gst_number else None,
                firm_name=payload.company_name.strip() if payload.company_name else None,
                address=payload.address or payload.place.strip(),
                phone=phone_number,
                contact_number=phone_number,
                previous_due=opening_due,
                opening_outstanding_note=clean_optional_text(payload.opening_outstanding_note),
                opening_outstanding_date=payload.opening_outstanding_date,
                advance_balance=advance_val,
                advance_balance_note=clean_optional_text(payload.advance_balance_note),
                advance_balance_date=payload.advance_balance_date,
                total_due=opening_due,
                pending_balance=opening_due,
                balance_amount=opening_due,
                pending_dues=float(opening_due),
            )
            db.add(customer)
            db.flush()
            if opening_due > 0:
                create_outstanding_bill(
                    db,
                    factory_id=current_user.factory_id,
                    customer_id=customer.id,
                    source_type="opening_outstanding",
                    tracking_number=f"OPEN-{customer.id}",
                    bill_date=payload.opening_outstanding_date or datetime.now(timezone.utc).date(),
                    bill_amount=opening_due,
                    amount_paid=Decimal("0.00"),
                )
                sync_customer_balance_from_bills(db, current_user.factory_id, customer)
        db.commit()
        db.refresh(customer)
        # P4.5 D1: customer created alert (best-effort, never raises)
        notify_customer_created(
            db,
            factory=factory,
            actor=current_user,
            customer_name=customer.name,
            place=(payload.place or "").strip() or "—",
        )
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Customer creation failed and rolled back")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Customer creation failed: {exc}") from exc
    return customer


class CustomerUpdatePayload(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone_number: str | None = None
    place: str | None = None
    gst_number: str | None = None
    company_name: str | None = None
    address: str | None = None
    previous_due: Decimal | None = None
    opening_outstanding: Decimal | None = None
    opening_outstanding_note: str | None = None
    opening_outstanding_date: date | None = None
    advance_balance: Decimal | None = None
    advance_balance_note: str | None = None
    advance_balance_date: date | None = None

    @field_validator("opening_outstanding_date", "advance_balance_date", mode="before")
    @classmethod
    def empty_balance_date_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


@router.patch("/customers/{customer_id}", response_model=CustomerSearchResponse)
def update_sales_customer(
    customer_id: int,
    payload: CustomerUpdatePayload,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    customer = (
        db.query(Customer)
        .filter(factory_id_filter(Customer.factory_id, current_user.factory_id))
        .filter(Customer.id == customer_id)
        .first()
    )
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    submitted_opening = (
        payload.opening_outstanding
        if payload.opening_outstanding is not None
        else payload.previous_due
    )
    opening_changed = (
        submitted_opening is not None
        and to_money(submitted_opening) != to_money(customer.previous_due)
    )
    advance_changed = (
        payload.advance_balance is not None
        and to_money(payload.advance_balance) != to_money(customer.advance_balance)
    )
    if opening_changed or advance_changed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use the customer ledger-adjustments endpoint to change outstanding balance",
        )

    old_outstanding = customer.previous_due
    old_opening = to_money(customer.previous_due or 0)
    old_total_due = to_money(customer.total_due or 0)
    old_advance = customer.advance_balance

    # Track activity log details
    changes = []

    if payload.name is not None:
        new_name = payload.name.strip()
        existing = (
            db.query(Customer)
            .filter(factory_id_filter(Customer.factory_id, current_user.factory_id))
            .filter(Customer.id != customer_id)
            .filter(sql_func.lower(Customer.name) == new_name.lower())
            .first()
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Customer name already in use by another customer")
        customer.name = new_name
    if payload.email is not None:
        customer.email = str(payload.email).strip().lower() or None
    if payload.phone_number is not None:
        new_phone = payload.phone_number.strip()
        existing = (
            db.query(Customer)
            .filter(factory_id_filter(Customer.factory_id, current_user.factory_id))
            .filter(Customer.id != customer_id)
            .filter(Customer.phone_number == new_phone)
            .first()
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phone number already in use by another customer")
        customer.phone_number = new_phone
        customer.phone = new_phone
        customer.contact_number = new_phone
    if payload.place is not None:
        customer.place = payload.place.strip()
        customer.address = payload.place.strip()
    if payload.address is not None:
        customer.address = payload.address.strip()
    if payload.gst_number is not None:
        new_gst_number = payload.gst_number.strip() or None
        if new_gst_number is not None:
            existing = (
                db.query(Customer)
                .filter(factory_id_filter(Customer.factory_id, current_user.factory_id))
                .filter(Customer.id != customer_id)
                .filter(sql_func.lower(Customer.gst_number) == new_gst_number.lower())
                .first()
            )
            if existing is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="GST number already in use by another customer")
        customer.gst_number = new_gst_number
    if payload.company_name is not None:
        new_company_name = payload.company_name.strip() or None
        if new_company_name is not None:
            existing = (
                db.query(Customer)
                .filter(factory_id_filter(Customer.factory_id, current_user.factory_id))
                .filter(Customer.id != customer_id)
                .filter(sql_func.lower(Customer.firm_name) == new_company_name.lower())
                .first()
            )
            if existing is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Company name already in use by another customer")
        customer.firm_name = new_company_name

    # Handle opening balance update
    new_opening = payload.opening_outstanding if payload.opening_outstanding is not None else payload.previous_due
    new_advance = payload.advance_balance
    delta = Decimal("0.00")

    if new_opening is not None:
        new_opening = to_money(new_opening)
        if new_opening < 0:
            raise HTTPException(status_code=400, detail="Opening outstanding cannot be negative.")
        curr_advance = to_money(new_advance if new_advance is not None else customer.advance_balance)
        if new_opening > 0 and curr_advance > 0:
            raise HTTPException(status_code=400, detail="A customer cannot have both opening outstanding and advance balance positive.")
        
        delta = new_opening - old_opening
        customer.previous_due = new_opening
        changes.append(f"previous due from ₹{old_opening} to ₹{new_opening}")

        # Update/Create the OPENING ledger bill
        open_bill = (
            db.query(OutstandingBill)
            .filter(OutstandingBill.factory_id == current_user.factory_id)
            .filter(OutstandingBill.customer_id == customer.id)
            .filter(OutstandingBill.source_type.in_(("opening_balance", "opening_outstanding")))
            .first()
        )
        if open_bill:
            open_bill.bill_amount = new_opening
            open_bill.balance_amount = max(Decimal("0.00"), to_money(open_bill.balance_amount) + delta)
            if open_bill.balance_amount <= 0:
                open_bill.status = "closed"
            else:
                open_bill.status = "active"
        elif new_opening > 0:
            create_outstanding_bill(
                db,
                factory_id=current_user.factory_id,
                customer_id=customer.id,
                source_type="opening_outstanding",
                tracking_number=f"OPEN-{customer.id}",
                bill_date=payload.opening_outstanding_date or datetime.now(timezone.utc).date(),
                bill_amount=new_opening,
                amount_paid=Decimal("0.00"),
            )

    if payload.opening_outstanding_note is not None:
        customer.opening_outstanding_note = payload.opening_outstanding_note
    if payload.opening_outstanding_date is not None:
        customer.opening_outstanding_date = payload.opening_outstanding_date

    # Handle advance balance update
    if new_advance is not None:
        new_advance = to_money(new_advance)
        if new_advance < 0:
            raise HTTPException(status_code=400, detail="Advance balance cannot be negative.")
        curr_outstanding = to_money(new_opening if new_opening is not None else customer.previous_due)
        if curr_outstanding > 0 and new_advance > 0:
            raise HTTPException(status_code=400, detail="A customer cannot have both opening outstanding and advance balance positive.")
        
        customer.advance_balance = new_advance
        changes.append(f"advance balance from ₹{old_advance} to ₹{new_advance}")

    if payload.advance_balance_note is not None:
        customer.advance_balance_note = payload.advance_balance_note
    if payload.advance_balance_date is not None:
        customer.advance_balance_date = payload.advance_balance_date

    # Force database sync to ensure total_due etc. matches the ledger
    sync_customer_balance_from_bills(db, current_user.factory_id, customer)

    db.commit()
    db.refresh(customer)

    # Log changes in activity_logs
    if changes:
        try:
            # Query unpaid invoice due
            unpaid_invoice_due = to_money(
                db.query(sql_func.coalesce(sql_func.sum(OutstandingBill.balance_amount), 0))
                .filter(OutstandingBill.factory_id == current_user.factory_id)
                .filter(OutstandingBill.customer_id == customer.id)
                .filter(OutstandingBill.source_type == "invoice")
                .filter(OutstandingBill.status.in_(["active", "partial"]))
                .scalar()
            )
            # Query payment total
            from models import PaymentCollection
            payment_total = to_money(
                db.query(sql_func.coalesce(sql_func.sum(PaymentCollection.amount_collected), 0))
                .filter(PaymentCollection.factory_id == current_user.factory_id)
                .filter(PaymentCollection.customer_id == customer.id)
                .scalar()
            )
            new_total_due = to_money(customer.total_due or 0)
            
            audit_metadata = {
                "customer_id": customer.id,
                "old_total_due": float(old_total_due),
                "new_total_due": float(new_total_due),
                "old_opening_balance": float(old_opening),
                "new_opening_balance": float(new_opening if new_opening is not None else old_opening),
                "delta": float(delta),
                "payment_total": float(payment_total),
                "invoice_due_total": float(unpaid_invoice_due),
                "changes": changes
            }
            log_activity(
                db,
                int(current_user.factory_id),
                current_user.id,
                current_user.full_name or current_user.username,
                current_user.role,
                "CUSTOMER_UPDATED",
                f"Updated customer {customer.name} fields: {', '.join(changes)}",
                "customer",
                customer.id,
                audit_metadata
            )
        except Exception:
            logger.warning("Activity logging failed on customer update", exc_info=True)

    return CustomerSearchResponse(
        id=customer.id,
        name=customer.name,
        email=customer.email,
        place=customer.place or customer.address or "",
        phone_number=customer.phone_number or customer.phone or customer.contact_number or "",
        gst_number=customer.gst_number,
        company_name=customer.firm_name,
        previous_due=customer.previous_due,
        opening_outstanding=customer.previous_due,
        current_outstanding=customer.total_due,
        opening_outstanding_note=customer.opening_outstanding_note,
        opening_outstanding_date=customer.opening_outstanding_date,
        advance_balance=customer.advance_balance,
        advance_balance_note=customer.advance_balance_note,
        advance_balance_date=customer.advance_balance_date,
    )


@router.get("/customers/search", response_model=list[CustomerSearchResponse])
def search_customers(
    q: str = Query(default="", max_length=100),
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    query_text = q.strip().lower()
    query = db.query(Customer).filter(factory_id_filter(Customer.factory_id, current_user.factory_id))
    if query_text:
        like_text = f"%{query_text}%"
        query = query.filter(
            or_(
                sql_func.lower(Customer.name).like(like_text),
                sql_func.lower(Customer.phone_number).like(like_text),
                sql_func.lower(Customer.phone).like(like_text),
                sql_func.lower(Customer.contact_number).like(like_text),
            )
        )
    customers = query.order_by(Customer.name.asc()).limit(20).all()
    results = []
    for customer in customers:
        source_rows = (
            db.query(
                OutstandingBill.source_type,
                sql_func.coalesce(sql_func.sum(OutstandingBill.balance_amount), 0),
            )
            .filter(
                OutstandingBill.factory_id == int(current_user.factory_id),
                OutstandingBill.customer_id == customer.id,
                OutstandingBill.deleted_at.is_(None),
                OutstandingBill.status.in_(("active", "partial")),
            )
            .group_by(OutstandingBill.source_type)
            .all()
        )
        source_map = {"opening_outstanding": Decimal("0.00"), "invoice": Decimal("0.00"), "manual_adjustment": Decimal("0.00")}
        for source_type, amount in source_rows:
            source = "opening_outstanding" if source_type in ("opening_balance", "opening_outstanding") else source_type
            if source not in source_map:
                source = "invoice"
            source_map[source] += to_money(amount)
        results.append(CustomerSearchResponse(
            id=customer.id,
            name=customer.name,
            email=customer.email,
            place=customer.place or customer.address or "",
            phone_number=customer.phone_number or customer.phone or customer.contact_number or "",
            gst_number=customer.gst_number,
            company_name=customer.firm_name,
            previous_due=customer.previous_due,
            opening_outstanding=customer.previous_due,
            current_outstanding=customer.total_due,
            opening_outstanding_note=customer.opening_outstanding_note,
            opening_outstanding_date=customer.opening_outstanding_date,
            advance_balance=customer.advance_balance,
            advance_balance_note=customer.advance_balance_note,
            advance_balance_date=customer.advance_balance_date,
            opening_outstanding_remaining=source_map["opening_outstanding"],
            invoice_outstanding_remaining=source_map["invoice"],
            manual_adjustment_remaining=source_map["manual_adjustment"],
        ))
    return results


@router.get("/bill-customers", response_model=list[BillCustomerOption])
def list_bill_customers(
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    customers = (
        db.query(Customer.id, Customer.name, Customer.phone_number, Customer.phone, Customer.contact_number, Customer.place, Customer.address, Customer.telegram_id)
        .filter(factory_id_filter(Customer.factory_id, current_user.factory_id))
        .order_by(Customer.name.asc())
        .limit(100)
        .all()
    )
    return [
        BillCustomerOption(
            id=customer.id,
            name=customer.name,
            phone_number=customer.phone_number or customer.phone or customer.contact_number or "",
            place=customer.place or customer.address or "",
            telegram_id=customer.telegram_id,
        )
        for customer in customers
    ]


@router.get("/customers/{customer_id}/orders", response_model=list[BillOrderOption])
def list_customer_orders(
    customer_id: int,
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    customer_exists = (
        db.query(Customer.id)
        .filter(factory_id_filter(Customer.factory_id, current_user.factory_id))
        .filter(Customer.id == customer_id)
        .first()
    )
    if customer_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    orders = (
        db.query(Order.id, Order.order_date, Order.status, Order.total_amount, Order.payment_method)
        .filter(factory_id_filter(Order.factory_id, current_user.factory_id))
        .filter(Order.customer_id == customer_id)
        .order_by(Order.order_date.desc(), Order.id.desc())
        .limit(25)
        .all()
    )
    return [
        BillOrderOption(
            id=order.id,
            order_date=order.order_date.isoformat() if order.order_date else "",
            status=order.status,
            total_amount=str(to_money(order.total_amount)),
            payment_method=order.payment_method,
        )
        for order in orders
    ]


@router.post("/send-bill-notification", response_model=BillNotificationResponse)
async def send_bill_notification(
    payload: BillNotificationRequest,
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    customer = (
        db.query(Customer)
        .filter(factory_id_filter(Customer.factory_id, current_user.factory_id))
        .filter(Customer.id == payload.customer_id)
        .first()
    )
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    order = (
        db.query(Order)
        .options(
            joinedload(Order.items)
            .joinedload(OrderItem.product)
            .joinedload(FinishedGoodsStock.packaging_profile)
        )
        .filter(factory_id_filter(Order.factory_id, current_user.factory_id))
        .filter(Order.id == payload.order_id)
        .filter(Order.customer_id == customer.id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    bill_summary = format_bill_summary(order, customer)
    owner_telegram_id = (os.getenv("OWNER_TELEGRAM_ID") or os.getenv("ADMIN_TELEGRAM_ID") or "").strip() or None
    owner_phone_number = (
        os.getenv("OWNER_WHATSAPP_NUMBER")
        or os.getenv("ADMIN_WHATSAPP_NUMBER")
        or os.getenv("ADMIN_PHONE_NUMBER")
        or ""
    ).strip()

    owner_channel = await send_bill_to_destination(owner_telegram_id, owner_phone_number, bill_summary)
    customer_channel = await send_bill_to_destination(customer.telegram_id, customer_display_phone(customer), bill_summary)

    return BillNotificationResponse(
        message="Bill successfully sent to Owner and Customer via Telegram/WhatsApp.",
        order_id=order.id,
        customer_id=customer.id,
        owner_channel=owner_channel,
        customer_channel=customer_channel,
        bill_summary=bill_summary,
    )


@router.get("/bill-customers", response_model=list[BillCustomerOption])
def list_bill_customers(
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    customers = (
        db.query(Customer.id, Customer.name, Customer.phone_number, Customer.phone, Customer.contact_number, Customer.place, Customer.address, Customer.telegram_id)
        .filter(factory_id_filter(Customer.factory_id, current_user.factory_id))
        .order_by(Customer.name.asc())
        .limit(100)
        .all()
    )
    return [
        BillCustomerOption(
            id=customer.id,
            name=customer.name,
            phone_number=customer.phone_number or customer.phone or customer.contact_number or "",
            place=customer.place or customer.address or "",
            telegram_id=customer.telegram_id,
        )
        for customer in customers
    ]


@router.get("/customers/{customer_id}/orders", response_model=list[BillOrderOption])
def list_customer_orders(
    customer_id: int,
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    customer_exists = (
        db.query(Customer.id)
        .filter(factory_id_filter(Customer.factory_id, current_user.factory_id))
        .filter(Customer.id == customer_id)
        .first()
    )
    if customer_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    orders = (
        db.query(Order.id, Order.order_date, Order.status, Order.total_amount, Order.payment_method)
        .filter(factory_id_filter(Order.factory_id, current_user.factory_id))
        .filter(Order.customer_id == customer_id)
        .order_by(Order.order_date.desc(), Order.id.desc())
        .limit(25)
        .all()
    )
    return [
        BillOrderOption(
            id=order.id,
            order_date=order.order_date.isoformat() if order.order_date else "",
            status=order.status,
            total_amount=str(to_money(order.total_amount)),
            payment_method=order.payment_method,
        )
        for order in orders
    ]


@router.post("/send-bill-notification", response_model=BillNotificationResponse)
async def send_bill_notification(
    payload: BillNotificationRequest,
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    customer = (
        db.query(Customer)
        .filter(factory_id_filter(Customer.factory_id, current_user.factory_id))
        .filter(Customer.id == payload.customer_id)
        .first()
    )
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    order = (
        db.query(Order)
        .options(
            joinedload(Order.items)
            .joinedload(OrderItem.product)
            .joinedload(FinishedGoodsStock.packaging_profile)
        )
        .filter(factory_id_filter(Order.factory_id, current_user.factory_id))
        .filter(Order.id == payload.order_id)
        .filter(Order.customer_id == customer.id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    bill_summary = format_bill_summary(order, customer)
    owner_telegram_id = (os.getenv("OWNER_TELEGRAM_ID") or os.getenv("ADMIN_TELEGRAM_ID") or "").strip() or None
    owner_phone_number = (
        os.getenv("OWNER_WHATSAPP_NUMBER")
        or os.getenv("ADMIN_WHATSAPP_NUMBER")
        or os.getenv("ADMIN_PHONE_NUMBER")
        or ""
    ).strip()

    owner_channel = await send_bill_to_destination(owner_telegram_id, owner_phone_number, bill_summary)
    customer_channel = await send_bill_to_destination(customer.telegram_id, customer_display_phone(customer), bill_summary)

    return BillNotificationResponse(
        message="Bill successfully sent to Owner and Customer via Telegram/WhatsApp.",
        order_id=order.id,
        customer_id=customer.id,
        owner_channel=owner_channel,
        customer_channel=customer_channel,
        bill_summary=bill_summary,
    )


@router.get("/invoices", response_model=InvoiceDashboardResponse)
def list_invoice_documents(
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = factory_id_text(current_user.factory_id)
    invoices = (
        db.query(InvoiceDocument)
        .filter(factory_id_filter(InvoiceDocument.factory_id, factory_id))
        .filter(InvoiceDocument.status != "archived")
        .order_by(InvoiceDocument.invoice_date.desc(), InvoiceDocument.id.desc())
        .limit(100)
        .all()
    )
    totals = (
        db.query(
            sql_func.count(InvoiceDocument.id),
            sql_func.coalesce(sql_func.sum(InvoiceDocument.bill_total), 0),
            sql_func.coalesce(sql_func.sum(InvoiceDocument.amount_paid), 0),
            sql_func.coalesce(sql_func.sum(InvoiceDocument.customer_total_due), 0),
        )
        .filter(factory_id_filter(InvoiceDocument.factory_id, factory_id))
        .filter(InvoiceDocument.status != "archived")
        .one()
    )
    invoice_summaries = []
    for invoice in invoices:
        bill = db.query(OutstandingBill).filter(OutstandingBill.invoice_document_id == invoice.id).first()
        payment_list = []
        live_paid = to_money(invoice.amount_paid)
        live_due = to_money(invoice.customer_total_due)
        
        if bill:
            live_paid = to_money(bill.amount_paid)
            live_due = to_money(bill.balance_amount)
            collections = db.query(PaymentCollection).filter(PaymentCollection.outstanding_bill_id == bill.id).order_by(PaymentCollection.collection_date.asc()).all()
            for col in collections:
                payment_list.append(
                    InvoicePaymentSummary(
                        payment_date=col.collection_date.isoformat(),
                        amount_paid=to_money(col.amount_collected),
                        payment_mode=col.payment_mode,
                    )
                )

        status = invoice.status
        if status == "created":
            status = "active"
        if bill:
            if bill.status == "cancelled":
                status = "cancelled"
            else:
                if live_due <= 0 and to_money(bill.bill_amount) > 0:
                    status = "paid"
                elif live_paid > 0:
                    status = "active"

        invoice_summaries.append(
            InvoiceDocumentSummary(
                id=invoice.id,
                invoice_number=invoice.invoice_number,
                invoice_date=invoice.invoice_date.isoformat(),
                customer_id=invoice.customer_id,
                customer_name=invoice.customer_name,
                customer_phone=invoice.customer_phone,
                customer_email=invoice.customer.email if invoice.customer else None,
                payment_method=invoice.payment_method,
                bill_total=to_money(invoice.bill_total),
                amount_paid=live_paid,
                customer_total_due=live_due,
                status=status,
                pdf_generated_count=invoice.pdf_generated_count,
                created_at=invoice.created_at.isoformat() if invoice.created_at else "",
                payments=payment_list,
                payment_collections=payment_list,
            )
        )

    return InvoiceDashboardResponse(
        total_invoices=int(totals[0] or 0),
        total_billed=to_money(totals[1]),
        total_paid=to_money(totals[2]),
        total_due=to_money(totals[3]),
        invoices=invoice_summaries,
    )


def _invoice_category(invoice: InvoiceDocument) -> str:
    payload = invoice.payload_json or {}
    invoice_payload = payload.get("invoice") or {}
    policy = payload.get("document_policy") or {}
    value = (
        invoice_payload.get("invoice_type")
        or policy.get("legal_invoice_type")
        or "bill_of_supply"
    )
    if value in ("BILL_OF_SUPPLY_SIMPLE", "bill_of_supply_simple", "simple_bill_of_supply"):
        return "simple_bill_of_supply"
    if value == "tax_invoice":
        return "tax_invoice"
    return "bill_of_supply"


def _safe_invoice_filename(invoice: InvoiceDocument) -> str:
    raw = f"{invoice.invoice_number}_{invoice.customer_name}_{invoice.invoice_date.isoformat()}"
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", raw).strip(" ._") + ".pdf"


@router.get("/invoices/bulk-download")
def bulk_download_invoices(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
    type: str = Query("all"),
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    allowed_types = {"all", "tax_invoice", "bill_of_supply", "simple_bill_of_supply"}
    if type not in allowed_types:
        raise HTTPException(status_code=422, detail="Invalid invoice category")

    start_date = date(year, month, 1)
    end_date = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    invoices = (
        db.query(InvoiceDocument)
        .filter(factory_id_filter(InvoiceDocument.factory_id, current_user.factory_id))
        .filter(InvoiceDocument.invoice_date >= start_date, InvoiceDocument.invoice_date < end_date)
        .order_by(InvoiceDocument.invoice_date.asc(), InvoiceDocument.id.asc())
        .all()
    )
    selected = [invoice for invoice in invoices if type == "all" or _invoice_category(invoice) == type]
    if not selected:
        raise HTTPException(status_code=404, detail="No invoices found for the selected month and category")

    folder_names = {
        "tax_invoice": "Tax-Invoice",
        "bill_of_supply": "Bill-of-Supply",
        "simple_bill_of_supply": "Simple-Bill-of-Supply",
    }
    month_folder = f"{year:04d}-{month:02d}"
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for invoice in selected:
            category = _invoice_category(invoice)
            path = f"{month_folder}/{folder_names[category]}/{_safe_invoice_filename(invoice)}"
            zip_file.writestr(path, _invoice_pdf_snapshot(db, invoice))
    archive.seek(0)
    return Response(
        content=archive.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="invoices_{month_folder}_{type}.zip"'},
    )


@router.post("/invoices/from-sale/{sale_id}", response_model=InvoiceFromSaleResponse)
def create_invoice_from_sale(
    sale_id: int,
    payload: InvoiceFromSaleRequest = InvoiceFromSaleRequest(),
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = factory_id_text(current_user.factory_id)
    sale = (
        db.query(DailySale)
        .filter(factory_id_filter(DailySale.factory_id, factory_id))
        .filter(DailySale.id == sale_id)
        .first()
    )
    if sale is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found")

    existing = (
        db.query(InvoiceDocument)
        .filter(factory_id_filter(InvoiceDocument.factory_id, factory_id))
        .order_by(InvoiceDocument.id.desc())
        .all()
    )
    for document in existing:
        sale_ids = (document.payload_json or {}).get("invoice", {}).get("sale_ids", [])
        if sale_id in sale_ids:
            return InvoiceFromSaleResponse(
                invoice_id=document.id,
                invoice_number=document.invoice_number,
                pdf_url=f"/api/invoices/{document.id}/pdf",
            )

    factory = db.query(Factory).filter(Factory.id == current_user.factory_id).with_for_update().first()
    customer = (
        db.query(Customer)
        .filter(factory_id_filter(Customer.factory_id, factory_id))
        .filter(Customer.id == sale.customer_id)
        .first()
    )
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    invoice_type = payload.invoice_type if payload.invoice_type in {"tax_invoice", "bill_of_supply"} else "tax_invoice"
    validate_gst_invoice(invoice_type, customer.gst_number, [float(payload.tax_rate or 0)])
    invoice_number = allocate_invoice_number(db, factory, invoice_type)
    subtotal = to_money(sale.total_amount or sale.total_bill)
    tax_rate = max(0.0, float(payload.tax_rate or 0.0)) if invoice_type == "tax_invoice" else 0.0
    intra_state = is_intra_state_supply(factory, customer.gst_number, customer.place)
    total_tax = to_money(subtotal * Decimal(str(tax_rate / 100)))
    cgst = to_money(total_tax / 2) if intra_state else Decimal("0.00")
    sgst = to_money(total_tax / 2) if intra_state else Decimal("0.00")
    igst = total_tax if not intra_state else Decimal("0.00")
    total = to_money(subtotal + cgst + sgst + igst)
    amount_paid = to_money(sale.amount_paid or sale.initial_payment)

    # Calculate ledger-based outstanding before this bill
    ledger_balance = active_customer_outstanding(db, factory_id, customer.id)
    available_advance = to_money(customer.advance_balance)
    
    total_before_advance = to_money(total + ledger_balance)
    advance_adjusted = min(available_advance, total_before_advance)
    remaining_payable = total_before_advance - advance_adjusted
    remaining_advance = available_advance - advance_adjusted

    invoice_payload = {
        "event": "invoice.created_from_sale",
        "factory_id": factory_id,
        "invoice": {
            "invoice_id": invoice_number,
            "invoice_type": invoice_type,
            "sale_ids": [sale.id],
            "invoice_date": sale.date,
            "customer_id": customer.id,
            "customer_name": customer.name,
            "customer_phone": customer_display_phone(customer),
            "customer_place": customer.place,
            "payment_method": payload.payment_method,
            "bill_total": total,
            "amount_paid": amount_paid,
            "previous_due": ledger_balance,
            "total_before_advance": total_before_advance,
            "advance_available": available_advance,
            "advance_adjusted": advance_adjusted,
            "remaining_payable": remaining_payable,
            "advance_balance_remaining": remaining_advance,
            "customer_total_due": remaining_payable,
            "status": "created",
        },
        "items": [{
            "product_size_ml": sale.product_size_ml,
            "variety": sale.variety,
            "packaging_size_name": sale.packaging_size_name,
            "boxes_sold": sale.boxes_sold,
            "loose_packets_sold": sale.loose_packets_sold,
            "rate_per_box": sale.rate_per_box,
            "rate_per_packet": sale.rate_per_packet,
            "line_total": subtotal,
            "tax_rate": tax_rate,
        }],
        "buyer_gstin": customer.gst_number,
        "place_of_supply": customer.place,
        "tax_rate": tax_rate,
        "total_taxable_value": subtotal,
        "total_cgst": cgst,
        "total_sgst": sgst,
        "total_igst": igst,
        "notes": clean_optional_text(payload.notes),
    }
    document = create_invoice_document(
        db=db,
        factory_id=factory_id,
        current_user=current_user,
        customer=customer,
        invoice_payload=invoice_payload,
    )

    if advance_adjusted > 0:
        # Create a ledger-based Payment for advance adjusted
        payment = Payment(
            factory_id=current_user.factory_id,
            customer_phone=customer_display_phone(customer) or customer.phone_number or "",
            sale_id=sale.id,
            amount_paid=advance_adjusted,
            payment_mode="UPI",
            date=sale.date or datetime.now(timezone.utc).date(),
        )
        db.add(payment)
        db.flush()

        apply_payment_to_outstanding_bills(
            db,
            factory_id=current_user.factory_id,
            customer_id=customer.id,
            amount=advance_adjusted,
            payment_mode="UPI",
            collection_date=sale.date or datetime.now(timezone.utc).date(),
            payment_id=payment.id,
            created_by_user_id=current_user.id,
        )

        customer.advance_balance = remaining_advance

    sync_customer_balance_from_bills(db, current_user.factory_id, customer)
    sync_next_invoice_setting(db, factory, invoice_number, invoice_type)
    db.commit()
    return InvoiceFromSaleResponse(
        invoice_id=document.id,
        invoice_number=document.invoice_number,
        pdf_url=f"/api/invoices/{document.id}/pdf",
    )


@router.get("/invoices/{invoice_document_id}/pdf")
def download_invoice_pdf(
    invoice_document_id: int,
    inline: bool = Query(False, description="If true, serve PDF inline in browser"),
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = factory_id_text(current_user.factory_id)
    invoice = (
        db.query(InvoiceDocument)
        .filter(factory_id_filter(InvoiceDocument.factory_id, factory_id))
        .filter(InvoiceDocument.id == invoice_document_id)
        .first()
    )
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    pdf_bytes = _invoice_pdf_snapshot(db, invoice)
    invoice.pdf_generated_count = (invoice.pdf_generated_count or 0) + 1
    invoice.last_pdf_generated_at = datetime.now(timezone.utc)
    db.add(
        InvoiceDeliveryLog(
            factory_id=current_user.factory_id,
            invoice_document_id=invoice.id,
            channel="DOWNLOAD",
            status="COMPLETED",
            created_by_user_id=current_user.id,
        )
    )
    db.commit()

    filename = f"invoice_{factory_id}_{invoice.invoice_number}.pdf".replace("/", "_").replace("\\", "_")
    disposition = "inline" if inline else "attachment"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


def _invoice_for_factory(db: Session, factory_id: int, invoice_document_id: int) -> InvoiceDocument:
    invoice = db.query(InvoiceDocument).filter(
        factory_id_filter(InvoiceDocument.factory_id, factory_id),
        InvoiceDocument.id == invoice_document_id,
    ).first()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return invoice


def _invoice_pdf_snapshot(db: Session, invoice: InvoiceDocument) -> bytes:
    bill = db.query(OutstandingBill).filter(
        OutstandingBill.factory_id == invoice.factory_id,
        OutstandingBill.invoice_document_id == invoice.id,
    ).first()
    payload = dict(invoice.payload_json or {})
    payload["id"] = invoice.id
    invoice_payload = dict(payload.get("invoice") or {})
    invoice_payload["amount_paid"] = float(bill.amount_paid if bill else invoice.amount_paid)
    invoice_payload["customer_total_due"] = float(bill.balance_amount if bill else invoice.customer_total_due)
    payload["invoice"] = invoice_payload
    payload["invoice_total"] = float(bill.bill_amount if bill else invoice.bill_total)
    payload["total_paid_against_invoice"] = float(bill.amount_paid if bill else invoice.amount_paid)
    payload["remaining_balance"] = float(bill.balance_amount if bill else invoice.customer_total_due)
    payload["payment_history"] = _invoice_payment_history(db, invoice, bill)
    return build_invoice_pdf_bytes(payload)


def _invoice_payment_history(
    db: Session,
    invoice: InvoiceDocument,
    bill: OutstandingBill | None,
) -> list[dict[str, object]]:
    if bill is None:
        return []

    collections = (
        db.query(PaymentCollection)
        .filter(
            PaymentCollection.factory_id == invoice.factory_id,
            PaymentCollection.outstanding_bill_id == bill.id,
        )
        .order_by(PaymentCollection.collection_date.asc(), PaymentCollection.created_at.asc(), PaymentCollection.id.asc())
        .all()
    )
    remaining = to_money(bill.bill_amount)
    history = []
    for collection in collections:
        allocated = to_money(collection.amount_collected)
        remaining = max(to_money(remaining - allocated), Decimal("0.00"))
        receiver = collection.created_by
        receiver_name = receiver.full_name or receiver.username if receiver else None
        receiver_role = receiver.role if receiver else None
        received_by = " ".join(part for part in [receiver_role, receiver_name] if part) or "System"
        history.append({
            "date": collection.collection_date,
            "amount_paid": allocated,
            "payment_mode": collection.payment_mode,
            "received_by": received_by,
            "note_reference": collection.reference_number or "-",
            "remaining_after_payment": remaining,
        })
    return history


@router.delete("/invoices/{invoice_document_id}")
def delete_invoice_document(
    invoice_document_id: int,
    payload: InvoiceDeleteRequest,
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    if current_user.role != "Owner":
        raise HTTPException(status_code=403, detail="Only Owner can delete invoices")
    if payload.confirmation.strip() != "DELETE INVOICE":
        raise HTTPException(status_code=422, detail="Type DELETE INVOICE to confirm deletion")

    invoice = (
        db.query(InvoiceDocument)
        .filter(factory_id_filter(InvoiceDocument.factory_id, current_user.factory_id))
        .filter(InvoiceDocument.id == invoice_document_id)
        .with_for_update()
        .first()
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    bill = db.query(OutstandingBill).filter(
        factory_id_filter(OutstandingBill.factory_id, current_user.factory_id),
        OutstandingBill.invoice_document_id == invoice.id,
    ).with_for_update().first()

    payload_json = invoice.payload_json or {}
    sale_ids = list((payload_json.get("invoice") or {}).get("sale_ids") or [])
    item_rows = list(payload_json.get("items") or [])

    # Check for payment allocations or real payments received.
    has_real_payment = False
    if bill is not None:
        if to_money(bill.amount_paid) > 0 or len(bill.payments) > 0:
            has_real_payment = True
        
        coll_exists = db.query(PaymentCollection).filter(
            PaymentCollection.factory_id == current_user.factory_id,
            PaymentCollection.outstanding_bill_id == bill.id,
        ).first()
        if coll_exists is not None:
            has_real_payment = True

    if sale_ids:
        sale_payments = db.query(Payment).filter(
            factory_id_filter(Payment.factory_id, current_user.factory_id),
            Payment.sale_id.in_(sale_ids),
        ).all()
        for sp in sale_payments:
            if to_money(sp.amount_paid) > 0:
                has_real_payment = True
            coll_exists = db.query(PaymentCollection).filter(
                PaymentCollection.factory_id == current_user.factory_id,
                PaymentCollection.payment_id == sp.id,
            ).first()
            if coll_exists is not None:
                has_real_payment = True

    action = getattr(payload, "action", "reverse") or "reverse"

    if action == "archive":
        invoice.status = "archived"
        if bill is not None:
            bill.status = "archived"
        db.commit()
        return {"status": "archived", "invoice_id": invoice_document_id, "invoice_number": invoice.invoice_number}

    if has_real_payment:
        raise HTTPException(
            status_code=409,
            detail="Invoice has payment entries. Delete payment first or use cancel invoice.",
        )

    if action == "cancel":
        invoice.status = "cancelled"
        if bill is not None:
            bill.status = "cancelled"
            bill.balance_amount = Decimal("0.00")
        if sale_ids:
            db.query(DailySale).filter(
                factory_id_filter(DailySale.factory_id, current_user.factory_id),
                DailySale.id.in_(sale_ids),
            ).delete(synchronize_session=False)
            db.flush()
        from routers.inventory import recalculate_and_sync_sku_stock
        seen_skus = set()
        for item in item_rows:
            sku = (
                item.get("product_size_ml"),
                (item.get("variety") or "").strip(),
                (item.get("packaging_size_name") or "").strip(),
            )
            if not all(sku) or sku in seen_skus:
                continue
            seen_skus.add(sku)
            recalculate_and_sync_sku_stock(
                db=db,
                factory_id=str(current_user.factory_id),
                product_size_ml=sku[0],
                variety=sku[1],
                packaging_size_name=sku[2],
            )
        if invoice.customer_id is not None:
            customer = db.query(Customer).filter(
                factory_id_filter(Customer.factory_id, current_user.factory_id),
                Customer.id == invoice.customer_id,
            ).first()
            if customer is not None:
                sync_customer_balance_from_bills(db, current_user.factory_id, customer)
        db.commit()
        return {"status": "cancelled", "invoice_id": invoice_document_id, "invoice_number": invoice.invoice_number}

    invoice_number = invoice.invoice_number
    customer_name = invoice.customer_name
    invoice_amount = to_money(invoice.bill_total)
    customer_id = invoice.customer_id

    try:
        from models import CustomerLedgerAdjustment

        if bill is not None:
            # Delete customer ledger adjustments referencing this bill
            db.query(CustomerLedgerAdjustment).filter(
                CustomerLedgerAdjustment.factory_id == current_user.factory_id,
                CustomerLedgerAdjustment.linked_bill_id == bill.id,
            ).delete(synchronize_session=False)

            # Delete payment collections referencing this bill
            db.query(PaymentCollection).filter(
                PaymentCollection.factory_id == current_user.factory_id,
                PaymentCollection.outstanding_bill_id == bill.id,
            ).delete(synchronize_session=False)

            db.delete(bill)
            db.flush()

        db.query(InvoiceDeliveryLog).filter(
            InvoiceDeliveryLog.factory_id == current_user.factory_id,
            InvoiceDeliveryLog.invoice_document_id == invoice.id,
        ).delete(synchronize_session=False)
        db.delete(invoice)
        db.flush()

        if sale_ids:
            # First find and delete collections referencing payments of these sales
            sale_payment_ids = [p.id for p in db.query(Payment.id).filter(
                factory_id_filter(Payment.factory_id, current_user.factory_id),
                Payment.sale_id.in_(sale_ids),
            ).all()]
            if sale_payment_ids:
                db.query(PaymentCollection).filter(
                    PaymentCollection.factory_id == current_user.factory_id,
                    PaymentCollection.payment_id.in_(sale_payment_ids),
                ).delete(synchronize_session=False)
                db.query(Payment).filter(
                    factory_id_filter(Payment.factory_id, current_user.factory_id),
                    Payment.id.in_(sale_payment_ids),
                ).delete(synchronize_session=False)

            db.query(DailySale).filter(
                factory_id_filter(DailySale.factory_id, current_user.factory_id),
                DailySale.id.in_(sale_ids),
            ).delete(synchronize_session=False)

        from routers.inventory import recalculate_and_sync_sku_stock
        seen_skus = set()
        for item in item_rows:
            sku = (
                item.get("product_size_ml"),
                (item.get("variety") or "").strip(),
                (item.get("packaging_size_name") or "").strip(),
            )
            if not all(sku) or sku in seen_skus:
                continue
            seen_skus.add(sku)
            recalculate_and_sync_sku_stock(
                db=db,
                factory_id=str(current_user.factory_id),
                product_size_ml=sku[0],
                variety=sku[1],
                packaging_size_name=sku[2],
            )

        match = re.search(r"(\d+)$", invoice_number or "")
        if match:
            recycled_number = int(match.group(1))
            exists = db.query(RecycledInvoice.id).filter(
                RecycledInvoice.factory_id == current_user.factory_id,
                RecycledInvoice.recycled_number == recycled_number,
            ).first()
            if exists is None:
                db.add(RecycledInvoice(factory_id=current_user.factory_id, recycled_number=recycled_number))

        if customer_id is not None:
            customer = db.query(Customer).filter(
                factory_id_filter(Customer.factory_id, current_user.factory_id),
                Customer.id == customer_id,
            ).first()
            if customer is not None:
                sync_customer_balance_from_bills(db, current_user.factory_id, customer)

        deleted_at = datetime.now(timezone.utc)
        db.add(ActivityLog(
            factory_id=int(current_user.factory_id),
            event_type="invoice",
            description="Invoice deleted by owner",
            log_date=deleted_at.date(),
            user_id=current_user.id,
            user_role=current_user.role,
            user_name=current_user.full_name or current_user.username,
            action_type="DELETE",
            action_summary=f"Invoice {invoice_number} deleted by owner",
            entity_name=invoice_number,
            entity_type="invoice",
            entity_id=invoice_document_id,
            short_statement="Invoice deleted by owner",
            committed_at=deleted_at,
            metadata_json={
                "invoice_number": invoice_number,
                "customer_name": customer_name,
                "amount": str(invoice_amount),
                "deleted_by": current_user.full_name or current_user.username,
                "deleted_at": deleted_at.isoformat(),
            },
        ))
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Invoice deletion failed: invoice_id=%s factory_id=%s", invoice_document_id, current_user.factory_id)
        raise HTTPException(status_code=409, detail="Invoice could not be deleted safely") from exc

    return {"status": "deleted", "invoice_id": invoice_document_id, "invoice_number": invoice_number}


@router.delete("/invoices/{invoice_id}/hard-delete")
def hard_delete_invoice_document(
    invoice_id: int,
    payload: InvoiceHardDeleteRequest,
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    if current_user.role != "Owner":
        raise HTTPException(status_code=403, detail="Only Owner can delete invoices")
    
    if not payload.confirm_test_invoice:
        raise HTTPException(status_code=422, detail="confirm_test_invoice must be true to verify test invoice deletion")
    if not payload.reason.strip():
        raise HTTPException(status_code=422, detail="Deletion reason is mandatory")
        
    invoice = (
        db.query(InvoiceDocument)
        .filter(factory_id_filter(InvoiceDocument.factory_id, current_user.factory_id))
        .filter(InvoiceDocument.id == invoice_id)
        .with_for_update()
        .first()
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    if payload.confirm_invoice_number != invoice.invoice_number:
        raise HTTPException(
            status_code=422,
            detail=f"Invoice number confirmation mismatch: expected '{invoice.invoice_number}', got '{payload.confirm_invoice_number}'"
        )
        
    if getattr(invoice, "accounting_locked", False) or invoice.exported_at or invoice.shared_at or invoice.emailed_at or invoice.printed_at:
        raise HTTPException(status_code=409, detail="Invoice is locked for accounting and cannot be hard deleted. You can only archive or cancel it.")
        
    bill = db.query(OutstandingBill).filter(
        factory_id_filter(OutstandingBill.factory_id, current_user.factory_id),
        OutstandingBill.invoice_document_id == invoice.id,
    ).with_for_update().first()

    has_real_payment = False
    if bill is not None:
        if to_money(bill.amount_paid) > 0 or len(bill.payments) > 0:
            has_real_payment = True
        
        coll_exists = db.query(PaymentCollection).filter(
            PaymentCollection.factory_id == current_user.factory_id,
            PaymentCollection.outstanding_bill_id == bill.id,
        ).first()
        if coll_exists is not None:
            has_real_payment = True

    payload_json = invoice.payload_json or {}
    sale_ids = list((payload_json.get("invoice") or {}).get("sale_ids") or [])
    item_rows = list(payload_json.get("items") or [])

    if sale_ids:
        sale_payments = db.query(Payment).filter(
            factory_id_filter(Payment.factory_id, current_user.factory_id),
            Payment.sale_id.in_(sale_ids),
        ).all()
        for sp in sale_payments:
            if to_money(sp.amount_paid) > 0:
                has_real_payment = True
            coll_exists = db.query(PaymentCollection).filter(
                PaymentCollection.factory_id == current_user.factory_id,
                PaymentCollection.payment_id == sp.id,
            ).first()
            if coll_exists is not None:
                has_real_payment = True

    if has_real_payment and not payload.reverse_payments:
        raise HTTPException(
            status_code=409,
            detail="Invoice has payment entries. Either allow reverse_payments or delete payments first."
        )

    # Determine if this is the latest invoice number
    import re
    match = re.search(r"(\d+)$", invoice.invoice_number or "")
    is_latest = True
    deleted_seq = None
    if match:
        deleted_seq = int(match.group(1))
        prefix_part = invoice.invoice_number[:match.start()]
        other_invoices = db.query(InvoiceDocument.invoice_number).filter(
            InvoiceDocument.factory_id == current_user.factory_id,
            InvoiceDocument.id != invoice.id,
            InvoiceDocument.invoice_number.like(f"{prefix_part}%")
        ).all()
        for (other_num,) in other_invoices:
            other_match = re.search(r"(\d+)$", other_num or "")
            if other_match:
                other_seq = int(other_match.group(1))
                if other_seq > deleted_seq:
                    is_latest = False
                    break

    if not is_latest:
        raise HTTPException(
            status_code=400,
            detail="This is not the latest invoice. Deleting it will create a numbering gap. You can archive/cancel it instead, or super admin can reset sequence manually."
        )

    invoice_number = invoice.invoice_number
    customer_name = invoice.customer_name
    invoice_amount = to_money(invoice.bill_total)
    customer_id = invoice.customer_id

    try:
        from models import CustomerLedgerAdjustment, BillPayment

        if bill is not None:
            # Delete BillPayment associations
            db.query(BillPayment).filter(
                BillPayment.factory_id == current_user.factory_id,
                BillPayment.bill_id == bill.id,
            ).delete(synchronize_session=False)

            # Delete customer ledger adjustments referencing this bill
            db.query(CustomerLedgerAdjustment).filter(
                CustomerLedgerAdjustment.factory_id == current_user.factory_id,
                CustomerLedgerAdjustment.linked_bill_id == bill.id,
            ).delete(synchronize_session=False)

            # Delete payment collections referencing this bill
            db.query(PaymentCollection).filter(
                PaymentCollection.factory_id == current_user.factory_id,
                PaymentCollection.outstanding_bill_id == bill.id,
            ).delete(synchronize_session=False)

            db.delete(bill)
            db.flush()

        db.query(InvoiceDeliveryLog).filter(
            InvoiceDeliveryLog.factory_id == current_user.factory_id,
            InvoiceDeliveryLog.invoice_document_id == invoice.id,
        ).delete(synchronize_session=False)
        db.delete(invoice)
        db.flush()

        if sale_ids:
            # First find and delete collections referencing payments of these sales
            sale_payment_ids = [p.id for p in db.query(Payment.id).filter(
                factory_id_filter(Payment.factory_id, current_user.factory_id),
                Payment.sale_id.in_(sale_ids),
            ).all()]
            if sale_payment_ids:
                db.query(PaymentCollection).filter(
                    PaymentCollection.factory_id == current_user.factory_id,
                    PaymentCollection.payment_id.in_(sale_payment_ids),
                ).delete(synchronize_session=False)
                db.query(Payment).filter(
                    factory_id_filter(Payment.factory_id, current_user.factory_id),
                    Payment.id.in_(sale_payment_ids),
                ).delete(synchronize_session=False)

            db.query(DailySale).filter(
                factory_id_filter(DailySale.factory_id, current_user.factory_id),
                DailySale.id.in_(sale_ids),
            ).delete(synchronize_session=False)

        # Restore stock impact
        from routers.inventory import recalculate_and_sync_sku_stock
        seen_skus = set()
        for item in item_rows:
            sku = (
                item.get("product_size_ml"),
                (item.get("variety") or "").strip(),
                (item.get("packaging_size_name") or "").strip(),
            )
            if not all(sku) or sku in seen_skus:
                continue
            seen_skus.add(sku)
            recalculate_and_sync_sku_stock(
                db=db,
                factory_id=str(current_user.factory_id),
                product_size_ml=sku[0],
                variety=sku[1],
                packaging_size_name=sku[2],
            )

        # Update invoice sequence
        if is_latest and deleted_seq is not None:
            # Delete from RecycledInvoice if it exists
            db.query(RecycledInvoice).filter(
                RecycledInvoice.factory_id == current_user.factory_id,
                RecycledInvoice.recycled_number == deleted_seq
            ).delete(synchronize_session=False)

            invoice_type = payload_json.get("document_policy", {}).get("legal_invoice_type") or "bill_of_supply"
            attr = _invoice_counter_attr(invoice_type)
            settings_attr = _settings_counter_attr(invoice_type)
            settings = get_or_create_factory_settings(db, current_user.factory_id, for_update=True)
            factory = db.query(Factory).filter(Factory.id == current_user.factory_id).with_for_update().first()
            setattr(settings, settings_attr, deleted_seq)
            setattr(factory, attr, deleted_seq)

        if customer_id is not None:
            customer = db.query(Customer).filter(
                factory_id_filter(Customer.factory_id, current_user.factory_id),
                Customer.id == customer_id,
            ).first()
            if customer is not None:
                sync_customer_balance_from_bills(db, current_user.factory_id, customer)

        deleted_at = datetime.now(timezone.utc)
        db.add(ActivityLog(
            factory_id=int(current_user.factory_id),
            event_type="invoice",
            description=f"Invoice hard-deleted by owner. Reason: {payload.reason}",
            log_date=deleted_at.date(),
            user_id=current_user.id,
            user_role=current_user.role,
            user_name=current_user.full_name or current_user.username,
            action_type="DELETE",
            action_summary=f"Invoice {invoice_number} hard-deleted by owner. Reason: {payload.reason}",
            entity_name=invoice_number,
            entity_type="invoice",
            entity_id=invoice_id,
            short_statement="Invoice hard-deleted by owner",
            committed_at=deleted_at,
            metadata_json={
                "invoice_number": invoice_number,
                "customer_name": customer_name,
                "amount": str(invoice_amount),
                "deleted_by": current_user.full_name or current_user.username,
                "deleted_at": deleted_at.isoformat(),
                "reason": payload.reason,
            },
        ))
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Invoice hard-deletion failed: invoice_id=%s factory_id=%s", invoice_id, current_user.factory_id)
        raise HTTPException(status_code=409, detail="Invoice could not be hard deleted safely") from exc

    return {"status": "deleted", "invoice_id": invoice_id, "invoice_number": invoice_number}


def _record_invoice_delivery(
    db: Session,
    *,
    current_user: User,
    invoice: InvoiceDocument,
    channel: str,
    destination: str | None,
    delivery_status: str,
    error: str | None = None,
) -> None:
    db.add(
        InvoiceDeliveryLog(
            factory_id=current_user.factory_id,
            invoice_document_id=invoice.id,
            channel=channel,
            destination_masked=destination,
            status=delivery_status,
            error_message=error[:500] if error else None,
            created_by_user_id=current_user.id,
        )
    )
    db.commit()


def _mask_email(email: str) -> str:
    local, domain = email.split("@", 1)
    return f"{local[:2]}***@{domain}"


@router.post("/invoices/{invoice_document_id}/reprint", response_model=InvoiceDeliveryResponse)
def reprint_invoice(
    invoice_document_id: int,
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    invoice = _invoice_for_factory(db, current_user.factory_id, invoice_document_id)
    _record_invoice_delivery(
        db, current_user=current_user, invoice=invoice, channel="REPRINT",
        destination=None, delivery_status="COMPLETED",
    )
    return InvoiceDeliveryResponse(status="completed", channel="REPRINT", destination="")


@router.post("/invoices/{invoice_document_id}/telegram", response_model=InvoiceDeliveryResponse)
def deliver_invoice_telegram(
    invoice_document_id: int,
    payload: InvoiceTelegramDeliveryRequest,
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db),
):
    invoice = _invoice_for_factory(db, current_user.factory_id, invoice_document_id)
    factory = db.query(Factory).filter(Factory.id == current_user.factory_id).first()
    destination = payload.destination.strip().lower()
    if destination == "customer":
        customer = db.query(Customer).filter(
            Customer.id == invoice.customer_id,
            factory_id_filter(Customer.factory_id, current_user.factory_id),
        ).first()
        targets = [customer.telegram_id] if customer and customer.telegram_id else []
    elif destination == "owner":
        targets = [
            row.telegram_chat_id
            for row in db.query(TelegramUserBinding).filter(
                TelegramUserBinding.factory_id == current_user.factory_id,
                TelegramUserBinding.role == "Owner",
                TelegramUserBinding.is_active.is_(True),
            ).all()
        ]
        if not targets and factory and factory.telegram_chat_id:
            targets = [factory.telegram_chat_id]
    else:
        raise HTTPException(status_code=422, detail="Telegram destination must be customer or owner")
    if not targets:
        raise HTTPException(status_code=409, detail=f"Telegram is not connected for {destination}")
    token = decrypt_token(factory.telegram_token) if factory and factory.telegram_token else (factory.telegram_bot_token if factory else "")
    if not token:
        raise HTTPException(status_code=409, detail="Factory Telegram bot is not configured")

    pdf_bytes = _invoice_pdf_snapshot(db, invoice)
    filename = f"{invoice.invoice_number}.pdf".replace("/", "_").replace("\\", "_")
    try:
        for chat_id in dict.fromkeys(targets):
            response = httpx.post(
                f"https://api.telegram.org/bot{token}/sendDocument",
                data={"chat_id": chat_id, "caption": f"Invoice {invoice.invoice_number} - {invoice.customer_name}"},
                files={"document": (filename, pdf_bytes, "application/pdf")},
                timeout=20,
            )
            response.raise_for_status()
            if not response.json().get("ok"):
                raise RuntimeError("Telegram rejected the invoice")
        _record_invoice_delivery(
            db, current_user=current_user, invoice=invoice, channel="TELEGRAM",
            destination=destination, delivery_status="SENT",
        )
    except Exception as exc:
        _record_invoice_delivery(
            db, current_user=current_user, invoice=invoice, channel="TELEGRAM",
            destination=destination, delivery_status="FAILED", error=type(exc).__name__,
        )
        raise HTTPException(status_code=502, detail="Invoice could not be delivered on Telegram") from exc
    return InvoiceDeliveryResponse(status="sent", channel="TELEGRAM", destination=destination)


@router.post("/invoices/{invoice_document_id}/email", response_model=InvoiceDeliveryResponse)
async def deliver_invoice_email(
    invoice_document_id: int,
    payload: InvoiceEmailDeliveryRequest,
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db),
):
    invoice = _invoice_for_factory(db, current_user.factory_id, invoice_document_id)
    customer = db.query(Customer).filter(
        Customer.factory_id == current_user.factory_id,
        Customer.id == invoice.customer_id,
    ).first() if invoice.customer_id else None
    recipient = (str(payload.email) if payload.email else (customer.email if customer else "") or "").strip().lower()
    if not is_email_address(recipient):
        raise HTTPException(status_code=422, detail="Customer email is missing. Enter a valid email address.")
    mail_config = build_mail_config()
    if mail_config is None:
        raise HTTPException(status_code=503, detail="Email delivery is not configured")
    pdf_bytes = _invoice_pdf_snapshot(db, invoice)
    filename = f"{invoice.invoice_number}.pdf".replace("/", "_").replace("\\", "_")
    message = MessageSchema(
        subject=f"Invoice {invoice.invoice_number} from {factory_display_name(current_user)}",
        recipients=[recipient],
        body=(
            f"Hello {invoice.customer_name},\n\n"
            f"Please find attached invoice {invoice.invoice_number} from {factory_display_name(current_user)}.\n"
            f"Invoice amount: Rs {to_money(invoice.bill_total)}\n"
            f"Remaining payable: Rs {to_money(invoice.customer_total_due)}\n"
        ),
        subtype=MessageType.plain,
        attachments=[{"file": BytesIO(pdf_bytes), "filename": filename, "content_type": "application/pdf"}],
    )
    try:
        await FastMail(mail_config).send_message(message)
        _record_invoice_delivery(
            db, current_user=current_user, invoice=invoice, channel="EMAIL",
            destination=_mask_email(recipient), delivery_status="SENT",
        )
    except Exception as exc:
        _record_invoice_delivery(
            db, current_user=current_user, invoice=invoice, channel="EMAIL",
            destination=_mask_email(recipient), delivery_status="FAILED", error=type(exc).__name__,
        )
        raise HTTPException(status_code=502, detail="Invoice could not be delivered by email") from exc
    return InvoiceDeliveryResponse(status="sent", channel="EMAIL", destination=_mask_email(recipient))


@router.get("/invoices/{invoice_document_id}/history", response_model=list[InvoiceDeliveryHistoryItem])
def invoice_delivery_history(
    invoice_document_id: int,
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    invoice = _invoice_for_factory(db, current_user.factory_id, invoice_document_id)
    rows = db.query(InvoiceDeliveryLog).filter(
        InvoiceDeliveryLog.factory_id == current_user.factory_id,
        InvoiceDeliveryLog.invoice_document_id == invoice.id,
    ).order_by(InvoiceDeliveryLog.created_at.desc(), InvoiceDeliveryLog.id.desc()).limit(100).all()
    return [
        InvoiceDeliveryHistoryItem(
            id=row.id, channel=row.channel, destination_masked=row.destination_masked,
            status=row.status, error_message=row.error_message,
            created_at=row.created_at.isoformat() if row.created_at else "",
        )
        for row in rows
    ]


@router.get("/pending", response_model=list[PendingSaleResponse])
def list_pending_sales(
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db),
):
    try:
        orders = (
            db.query(Order)
            .options(joinedload(Order.customer), joinedload(Order.items))
            .filter(factory_id_filter(Order.factory_id, current_user.factory_id))
            .filter(Order.status == "pending_owner")
            .order_by(Order.order_date.desc(), Order.id.desc())
            .all()
        )
        return [
            PendingSaleResponse(
                order_id=order.id,
                customer_id=order.customer_id,
                customer_name=order.customer.name if order.customer else "",
                customer_phone=customer_display_phone(order.customer) if order.customer else "",
                total_amount=to_money(order.total_amount),
                status=order.status,
                order_date=order.order_date.isoformat() if order.order_date else "",
                items=[
                    PendingSaleItemResponse(
                        product_size_ml=item.product_size_ml,
                        variety=item.variety,
                        packaging_size_name=item.packaging_size_name,
                        boxes_sold=item.boxes_sold or 0,
                        loose_packets_sold=item.loose_packets_sold or 0,
                        rate_per_box=effective_rate_per_box(item),
                        rate_per_packet=to_money(item.rate_per_packet),
                    )
                    for item in order.items
                ],
            )
            for order in orders
        ]
    except Exception as e:
        logger.warning("Pending sales query failed for factory_id=%s", current_user.factory_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching pending sales") from e


@router.post("/order/{order_id}/approve", response_model=SalesOrderActionResponse)
def approve_sales_order(
    order_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    try:
        order = (
            db.query(Order)
            .options(joinedload(Order.customer), joinedload(Order.items))
            .filter(factory_id_filter(Order.factory_id, current_user.factory_id))
            .filter(Order.id == order_id)
            .with_for_update(of=Order)
            .first()
        )
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Pending order {order_id} not found for factory {current_user.factory_id}",
            )
        if order.status != "pending_owner":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending orders can be approved")

        for item in order.items:
            if not item.packaging_size_name or item.product_size_ml is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Order item is missing stock details")

            stock = find_final_stock_for_sale(db, current_user.factory_id, item, lock=True)
            if stock is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Stock not found for pending order item: "
                        f"{item.product_size_ml}ml {item.variety or ''} {item.packaging_size_name}"
                    ),
                )

            # Resolve exact live dynamic stock balance
            from routers.inventory import calculate_live_sku_stock
            packets_per_box = stock.packets_per_box_limit or 1000
            live_boxes, live_loose = calculate_live_sku_stock(
                db=db,
                factory_id=str(current_user.factory_id),
                product_size_ml=item.product_size_ml,
                variety=item.variety,
                packaging_size_name=item.packaging_size_name,
                onboarding_boxes=stock.total_boxes or 0,
                onboarding_loose=stock.loose_packets or 0,
                packets_per_box_limit=packets_per_box
            )
            available_packets = live_boxes * packets_per_box + live_loose
            requested_packets = (item.boxes_sold or 0) * packets_per_box + (item.loose_packets_sold or 0)
            if available_packets < requested_packets:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Insufficient final product stock for {item.product_size_ml}ml {item.variety} {item.packaging_size_name}",
                )

            # Preserve onboarding totals in stock.total_boxes. Dynamic sync helper recalculates current_quantity.

            box_stock = (
                db.query(BoxStock)
                .filter(factory_id_filter(BoxStock.factory_id, current_user.factory_id))
                .filter(sql_func.lower(BoxStock.packaging_size_name) == item.packaging_size_name.lower())
                .with_for_update()
                .first()
            )
            if box_stock is not None and item.boxes_sold:
                box_stock.total_boxes = max((box_stock.total_boxes or 0) - item.boxes_sold, 0)
                box_stock.quantity = max((box_stock.quantity or 0) - item.boxes_sold, 0)

        order.status = "confirmed"
        order.owner_confirmed_at = datetime.now(timezone.utc)
        order.balance_amount = max(to_money(order.total_amount) - to_money(order.amount_paid), Decimal("0.00"))
        order.pending_amount = order.balance_amount
        order.payment_status = payment_status_for(to_money(order.total_amount), to_money(order.amount_paid))
        if order.customer is not None:
            new_balance = to_money(order.customer.total_due or order.customer.balance_amount or 0) + to_money(order.balance_amount)
            order.customer.total_due = new_balance
            order.customer.balance_amount = new_balance
            order.customer.pending_balance = new_balance
            order.customer.pending_dues = float(new_balance)

        # Recalculate dynamic live stock balance and sync caches for all sold SKUs
        from routers.inventory import recalculate_and_sync_sku_stock
        for item in order.items:
            recalculate_and_sync_sku_stock(
                db=db,
                factory_id=str(current_user.factory_id),
                product_size_ml=item.product_size_ml,
                variety=item.variety,
                packaging_size_name=item.packaging_size_name,
            )

        activity = ActivityLog(
            factory_id=current_user.factory_id,
            event_type="payment",
            description=f"Approved Storefront Order #{order.id} for customer {order.customer.name if order.customer else 'N/A'}: Bill Total ₹{order.total_amount:,.2f}"
        )
        db.add(activity)

        invoice_payload = build_order_invoice_payload(db, str(current_user.factory_id), order)
        create_invoice_document(
            db=db,
            factory_id=str(current_user.factory_id),
            current_user=current_user,
            customer=order.customer,
            invoice_payload=invoice_payload,
            order_id=order.id,
        )
        if order.customer is not None:
            sync_customer_balance_from_bills(db, current_user.factory_id, order.customer)

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        logger.warning("Sales order approval failed for order_id=%s factory_id=%s", order_id, current_user.factory_id, exc_info=True)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Order approval failed") from exc

    background_tasks.add_task(
        sync_data_to_n8n_bg,
        factory_id=str(current_user.factory_id),
        sync_type="sales",
        action="insert",
        data={"order_id": order_id, "status": order.status},
    )
    if order.customer is not None:
        message = build_confirmed_bill_message(order.customer.name, factory_display_name(current_user), to_money(order.total_amount))
        background_tasks.add_task(send_order_whatsapp_bill, customer_display_phone(order.customer), message)

    return SalesOrderActionResponse(
        message="Bill sent to Customer via WhatsApp.",
        order_id=order.id,
        status=order.status,
    )


@router.post("/order/{order_id}/reject", response_model=SalesOrderActionResponse)
def reject_sales_order(
    order_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    try:
        order = (
            db.query(Order)
            .filter(factory_id_filter(Order.factory_id, current_user.factory_id))
            .filter(Order.id == order_id)
            .with_for_update()
            .first()
        )
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Pending order {order_id} not found for factory {current_user.factory_id}",
            )
        if order.status != "pending_owner":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending orders can be rejected")

        order.status = "cancelled"
        db.commit()
        background_tasks.add_task(
            sync_data_to_n8n_bg,
            factory_id=str(current_user.factory_id),
            sync_type="sales",
            action="delete",
            data={"order_id": order_id, "status": order.status},
        )
        return SalesOrderActionResponse(message="Order rejected.", order_id=order.id, status=order.status)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        logger.warning("Sales order rejection failed for order_id=%s factory_id=%s", order_id, current_user.factory_id, exc_info=True)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Order rejection failed") from exc


@router.get("/outstanding", response_model=SalesOutstandingResponse)
def get_sales_outstanding(
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    ledger_bills = (
        db.query(OutstandingBill)
        .options(joinedload(OutstandingBill.customer), joinedload(OutstandingBill.payments))
        .filter(factory_id_filter(OutstandingBill.factory_id, current_user.factory_id))
        .filter(OutstandingBill.balance_amount > 0)
        .filter(OutstandingBill.status.in_(["active", "partial"]))
        .filter(OutstandingBill.deleted_at.is_(None))
        .order_by(OutstandingBill.customer_id.asc(), OutstandingBill.bill_date.asc(), OutstandingBill.id.asc())
        .all()
    )
    if ledger_bills:
        grouped: dict[int, OutstandingCustomerBillsResponse] = {}
        grand_total = Decimal("0.00")
        source_totals = {
            "opening_outstanding": Decimal("0.00"),
            "invoice": Decimal("0.00"),
            "manual_adjustment": Decimal("0.00"),
        }
        for bill in ledger_bills:
            if bill.customer is None:
                continue
            customer_id = bill.customer.id
            if customer_id not in grouped:
                grouped[customer_id] = OutstandingCustomerBillsResponse(
                    customer_id=customer_id,
                    customer_name=bill.customer.name,
                    customer_phone=customer_display_phone(bill.customer),
                    place=bill.customer.place or bill.customer.address or "",
                    total_bill_amount=Decimal("0.00"),
                    total_paid=Decimal("0.00"),
                    current_pending_balance=Decimal("0.00"),
                    opening_outstanding=to_money(bill.customer.previous_due or 0),
                    advance_balance=to_money(bill.customer.advance_balance or 0),
                    bills=[],
                )
            row = grouped[customer_id]
            row.total_bill_amount = to_money(row.total_bill_amount + to_money(bill.bill_amount))
            row.total_paid = to_money(row.total_paid + to_money(bill.amount_paid))
            row.current_pending_balance = to_money(row.current_pending_balance + to_money(bill.balance_amount))
            normalized_source = "opening_outstanding" if bill.source_type in ("opening_balance", "opening_outstanding") else bill.source_type
            if normalized_source == "opening_outstanding":
                row.opening_outstanding_remaining = to_money(row.opening_outstanding_remaining + bill.balance_amount)
            elif normalized_source == "manual_adjustment":
                row.manual_adjustment_remaining = to_money(row.manual_adjustment_remaining + bill.balance_amount)
            else:
                row.invoice_outstanding_remaining = to_money(row.invoice_outstanding_remaining + bill.balance_amount)
                normalized_source = "invoice"
            source_totals[normalized_source] = to_money(source_totals[normalized_source] + bill.balance_amount)
            row.bills.append(
                OutstandingBillResponse(
                    bill_id=bill.id,
                    order_id=bill.order_id,
                    order_date=bill.bill_date.isoformat() if bill.bill_date else "",
                    bill_amount=to_money(bill.bill_amount),
                    amount_paid=to_money(bill.amount_paid),
                    remaining_balance=to_money(bill.balance_amount),
                    status=bill.status,
                    source_type=normalized_source,
                    source_label={
                        "opening_outstanding": "Opening Outstanding / Old Balance",
                        "manual_adjustment": "Manual Adjustment",
                    }.get(normalized_source, "Generated Invoice"),
                    stock_impact=normalized_source == "invoice",
                    note=bill.note,
                    payments=[
                        BillPaymentLogResponse(
                            id=p.id,
                            amount_allocated=to_money(p.amount_allocated),
                            payment_date=p.payment_date.isoformat() if p.payment_date else "",
                            received_by_name=p.received_by_name,
                            received_by_role=p.received_by_role,
                        )
                        for p in (bill.payments or [])
                    ]
                )
            )
            grand_total = to_money(grand_total + to_money(bill.balance_amount))

        return SalesOutstandingResponse(
            grand_total_outstanding=grand_total,
            source_totals=source_totals,
            customers=list(grouped.values()),
        )

    orders = (
        db.query(Order)
        .options(joinedload(Order.customer))
        .filter(factory_id_filter(Order.factory_id, current_user.factory_id))
        .filter(Order.balance_amount > 0)
        .filter(Order.status.notin_(["cancelled", "adjusted_closed", "Rejected"]))
        .order_by(Order.customer_id.asc(), Order.order_date.asc(), Order.id.asc())
        .all()
    )

    grouped: dict[int, OutstandingCustomerBillsResponse] = {}
    grand_total = Decimal("0.00")
    for order in orders:
        if order.customer is None:
            continue
        customer_id = order.customer.id
        if customer_id not in grouped:
            grouped[customer_id] = OutstandingCustomerBillsResponse(
                customer_id=customer_id,
                customer_name=order.customer.name,
                customer_phone=customer_display_phone(order.customer),
                place=order.customer.place or order.customer.address or "",
                total_bill_amount=Decimal("0.00"),
                total_paid=Decimal("0.00"),
                current_pending_balance=Decimal("0.00"),
                opening_outstanding=to_money(order.customer.previous_due or 0),
                advance_balance=to_money(order.customer.advance_balance or 0),
                bills=[],
            )

        row = grouped[customer_id]
        bill_amount = to_money(order.total_amount)
        paid_amount = to_money(order.amount_paid)
        balance = to_money(order.balance_amount)
        row.total_bill_amount = to_money(row.total_bill_amount + bill_amount)
        row.total_paid = to_money(row.total_paid + paid_amount)
        row.current_pending_balance = to_money(row.current_pending_balance + balance)
        row.bills.append(
            OutstandingBillResponse(
                bill_id=None,
                order_id=order.id,
                order_date=order.order_date.isoformat() if order.order_date else "",
                bill_amount=bill_amount,
                amount_paid=paid_amount,
                remaining_balance=balance,
                status=order.status,
            )
        )
        grand_total = to_money(grand_total + balance)

    return SalesOutstandingResponse(grand_total_outstanding=grand_total, customers=list(grouped.values()))


@router.get("/dues/pending", response_model=list[PendingDueResponse])
def get_pending_payment_dues(
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    try:
        return pending_payment_dues(db, current_user.factory_id)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Pending dues fetch failed: {exc}") from exc


@router.delete("/outstanding/{bill_id}", response_model=SalesOrderActionResponse)
def clear_outstanding_order(
    bill_id: int,
    background_tasks: BackgroundTasks,
    confirm: bool = Query(default=True),
    reason: str = Query(None, description="Reason for deleting the bill: mistake or paid"),
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    if current_user.role.lower() == "supervisor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Supervisor role is not authorized to edit or delete operational data",
        )
    if current_user.role not in {"Owner", "Sub-Owner"}:
        return SalesOrderActionResponse(
            status="error",
            message="Access Denied: Only the Factory Owner is authorized to delete entries.",
            order_id=bill_id
        )
    if not confirm:
        return SalesOrderActionResponse(
            status="error",
            message="Confirmation required to clear outstanding balance",
            order_id=bill_id
        )

    factory_id = int(current_user.factory_id)
    return_order_id = bill_id

    # Enforce atomic transaction
    if not db.in_transaction():
        db.begin()

    try:
        # 1. Look up the OutstandingBill
        ledger_bill = (
            db.query(OutstandingBill)
            .options(joinedload(OutstandingBill.customer), joinedload(OutstandingBill.order))
            .filter(factory_id_filter(OutstandingBill.factory_id, current_user.factory_id))
            .filter(OutstandingBill.id == bill_id)
            .with_for_update()
            .first()
        )

        if ledger_bill is not None:
            customer_id = ledger_bill.customer_id
            order_id = ledger_bill.order_id
            if order_id is not None:
                return_order_id = order_id
            else:
                # Fallback to invoice document if order_id is not directly set
                if ledger_bill.invoice_document_id is not None:
                    invoice_doc = db.query(InvoiceDocument).filter(InvoiceDocument.id == ledger_bill.invoice_document_id).first()
                    if invoice_doc is not None and invoice_doc.order_id is not None:
                        order_id = invoice_doc.order_id
                        return_order_id = order_id

            # Fetch active line items and quantities associated with this bill/invoice before dropping it
            order_items = []
            if order_id is not None:
                order_items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()

            # Dynamic stock restoration based on deletion reason
            if reason == "mistake":
                # Find sale_ids and items from invoice document if order_id is not set or order_items is empty
                sale_ids = []
                invoice_items_data = []
                if ledger_bill.invoice_document_id is not None:
                    invoice_doc = db.query(InvoiceDocument).filter(InvoiceDocument.id == ledger_bill.invoice_document_id).first()
                    if invoice_doc:
                        # Recycle invoice number
                        import re
                        from models import RecycledInvoice
                        match = re.search(r'\d+', invoice_doc.invoice_number or "")
                        if match:
                            recycled_num = int(match.group())
                            exists = db.query(RecycledInvoice).filter(
                                RecycledInvoice.factory_id == current_user.factory_id,
                                RecycledInvoice.recycled_number == recycled_num
                            ).first()
                            if not exists:
                                db.add(RecycledInvoice(
                                    factory_id=current_user.factory_id,
                                    recycled_number=recycled_num
                                ))
                                db.flush()
                        
                        # Hard-delete the InvoiceDocument
                        db.delete(invoice_doc)
                        db.flush()

                        if invoice_doc.payload_json:
                            invoice_data = invoice_doc.payload_json.get("invoice", {})
                            sale_ids = invoice_data.get("sale_ids", [])
                            invoice_items_data = invoice_doc.payload_json.get("items", [])

                # 1. Delete daily sales from database so they don't count towards live stock calculations
                if sale_ids:
                    db.query(DailySale).filter(DailySale.id.in_(sale_ids)).delete(synchronize_session=False)
                elif ledger_bill.customer_id is not None:
                    db.query(DailySale).filter(
                        DailySale.factory_id == str(factory_id),
                        DailySale.customer_id == ledger_bill.customer_id,
                        DailySale.date == ledger_bill.bill_date
                    ).delete(synchronize_session=False)

                # 2. Sequential Stock = Stock + Order_Quantity increment on FinishedGoodsStock and FinalProductStock
                if order_items:
                    for item in order_items:
                        qty = item.boxes_sold or item.quantity or 0
                        if qty > 0:
                            # Update FinishedGoodsStock if product_id is set
                            if item.product_id is not None:
                                fg_stock = db.query(FinishedGoodsStock).filter(
                                    FinishedGoodsStock.factory_id == str(factory_id),
                                    FinishedGoodsStock.id == item.product_id
                                ).with_for_update().first()
                                if fg_stock is not None:
                                    fg_stock.boxes_available += qty
                                    db.add(fg_stock)
                            
                            # Sequential lookup on FinalProductStock by product attributes
                            if item.product_size_ml and item.packaging_size_name:
                                variety_val = item.variety or "Standard/White"
                                final_stock = db.query(FinalProductStock).filter(
                                    FinalProductStock.factory_id == str(factory_id),
                                    FinalProductStock.product_size_ml == item.product_size_ml,
                                    sql_func.lower(FinalProductStock.variety) == variety_val.strip().lower(),
                                    sql_func.lower(FinalProductStock.packaging_size_name) == item.packaging_size_name.strip().lower()
                                ).with_for_update().first()
                                if final_stock is not None:
                                    final_stock.current_quantity += qty
                                    db.add(final_stock)
                                    
                                    # Cross-sync FinishedGoodsStock by profile
                                    profile = db.query(PackagingProfile).filter(
                                        PackagingProfile.factory_id == str(factory_id),
                                        PackagingProfile.cup_size_ml == item.product_size_ml,
                                        sql_func.lower(PackagingProfile.profile_name) == item.packaging_size_name.strip().lower()
                                    ).first()
                                    if profile:
                                        fg_stock2 = db.query(FinishedGoodsStock).filter(
                                            FinishedGoodsStock.factory_id == str(factory_id),
                                            FinishedGoodsStock.packaging_profile_id == profile.id
                                        ).with_for_update().first()
                                        if fg_stock2 is not None:
                                            fg_stock2.boxes_available += qty
                                            db.add(fg_stock2)
                elif invoice_items_data:
                    for item_data in invoice_items_data:
                        qty = item_data.get("boxes_sold") or 0
                        product_size_ml = item_data.get("product_size_ml")
                        packaging_size_name = item_data.get("packaging_size_name")
                        variety_val = item_data.get("variety") or "Standard/White"
                        
                        if qty > 0 and product_size_ml and packaging_size_name:
                            final_stock = db.query(FinalProductStock).filter(
                                FinalProductStock.factory_id == str(factory_id),
                                FinalProductStock.product_size_ml == product_size_ml,
                                sql_func.lower(FinalProductStock.variety) == variety_val.strip().lower(),
                                sql_func.lower(FinalProductStock.packaging_size_name) == packaging_size_name.strip().lower()
                            ).with_for_update().first()
                            if final_stock is not None:
                                final_stock.current_quantity += qty
                                db.add(final_stock)
                                
                            profile = db.query(PackagingProfile).filter(
                                PackagingProfile.factory_id == str(factory_id),
                                PackagingProfile.cup_size_ml == product_size_ml,
                                sql_func.lower(PackagingProfile.profile_name) == packaging_size_name.strip().lower()
                            ).first()
                            if profile:
                                fg_stock = db.query(FinishedGoodsStock).filter(
                                    FinishedGoodsStock.factory_id == str(factory_id),
                                    FinishedGoodsStock.packaging_profile_id == profile.id
                                ).with_for_update().first()
                                if fg_stock is not None:
                                    fg_stock.boxes_available += qty
                                    db.add(fg_stock)
            elif reason == "paid":
                # Do NOT alter the inventory stock metrics (keep it deducted since goods are sold)
                pass

            # 2. Hard delete dependent payment collections first to prevent FK constraint violations
            db.query(PaymentCollection).filter(
                (PaymentCollection.outstanding_bill_id == bill_id) |
                (PaymentCollection.outstanding_bill_id == ledger_bill.id)
            ).delete()
            db.flush()

            # 3. Hard delete the Outstanding Bill itself
            db.delete(ledger_bill)
            db.flush()

            # 4. Clean up corresponding order status if linked
            if order_id is not None:
                order = db.query(Order).filter(Order.factory_id == str(factory_id), Order.id == order_id).first()
                if order is not None:
                    order.balance_amount = Decimal("0.00")
                    order.pending_amount = Decimal("0.00")
                    order.payment_status = "Paid" if reason == "paid" else "Adjusted"
                    order.status = "adjusted_closed"

            # 5. Safely recalculate and sync remaining active customer dues
            if customer_id is not None:
                db.flush()
                active_due = db.query(sql_func.coalesce(sql_func.sum(OutstandingBill.balance_amount), 0)).filter(
                    OutstandingBill.factory_id == factory_id,
                    OutstandingBill.customer_id == customer_id,
                    OutstandingBill.status.in_(["active", "partial"])
                ).scalar() or Decimal("0.00")
                
                customer = db.query(Customer).filter(Customer.factory_id == str(factory_id), Customer.id == customer_id).first()
                if customer is not None:
                    customer.total_due = max(to_money(active_due), Decimal("0.00"))
                    customer.balance_amount = customer.total_due
                    customer.pending_balance = customer.total_due
                    customer.pending_dues = float(customer.total_due)

            # Log to Audit Trail
            from routers.operations import log_audit_trail
            log_audit_trail(
                db=db,
                factory_id=current_user.factory_id,
                user_id=current_user.id,
                user_role=current_user.role,
                action_type="DELETE",
                entity_name="Invoice",
                short_statement=f"Deleted Outstanding Bill/Invoice ID #{bill_id} ({reason})",
                event_type="payment"
            )
            
            db.commit()
        else:
            # Fallback legacy order adjustment if ledger bill was not found
            order = (
                db.query(Order)
                .options(joinedload(Order.customer))
                .filter(factory_id_filter(Order.factory_id, current_user.factory_id))
                .filter(Order.id == bill_id)
                .with_for_update()
                .first()
            )
            if order is None:
                db.rollback()
                return SalesOrderActionResponse(status="error", message="Outstanding bill not found", order_id=bill_id)

            # Clean any collections mapped to this legacy order
            db.query(PaymentCollection).filter(PaymentCollection.factory_id == factory_id, PaymentCollection.customer_id == order.customer_id).delete()
            db.flush()

            # Dynamic stock restoration for legacy fallback
            if reason == "mistake":
                # Delete daily sales for this customer on this date
                if order.customer_id is not None:
                    db.query(DailySale).filter(
                        DailySale.factory_id == str(factory_id),
                        DailySale.customer_id == order.customer_id,
                        DailySale.date == (order.order_date.date() if order.order_date else datetime.now(timezone.utc).date())
                    ).delete(synchronize_session=False)

                order_items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
                for item in order_items:
                    qty = item.boxes_sold or item.quantity or 0
                    if qty > 0:
                        if item.product_id is not None:
                            fg_stock = db.query(FinishedGoodsStock).filter(
                                FinishedGoodsStock.factory_id == str(factory_id),
                                FinishedGoodsStock.id == item.product_id
                            ).with_for_update().first()
                            if fg_stock is not None:
                                fg_stock.boxes_available += qty
                                db.add(fg_stock)
                        
                        if item.product_size_ml and item.packaging_size_name:
                            variety_val = item.variety or "Standard/White"
                            final_stock = db.query(FinalProductStock).filter(
                                FinalProductStock.factory_id == str(factory_id),
                                FinalProductStock.product_size_ml == item.product_size_ml,
                                sql_func.lower(FinalProductStock.variety) == variety_val.strip().lower(),
                                sql_func.lower(FinalProductStock.packaging_size_name) == item.packaging_size_name.strip().lower()
                            ).with_for_update().first()
                            if final_stock is not None:
                                final_stock.current_quantity += qty
                                db.add(final_stock)

                            profile = db.query(PackagingProfile).filter(
                                PackagingProfile.factory_id == str(factory_id),
                                PackagingProfile.cup_size_ml == item.product_size_ml,
                                sql_func.lower(PackagingProfile.profile_name) == item.packaging_size_name.strip().lower()
                            ).first()
                            if profile:
                                fg_stock2 = db.query(FinishedGoodsStock).filter(
                                    FinishedGoodsStock.factory_id == str(factory_id),
                                    FinishedGoodsStock.packaging_profile_id == profile.id
                                ).with_for_update().first()
                                if fg_stock2 is not None:
                                    fg_stock2.boxes_available += qty
                                    db.add(fg_stock2)

            previous_balance = to_money(order.balance_amount)
            order.balance_amount = Decimal("0.00")
            order.pending_amount = Decimal("0.00")
            order.payment_status = "Paid" if reason == "paid" else "Adjusted"
            order.status = "adjusted_closed"

            if order.customer is not None:
                remaining_customer_balance = max(
                    to_money(order.customer.total_due or order.customer.balance_amount or 0) - previous_balance,
                    Decimal("0.00"),
                )
                order.customer.total_due = remaining_customer_balance
                order.customer.balance_amount = remaining_customer_balance
                order.customer.pending_balance = remaining_customer_balance
                order.customer.pending_dues = float(remaining_customer_balance)

            # Log to Audit Trail
            from routers.operations import log_audit_trail
            log_audit_trail(
                db=db,
                factory_id=current_user.factory_id,
                user_id=current_user.id,
                user_role=current_user.role,
                action_type="DELETE",
                entity_name="Invoice",
                short_statement=f"Deleted Outstanding Bill/Invoice ID #{bill_id} ({reason})",
                event_type="payment"
            )
            
            db.commit()
            return_order_id = order.id

        background_tasks.add_task(
            sync_data_to_n8n_bg,
            factory_id=str(current_user.factory_id),
            sync_type="sales",
            action="delete",
            data={"bill_id": bill_id, "order_id": return_order_id}
        )

        return SalesOrderActionResponse(
            status="success",
            message="Bill processed and cleared successfully.",
            order_id=return_order_id
        )

    except Exception as exc:
        db.rollback()
        logger.exception("Outstanding bill hard-delete operation failed; attempting raw SQL force-deletion: bill_id=%s", bill_id)
        try:
            # Force hard-deletion and state reset via direct raw SQL updates to bypass any complex ORM constraint blocks
            factory_id_val = int(current_user.factory_id)
            
            # Fetch customer_id and order_id to update balances and handle stock if reason == mistake
            cust_id_res = db.execute(
                text("SELECT customer_id, order_id FROM outstanding_bills WHERE factory_id = :fid AND id = :bid"),
                {"fid": factory_id_val, "bid": bill_id}
            ).first()
            
            # If reason == mistake, reverse stock via raw SQL
            if reason == "mistake":
                # Find sale ids and delete daily sales via raw SQL
                db.execute(
                    text("DELETE FROM daily_sales WHERE customer_id = :cid AND date = (SELECT bill_date FROM outstanding_bills WHERE id = :bid)"),
                    {"cid": cust_id_res[0] if cust_id_res else -1, "bid": bill_id}
                )
                if cust_id_res and cust_id_res[1] is not None:
                    oid = cust_id_res[1]
                    items_res = db.execute(
                        text("SELECT product_id, quantity, boxes_sold, product_size_ml, variety, packaging_size_name FROM order_items WHERE order_id = :oid"),
                        {"oid": oid}
                    ).all()
                    for item in items_res:
                        qty = item[2] or item[1] or 0
                        if qty > 0:
                            if item[0] is not None:
                                db.execute(
                                    text("UPDATE finished_goods_stock SET boxes_available = boxes_available + :qty WHERE factory_id = :fid AND id = :pid"),
                                    {"qty": qty, "fid": str(factory_id_val), "pid": item[0]}
                                )
                            if item[3] is not None and item[5] is not None:
                                db.execute(
                                    text("UPDATE final_product_stock SET current_quantity = current_quantity + :qty WHERE factory_id = :fid AND product_size_ml = :size AND LOWER(variety) = LOWER(:variety) AND LOWER(packaging_size_name) = LOWER(:pack)"),
                                    {"qty": qty, "fid": str(factory_id_val), "size": item[3], "variety": item[4] or "Standard/White", "pack": item[5]}
                                )
                                # Also update finished goods stock matching that profile
                                db.execute(
                                    text("UPDATE finished_goods_stock SET boxes_available = boxes_available + :qty WHERE factory_id = :fid AND packaging_profile_id = (SELECT id FROM packaging_profiles WHERE factory_id = :fid AND cup_size_ml = :size AND LOWER(profile_name) = LOWER(:pack))"),
                                    {"qty": qty, "fid": str(factory_id_val), "size": item[3], "pack": item[5]}
                                )

            db.execute(
                text("DELETE FROM payment_collections WHERE outstanding_bill_id = :bid"),
                {"bid": bill_id}
            )
            db.execute(
                text("DELETE FROM outstanding_bills WHERE factory_id = :fid AND id = :bid"),
                {"fid": factory_id_val, "bid": bill_id}
            )
            
            payment_status_val = "Paid" if reason == "paid" else "Adjusted"
            db.execute(
                text("UPDATE orders SET balance_amount = 0, pending_amount = 0, payment_status = :pstatus, status = 'adjusted_closed' WHERE factory_id = :fid AND (id = :bid OR id = :oid)"),
                {"fid": factory_id_val, "bid": bill_id, "oid": cust_id_res[1] if cust_id_res and cust_id_res[1] is not None else -1, "pstatus": payment_status_val}
            )
            
            # Recalculate customer due
            if cust_id_res and cust_id_res[0] is not None:
                cid = cust_id_res[0]
                active_due_res = db.execute(
                    text("SELECT COALESCE(SUM(balance_amount), 0) FROM outstanding_bills WHERE factory_id = :fid AND customer_id = :cid AND status IN ('active', 'partial')"),
                    {"fid": factory_id_val, "cid": cid}
                ).scalar() or Decimal("0.00")
                
                db.execute(
                    text("UPDATE customers SET total_due = :due, balance_amount = :due, pending_balance = :due, pending_dues = :due_f WHERE factory_id = :fid AND id = :cid"),
                    {"due": active_due_res, "due_f": float(active_due_res), "fid": str(factory_id_val), "cid": cid}
                )
                
            db.commit()

            background_tasks.add_task(
                sync_data_to_n8n_bg,
                factory_id=str(current_user.factory_id),
                sync_type="sales",
                action="delete",
                data={"bill_id": bill_id, "order_id": return_order_id}
            )

            return SalesOrderActionResponse(
                status="success",
                message="Bill processed and cleared successfully.",
                order_id=return_order_id
            )

        except Exception as inner_exc:
            db.rollback()
            logger.exception("Force SQL adjustment failed: %s", inner_exc)
            return SalesOrderActionResponse(
                status="error",
                message=f"Outstanding bill deletion failed completely: {inner_exc}",
                order_id=bill_id
            )





@router.get("/customers/{customer_id}/balance", response_model=CustomerBalanceResponse)
def get_customer_balance(
    customer_id: int,
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    customer = (
        db.query(Customer)
        .filter(factory_id_filter(Customer.factory_id, current_user.factory_id))
        .filter(Customer.id == customer_id)
        .first()
    )
    if customer is None:
        return CustomerBalanceResponse(customer_id=customer_id, customer_name="", previous_due=0, total_due=0)
    return CustomerBalanceResponse(
        customer_id=customer.id,
        customer_name=customer.name,
        previous_due=float(customer.previous_due or 0),
        total_due=float(customer.total_due or 0),
    )


@router.post("/v1/customers/upload-seed", response_model=None)
def upload_customers_seed(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    import pandas as pd
    import json
    import csv
    from io import StringIO, BytesIO
    
    factory_id = current_user.factory_id
    filename = file.filename or "upload.csv"
    
    try:
        contents = file.file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file contents: {exc}"
        )
        
    records = []
    
    # 1. Tabular data extraction with fallback support
    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(BytesIO(contents))
            records = df.to_dict(orient="records")
        else:
            try:
                df = pd.read_csv(BytesIO(contents))
                records = df.to_dict(orient="records")
            except Exception:
                text_data = contents.decode("utf-8", errors="ignore")
                reader = csv.DictReader(StringIO(text_data))
                records = list(reader)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Spreadsheet parser extraction failed: {exc}"
        )

    count = 0
    skipped = 0
    
    for row in records:
        if row is None or not isinstance(row, dict):
            continue
            
        normalized_row = {str(k).strip().lower(): str(v).strip() for k, v in row.items() if k is not None}
        
        # Match name
        name = ""
        for name_key in ["name", "customer name", "customer_name", "full name", "fullname", "buyer"]:
            if name_key in normalized_row:
                name = normalized_row[name_key]
                break
                
        # Match phone_number
        phone_number = ""
        for phone_key in ["phone", "phone number", "phone_number", "mobile", "mobile number", "contact", "contact_number"]:
            if phone_key in normalized_row:
                phone_number = normalized_row[phone_key]
                break
                
        if not phone_number or not name:
            skipped += 1
            continue
            
        # Clean phone digits
        cleaned_phone = "".join(filter(str.isdigit, phone_number))
        if len(cleaned_phone) > 10:
            cleaned_phone = cleaned_phone[-10:]
            
        if not cleaned_phone:
            skipped += 1
            continue
            
        # Extract remaining fields as details
        metadata = {}
        for k, v in row.items():
            if k is None:
                continue
            k_clean = str(k).strip()
            if k_clean.lower() not in ["name", "customer name", "customer_name", "full name", "fullname", "buyer", "phone", "phone number", "phone_number", "mobile", "mobile number", "contact", "contact_number"]:
                metadata[k_clean] = str(v).strip()
                
        place = metadata.get("place", metadata.get("address", ""))
        
        # Multi-Tenancy Guardrail check matching context factory_id
        existing = (
            db.query(Customer)
            .filter(Customer.factory_id == str(factory_id))
            .filter((Customer.phone_number == cleaned_phone) | (Customer.phone == cleaned_phone))
            .first()
        )
        if existing is not None:
            skipped += 1
            continue
            
        new_customer = Customer(
            factory_id=str(factory_id),
            name=name,
            phone_number=cleaned_phone,
            phone=cleaned_phone,
            contact_number=cleaned_phone,
            place=place,
            address=place,
            previous_due=Decimal("0.00"),
            total_due=Decimal("0.00"),
            pending_balance=Decimal("0.00"),
            balance_amount=Decimal("0.00"),
            pending_dues=0.0
        )
        db.add(new_customer)
        count += 1

    if count > 0:
        try:
            db.commit()
            background_tasks.add_task(
                log_activity,
                db,
                int(current_user.factory_id),
                current_user.id,
                current_user.full_name or current_user.username,
                current_user.role,
                "CUSTOMER_SEED_UPLOADED",
                f"Uploaded customer seed with {count} imported and {skipped} skipped rows",
                "customer",
                None,
                {"filename": filename, "imported_count": count, "skipped_count": skipped},
            )
        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database transaction commit failed: {exc}"
            )
            
    return {
        "status": "success",
        "message": f"Successfully imported {count} customers. Skipped {skipped} duplicates or invalid rows.",
        "imported_count": count,
        "skipped_count": skipped
    }


class LedgerAdjustmentCreate(BaseModel):
    adjustment_type: str = Field(..., pattern="^(add_balance|reduce_balance)$")
    amount: Decimal = Field(..., gt=0)
    reason: str = Field(..., min_length=1, max_length=1000)
    linked_bill_id: int | None = None

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Reason is required")
        return cleaned


class LedgerAdjustmentResponse(BaseModel):
    adjustment_id: int
    previous_outstanding: Decimal
    adjustment_amount: Decimal
    new_outstanding: Decimal
    adjustment_type: str
    reason: str


class OpeningOutstandingCreate(BaseModel):
    amount: Decimal = Field(..., gt=0)
    opening_date: date | None = Field(default=None, alias="date")
    reason: str = Field(..., min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Reason is required")
        return cleaned


class OpeningOutstandingUpdate(BaseModel):
    new_amount: Decimal = Field(..., ge=0)
    reason: str = Field(..., min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def clean_update_reason(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Reason is required")
        return cleaned


class OpeningOutstandingResponse(BaseModel):
    id: int
    previous_outstanding: Decimal
    new_outstanding: Decimal
    difference: Decimal
    customer_total_outstanding: Decimal
    stock_impact: bool = False


@router.post("/customers/{customer_id}/opening-outstanding", response_model=OpeningOutstandingResponse)
def create_opening_outstanding(
    customer_id: int,
    payload: OpeningOutstandingCreate,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    customer = db.query(Customer).filter(
        factory_id_filter(Customer.factory_id, current_user.factory_id),
        Customer.id == customer_id,
    ).with_for_update().first()
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    previous = active_customer_outstanding(db, current_user.factory_id, customer.id)
    bill = create_outstanding_bill(
        db,
        factory_id=current_user.factory_id,
        customer_id=customer.id,
        source_type="opening_outstanding",
        tracking_number=f"OPEN-{customer.id}-{int(datetime.now(timezone.utc).timestamp())}",
        bill_date=payload.opening_date or datetime.now(timezone.utc).date(),
        bill_amount=payload.amount,
        note=payload.reason,
        created_by_user_id=current_user.id,
    )
    customer.previous_due = to_money(customer.previous_due) + to_money(payload.amount)
    customer.opening_outstanding_note = payload.reason
    customer.opening_outstanding_date = payload.opening_date or datetime.now(timezone.utc).date()
    new_total = sync_customer_balance_from_bills(db, current_user.factory_id, customer)
    log_activity(
        db, int(current_user.factory_id), current_user.id,
        current_user.full_name or current_user.username, current_user.role,
        "OPENING_OUTSTANDING_CREATED", f"Opening outstanding added for {customer.name}",
        "opening_outstanding", bill.id,
        {"old_balance": float(previous), "amount": float(payload.amount), "new_balance": float(new_total), "reason": payload.reason},
    )
    db.commit()
    return OpeningOutstandingResponse(
        id=bill.id, previous_outstanding=previous, new_outstanding=payload.amount,
        difference=payload.amount, customer_total_outstanding=new_total,
    )


@router.patch("/customers/{customer_id}/opening-outstanding/{opening_id}", response_model=OpeningOutstandingResponse)
def update_opening_outstanding(
    customer_id: int,
    opening_id: int,
    payload: OpeningOutstandingUpdate,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    customer = db.query(Customer).filter(
        factory_id_filter(Customer.factory_id, current_user.factory_id), Customer.id == customer_id
    ).with_for_update().first()
    bill = db.query(OutstandingBill).filter(
        OutstandingBill.factory_id == int(current_user.factory_id),
        OutstandingBill.customer_id == customer_id,
        OutstandingBill.id == opening_id,
        OutstandingBill.source_type.in_(("opening_balance", "opening_outstanding")),
        OutstandingBill.deleted_at.is_(None),
    ).with_for_update().first()
    if customer is None or bill is None:
        raise HTTPException(status_code=404, detail="Opening outstanding not found")
    paid = to_money(bill.amount_paid)
    if payload.new_amount < paid:
        raise HTTPException(status_code=400, detail="Opening outstanding cannot be lower than amount already paid")
    old_original = to_money(bill.bill_amount)
    old_total = active_customer_outstanding(db, current_user.factory_id, customer.id)
    bill.bill_amount = to_money(payload.new_amount)
    bill.balance_amount = to_money(payload.new_amount) - paid
    bill.status = "closed" if bill.balance_amount <= 0 else ("partial" if paid > 0 else "active")
    bill.note = payload.reason
    bill.updated_by_user_id = current_user.id
    customer.previous_due = max(Decimal("0.00"), to_money(customer.previous_due) + (to_money(payload.new_amount) - old_original))
    new_total = sync_customer_balance_from_bills(db, current_user.factory_id, customer)
    log_activity(
        db, int(current_user.factory_id), current_user.id,
        current_user.full_name or current_user.username, current_user.role,
        "OPENING_OUTSTANDING_UPDATED", f"Opening outstanding updated for {customer.name}",
        "opening_outstanding", bill.id,
        {"old_value": float(old_original), "new_value": float(payload.new_amount), "old_balance": float(old_total), "new_balance": float(new_total), "reason": payload.reason},
    )
    db.commit()
    return OpeningOutstandingResponse(
        id=bill.id, previous_outstanding=old_original, new_outstanding=payload.new_amount,
        difference=to_money(payload.new_amount) - old_original, customer_total_outstanding=new_total,
    )


@router.delete("/customers/{customer_id}/opening-outstanding/{opening_id}", response_model=OpeningOutstandingResponse)
def delete_opening_outstanding(
    customer_id: int,
    opening_id: int,
    reason: str = Query(..., min_length=1),
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    customer = db.query(Customer).filter(
        factory_id_filter(Customer.factory_id, current_user.factory_id), Customer.id == customer_id
    ).with_for_update().first()
    bill = db.query(OutstandingBill).filter(
        OutstandingBill.factory_id == int(current_user.factory_id),
        OutstandingBill.customer_id == customer_id,
        OutstandingBill.id == opening_id,
        OutstandingBill.source_type.in_(("opening_balance", "opening_outstanding")),
        OutstandingBill.deleted_at.is_(None),
    ).with_for_update().first()
    if customer is None or bill is None:
        raise HTTPException(status_code=404, detail="Opening outstanding not found")
    if to_money(bill.amount_paid) > 0:
        raise HTTPException(status_code=400, detail="Paid opening outstanding cannot be deleted; reduce it instead")
    old_total = active_customer_outstanding(db, current_user.factory_id, customer.id)
    removed = to_money(bill.balance_amount)
    bill.deleted_at = datetime.now(timezone.utc)
    bill.deleted_by_user_id = current_user.id
    bill.deletion_reason = reason.strip()
    bill.status = "cancelled"
    customer.previous_due = max(Decimal("0.00"), to_money(customer.previous_due) - to_money(bill.bill_amount))
    new_total = sync_customer_balance_from_bills(db, current_user.factory_id, customer)
    log_activity(
        db, int(current_user.factory_id), current_user.id,
        current_user.full_name or current_user.username, current_user.role,
        "OPENING_OUTSTANDING_DELETED", f"Opening outstanding deleted for {customer.name}",
        "opening_outstanding", bill.id,
        {"removed": float(removed), "old_balance": float(old_total), "new_balance": float(new_total), "reason": reason.strip(), "stock_impact": False},
    )
    db.commit()
    return OpeningOutstandingResponse(
        id=bill.id, previous_outstanding=removed, new_outstanding=Decimal("0.00"),
        difference=-removed, customer_total_outstanding=new_total,
    )


@router.get("/customers/{customer_id}/ledger")
def get_customer_ledger(
    customer_id: int,
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    customer = db.query(Customer).filter(
        factory_id_filter(Customer.factory_id, current_user.factory_id), Customer.id == customer_id
    ).first()
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    bills = db.query(OutstandingBill).options(joinedload(OutstandingBill.payments)).filter(
        OutstandingBill.factory_id == int(current_user.factory_id),
        OutstandingBill.customer_id == customer_id,
    ).order_by(OutstandingBill.created_at.asc(), OutstandingBill.id.asc()).all()
    entries = []
    running = Decimal("0.00")
    for bill in bills:
        source = "opening_outstanding" if bill.source_type in ("opening_balance", "opening_outstanding") else bill.source_type
        running += to_money(bill.bill_amount)
        entries.append({
            "date_time": bill.created_at, "type": source, "debit": to_money(bill.bill_amount),
            "credit": Decimal("0.00"), "amount": to_money(bill.bill_amount), "running_balance": to_money(running),
            "source": bill.tracking_number, "created_by": getattr(bill.created_by, "username", None),
            "notes": bill.note, "stock_impact": source == "invoice",
        })
        for payment in sorted(bill.payments or [], key=lambda item: (item.payment_date, item.id)):
            running -= to_money(payment.amount_allocated)
            entries.append({
                "date_time": payment.created_at, "type": "payment_allocation", "debit": Decimal("0.00"),
                "credit": to_money(payment.amount_allocated), "amount": to_money(payment.amount_allocated),
                "running_balance": to_money(running), "source": bill.tracking_number,
                "created_by": payment.received_by_name, "notes": f"Allocated to {source}", "stock_impact": False,
            })
        if bill.deleted_at is not None:
            running -= to_money(bill.balance_amount)
            entries.append({
                "date_time": bill.deleted_at, "type": "opening_outstanding_deleted",
                "debit": Decimal("0.00"), "credit": to_money(bill.balance_amount),
                "amount": to_money(bill.balance_amount), "running_balance": to_money(running),
                "source": bill.tracking_number, "created_by": None,
                "notes": bill.deletion_reason, "stock_impact": False,
            })
    from models import CustomerLedgerAdjustment
    adjustments = db.query(CustomerLedgerAdjustment).filter(
        CustomerLedgerAdjustment.factory_id == int(current_user.factory_id),
        CustomerLedgerAdjustment.customer_id == customer_id,
    ).order_by(CustomerLedgerAdjustment.created_at.asc(), CustomerLedgerAdjustment.id.asc()).all()
    for adjustment in adjustments:
        if adjustment.adjustment_type == "add_balance" and adjustment.linked_bill_id is not None:
            continue
        entries.append({
            "date_time": adjustment.created_at,
            "type": adjustment.adjustment_type,
            "debit": to_money(adjustment.amount) if adjustment.adjustment_type == "add_balance" else Decimal("0.00"),
            "credit": to_money(adjustment.amount) if adjustment.adjustment_type == "reduce_balance" else Decimal("0.00"),
            "amount": to_money(adjustment.amount),
            "running_balance": None,
            "source": f"ADJ-{adjustment.id}",
            "created_by": adjustment.created_by_name,
            "notes": adjustment.reason,
            "stock_impact": False,
        })
    entries.sort(key=lambda entry: (entry["date_time"] or datetime.min.replace(tzinfo=timezone.utc), entry["source"]))
    running = Decimal("0.00")
    for entry in entries:
        running += to_money(entry["debit"]) - to_money(entry["credit"])
        entry["running_balance"] = max(Decimal("0.00"), to_money(running))
    return {"customer_id": customer.id, "customer_name": customer.name, "current_balance": active_customer_outstanding(db, current_user.factory_id, customer.id), "entries": entries}


@router.post("/customers/{customer_id}/ledger-adjustments", response_model=LedgerAdjustmentResponse)
def create_customer_adjustment(
    customer_id: int,
    payload: LedgerAdjustmentCreate,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    from models import CustomerLedgerAdjustment

    customer = (
        db.query(Customer)
        .filter(factory_id_filter(Customer.factory_id, current_user.factory_id))
        .filter(Customer.id == customer_id)
        .with_for_update()
        .first()
    )
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    try:
        previous_outstanding = active_customer_outstanding(db, current_user.factory_id, customer.id)
        linked_bill = None
        if payload.linked_bill_id is not None:
            linked_bill = (
                db.query(OutstandingBill)
                .filter(OutstandingBill.id == payload.linked_bill_id)
                .filter(OutstandingBill.factory_id == int(current_user.factory_id))
                .filter(OutstandingBill.customer_id == customer.id)
                .first()
            )
            if linked_bill is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked bill not found")

        adjustment = CustomerLedgerAdjustment(
            customer_id=customer.id,
            factory_id=current_user.factory_id,
            adjustment_type=payload.adjustment_type,
            amount=payload.amount,
            reason=payload.reason,
            linked_bill_id=linked_bill.id if linked_bill is not None else None,
            created_by_user_id=current_user.id,
            created_by_name=current_user.full_name or current_user.username,
        )
        db.add(adjustment)
        db.flush()

        if payload.adjustment_type == "add_balance":
            manual_bill = create_outstanding_bill(
                db,
                factory_id=current_user.factory_id,
                customer_id=customer.id,
                source_type="manual_adjustment",
                tracking_number=f"ADJ-{adjustment.id}",
                bill_date=datetime.now(timezone.utc).date(),
                bill_amount=payload.amount,
                amount_paid=Decimal("0.00"),
                note=payload.reason,
                created_by_user_id=current_user.id,
            )
            adjustment.linked_bill_id = manual_bill.id if manual_bill is not None else None
        else:
            if payload.amount > previous_outstanding:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Reduction amount cannot exceed current outstanding",
                )
            remaining = to_money(payload.amount)
            bills_query = (
                db.query(OutstandingBill)
                .filter(OutstandingBill.factory_id == int(current_user.factory_id))
                .filter(OutstandingBill.customer_id == customer.id)
                .filter(OutstandingBill.balance_amount > 0)
                .filter(OutstandingBill.status.in_(("active", "partial")))
                .with_for_update()
            )
            if linked_bill is not None:
                bills_query = bills_query.filter(OutstandingBill.id == linked_bill.id)
            bills = bills_query.order_by(OutstandingBill.bill_date.asc(), OutstandingBill.id.asc()).all()
            for bill in bills:
                if remaining <= 0:
                    break
                reduction = min(remaining, to_money(bill.balance_amount))
                bill.balance_amount = to_money(bill.balance_amount) - reduction
                bill.status = "closed" if bill.balance_amount <= 0 else "partial"
                remaining -= reduction
            if remaining > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Reduction amount exceeds the selected bill balance",
                )

        new_outstanding = sync_customer_balance_from_bills(db, current_user.factory_id, customer)
        log_activity(
            db,
            int(current_user.factory_id),
            current_user.id,
            current_user.full_name or current_user.username,
            current_user.role,
            "LEDGER_ADJUSTMENT_CREATED",
            f"Recorded {payload.adjustment_type} adjustment of Rs {payload.amount:,.2f} for {customer.name}",
            "customer",
            customer.id,
            {
                "customer_id": customer.id,
                "adjustment_id": adjustment.id,
                "adjustment_type": payload.adjustment_type,
                "amount": float(payload.amount),
                "reason": payload.reason,
                "previous_outstanding": float(previous_outstanding),
                "new_outstanding": float(new_outstanding),
            }
        )
        db.commit()
        return LedgerAdjustmentResponse(
            adjustment_id=adjustment.id,
            previous_outstanding=previous_outstanding,
            adjustment_amount=payload.amount,
            new_outstanding=new_outstanding,
            adjustment_type=payload.adjustment_type,
            reason=payload.reason,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("Failed to create customer ledger adjustment")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record customer ledger adjustment",
        )

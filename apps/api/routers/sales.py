from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
import logging
import os

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import String, cast, or_, func as sql_func, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload
from starlette.datastructures import UploadFile

from dependencies import OWNER_ROLES, SALES_ROLES, check_permissions
from db import get_db
from models import BoxStock, Customer, DailySale, Factory, FactoryAutomationSheet, FinalProductStock, FinishedGoodsStock, InvoiceDocument, Order, OrderItem, Payment, RecycledInvoice, User, ActivityLog, OutstandingBill, PaymentCollection, PackagingProfile
from routers.payments import customer_phone, send_n8n_whatsapp_event
from schemas import CustomerCreate, CustomerResponse, DailySaleCreate, DailySaleResponse
from services.accounting import create_outstanding_bill, sync_customer_balance_from_bills
from services.invoice_pdf import build_invoice_pdf_bytes
from services.n8n_sync import sync_data_to_n8n_bg


router = APIRouter()
MONEY_QUANT = Decimal("0.01")
logger = logging.getLogger(__name__)


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
    # Legacy fallback — uses the shared counter
    return "current_invoice_counter"


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
        invoice_counter = getattr(factory, attr, None) or factory.current_invoice_counter or factory.initial_invoice_number or 1
        setattr(factory, attr, invoice_counter + 1)
        # Keep legacy counter in sync for backward compatibility
        if attr != "current_invoice_counter":
            factory.current_invoice_counter = (factory.current_invoice_counter or 1)

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
    counter = getattr(factory, attr, None) or factory.current_invoice_counter or factory.initial_invoice_number or 1
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


def sync_next_invoice_setting(factory: Factory | None, used_invoice_number: str | None) -> None:
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
    factory.current_invoice_counter = max(next_counter, factory.current_invoice_counter or 0)




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
    place: str
    phone_number: str
    gst_number: str | None = None
    company_name: str | None = None


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
    payments: list[BillPaymentLogResponse] = []


class OutstandingCustomerBillsResponse(BaseModel):
    customer_id: int
    customer_name: str
    customer_phone: str
    place: str = ""
    total_bill_amount: Decimal
    total_paid: Decimal
    current_pending_balance: Decimal
    bills: list[OutstandingBillResponse]


class SalesOutstandingResponse(BaseModel):
    grand_total_outstanding: Decimal
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
        print("Owner sale alert email skipped: SMTP_USER, SMTP_PASSWORD, SMTP_FROM, or SMTP_HOST is not configured")
        return

    attachment = UploadFile(file=BytesIO(pdf_bytes), filename=filename)
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

    try:
        factory = db.query(Factory).filter(Factory.id == current_user.factory_id).with_for_update().first()
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

        previous_remaining_balance = to_money(customer.total_due or customer.balance_amount or 0)
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

        for item in payload.items:
            require_sold_quantity(item.boxes_sold, item.loose_packets_sold)
            stock = (
                db.query(FinalProductStock)
                .filter(factory_id_filter(FinalProductStock.factory_id, factory_id))
                .filter(FinalProductStock.product_size_ml == item.product_size_ml)
                .filter(sql_func.lower(FinalProductStock.variety) == item.variety.lower())
                .filter(sql_func.lower(FinalProductStock.packaging_size_name) == item.packaging_size_name.lower())
                .with_for_update()
                .first()
            )
            is_custom_invoice_item = stock is None and item.product_id is None
            if stock is None and not is_custom_invoice_item:
                box_stock = (
                    db.query(BoxStock)
                    .filter(factory_id_filter(BoxStock.factory_id, factory_id))
                    .filter(sql_func.lower(BoxStock.packaging_size_name) == item.packaging_size_name.lower())
                    .with_for_update()
                    .first()
                )
                if box_stock is None:
                    box_stock = BoxStock(
                        factory_id=factory_id,
                        packaging_size_name=item.packaging_size_name.strip(),
                        total_boxes=0,
                    )
                    db.add(box_stock)
                    db.flush()

                stock = FinalProductStock(
                    factory_id=factory_id,
                    product_size_ml=item.product_size_ml,
                    variety=item.variety.strip(),
                    packaging_size_name=item.packaging_size_name.strip(),
                    current_quantity=0,
                    total_boxes=0,
                    loose_packets=0,
                    packets_per_box_limit=1,
                )
                db.add(stock)
                db.flush()

            if stock is not None:
                # Resolve exact live dynamic stock balance
                from routers.inventory import calculate_live_sku_stock
                live_boxes, live_loose = calculate_live_sku_stock(
                    db=db,
                    factory_id=str(factory_id),
                    product_size_ml=item.product_size_ml,
                    variety=item.variety,
                    packaging_size_name=item.packaging_size_name,
                    onboarding_boxes=stock.total_boxes or 0,
                    onboarding_loose=stock.loose_packets or 0,
                    packets_per_box_limit=stock.packets_per_box_limit or 1000
                )
                available_packets = live_boxes * stock.packets_per_box_limit + live_loose
                sold_packets = item.boxes_sold * stock.packets_per_box_limit + item.loose_packets_sold
                if available_packets < sold_packets:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Insufficient final product stock for {item.product_size_ml}ml {item.variety} {item.packaging_size_name}",
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

        net_outstanding_balance = to_money(previous_remaining_balance + current_bill_amount)
        customer_due_after_payment = to_money(net_outstanding_balance - to_money(payload.amount_paid))
        if customer_due_after_payment < 0:
            customer_due_after_payment = Decimal("0.00")

        if sale_ids:
            first_sale = db.query(DailySale).filter(DailySale.id == sale_ids[0]).first()
            if first_sale is not None:
                initial_payment = to_money(payload.amount_paid)
                first_sale.amount_paid = initial_payment
                first_sale.initial_payment = initial_payment
                if initial_payment > 0:
                    db.add(
                        Payment(
                            factory_id=factory_id,
                            customer_phone=normalized_customer_phone,
                            sale_id=first_sale.id,
                            amount_paid=initial_payment,
                            payment_mode="Cash",
                            date=payload.date,
                        )
                    )

        customer.previous_due = previous_remaining_balance
        customer.total_due = customer_due_after_payment
        customer.balance_amount = customer_due_after_payment
        customer.pending_balance = customer_due_after_payment
        customer.pending_dues = float(customer_due_after_payment)

        # Recalculate dynamic live stock balance and sync caches for all sold SKUs
        from routers.inventory import recalculate_and_sync_sku_stock
        for item in stock_sync_items:
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
                "amount_paid": to_money(payload.amount_paid),
                "previous_due": previous_remaining_balance,
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
        sync_next_invoice_setting(factory, invoice_num)
        sync_customer_balance_from_bills(db, current_user.factory_id, customer)
        db.commit()

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
    except Exception as exc:
        db.rollback()
        logger.exception("Sale invoice creation failed due to exception:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sale invoice failed and was rolled back: {exc}",
        ) from exc


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
            print(f"Owner sale alert email skipped: no owner email found for factory_id={factory_id}")

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
    )
    phone_number = payload.phone_number.strip()
    try:
        with db.begin():
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
                phone_number=phone_number,
                place=payload.place.strip(),
                gst_number=payload.gst_number.strip() if payload.gst_number else None,
                firm_name=payload.company_name.strip() if payload.company_name else None,
                address=payload.address or payload.place.strip(),
                phone=phone_number,
                contact_number=phone_number,
                previous_due=opening_due,
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
                    source_type="opening_balance",
                    tracking_number=f"OPEN-{customer.id}",
                    bill_date=datetime.now(timezone.utc).date(),
                    bill_amount=opening_due,
                    amount_paid=Decimal("0.00"),
                )
                sync_customer_balance_from_bills(db, current_user.factory_id, customer)
        db.refresh(customer)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Customer creation failed and rolled back")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Customer creation failed: {exc}") from exc
    return customer


class CustomerUpdatePayload(BaseModel):
    name: str | None = None
    phone_number: str | None = None
    place: str | None = None
    gst_number: str | None = None
    company_name: str | None = None


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

    if payload.name is not None:
        customer.name = payload.name.strip()
    if payload.phone_number is not None:
        new_phone = payload.phone_number.strip()
        if new_phone != (customer.phone_number or ""):
            existing = (
                db.query(Customer)
                .filter(factory_id_filter(Customer.factory_id, current_user.factory_id))
                .filter(Customer.phone_number == new_phone)
                .filter(Customer.id != customer_id)
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
    if payload.gst_number is not None:
        customer.gst_number = payload.gst_number.strip() or None
    if payload.company_name is not None:
        customer.firm_name = payload.company_name.strip() or None

    db.commit()
    db.refresh(customer)
    return CustomerSearchResponse(
        id=customer.id,
        name=customer.name,
        place=customer.place or customer.address or "",
        phone_number=customer.phone_number or customer.phone or customer.contact_number or "",
        gst_number=customer.gst_number,
        company_name=customer.firm_name,
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
    return [
        CustomerSearchResponse(
            id=customer.id,
            name=customer.name,
            place=customer.place or customer.address or "",
            phone_number=customer.phone_number or customer.phone or customer.contact_number or "",
            gst_number=customer.gst_number,
            company_name=customer.firm_name,
        )
        for customer in customers
    ]


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

        invoice_summaries.append(
            InvoiceDocumentSummary(
                id=invoice.id,
                invoice_number=invoice.invoice_number,
                invoice_date=invoice.invoice_date.isoformat(),
                customer_id=invoice.customer_id,
                customer_name=invoice.customer_name,
                customer_phone=invoice.customer_phone,
                payment_method=invoice.payment_method,
                bill_total=to_money(invoice.bill_total),
                amount_paid=live_paid,
                customer_total_due=live_due,
                status=invoice.status,
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

    bill = db.query(OutstandingBill).filter(OutstandingBill.invoice_document_id == invoice.id).first()
    payload = invoice.payload_json or {}
    if "invoice" in payload:
        if bill:
            payload["invoice"]["amount_paid"] = float(bill.amount_paid)
            payload["invoice"]["customer_total_due"] = float(bill.balance_amount)
        else:
            payload["invoice"]["amount_paid"] = float(invoice.amount_paid)
            payload["invoice"]["customer_total_due"] = float(invoice.customer_total_due)
        payload["id"] = invoice.id

    pdf_bytes = build_invoice_pdf_bytes(payload)
    invoice.pdf_generated_count = (invoice.pdf_generated_count or 0) + 1
    invoice.last_pdf_generated_at = datetime.now(timezone.utc)
    db.commit()

    filename = f"invoice_{factory_id}_{invoice.invoice_number}.pdf".replace("/", "_").replace("\\", "_")
    disposition = "inline" if inline else "attachment"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.get("/pending", response_model=list[PendingSaleResponse])
def list_pending_sales(
    current_user: User = Depends(check_permissions(["Owner"])),
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
        print(f"Error in pending sales: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


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
        print(f"Error approving sales order {order_id}: {exc}")
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Order approval failed: {exc}") from exc

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
        print(f"Error rejecting sales order {order_id}: {exc}")
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Order rejection failed: {exc}") from exc


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
        .order_by(OutstandingBill.customer_id.asc(), OutstandingBill.bill_date.asc(), OutstandingBill.id.asc())
        .all()
    )
    if ledger_bills:
        grouped: dict[int, OutstandingCustomerBillsResponse] = {}
        grand_total = Decimal("0.00")
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
                    bills=[],
                )
            row = grouped[customer_id]
            row.total_bill_amount = to_money(row.total_bill_amount + to_money(bill.bill_amount))
            row.total_paid = to_money(row.total_paid + to_money(bill.amount_paid))
            row.current_pending_balance = to_money(row.current_pending_balance + to_money(bill.balance_amount))
            row.bills.append(
                OutstandingBillResponse(
                    bill_id=bill.id,
                    order_id=bill.order_id,
                    order_date=bill.bill_date.isoformat() if bill.bill_date else "",
                    bill_amount=to_money(bill.bill_amount),
                    amount_paid=to_money(bill.amount_paid),
                    remaining_balance=to_money(bill.balance_amount),
                    status=bill.status,
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
        return SalesOutstandingResponse(grand_total_outstanding=grand_total, customers=list(grouped.values()))

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
    if current_user.role != "Owner":
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


@router.post("/v1/customers/upload-seed")
def upload_customers_seed(
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
            
            # Write audit activity log
            activity = ActivityLog(
                factory_id=int(factory_id),
                event_type="payment",
                description=f"Successfully imported {count} customers via batch spreadsheet seed upload."
            )
            db.add(activity)
            db.commit()
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

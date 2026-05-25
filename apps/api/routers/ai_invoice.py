from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import Integer, func as sql_func
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from db import get_db
from models import Customer, FinishedGoodsStock, PackagingProfile, SalesInvoice

router = APIRouter(prefix="/api/ai-invoice", tags=["ai-invoice"])

GST_RATE = Decimal("0.18")
MONEY_QUANT = Decimal("0.01")


def to_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


class InvoiceItemPayload(BaseModel):
    product_name: str = Field(..., min_length=1, max_length=255)
    volume_ml: int = Field(..., gt=0)
    packaging_dimension: str = Field(..., min_length=1, max_length=255)
    box_quantity: int = Field(..., gt=0)
    pieces_per_box: int = Field(..., gt=0)
    unit_price_per_packet: Decimal = Field(..., gt=0)


class DraftInvoiceRequest(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=255)
    factory_id: str = Field(..., min_length=1, max_length=100)
    items: List[InvoiceItemPayload] = Field(..., min_length=1)


InvoiceDraftItem = InvoiceItemPayload
CalculateDraftRequest = DraftInvoiceRequest


class InvoiceDraftItemResponse(BaseModel):
    product_name: str
    volume_ml: int
    packaging_dimension: str
    box_quantity: int
    pieces_per_box: int
    unit_price_per_packet: Decimal
    total_packets: int
    taxable_amount: Decimal
    gst_amount: Decimal
    total_amount: Decimal


class CalculateDraftResponse(BaseModel):
    customer_name: str
    factory_id: str
    gst_rate: Decimal
    items: List[InvoiceDraftItemResponse]
    total_amount_before_gst: Decimal
    gst_amount: Decimal
    grand_total: Decimal


class ConfirmInvoiceResponse(CalculateDraftResponse):
    status: str
    message: str
    invoice_ids: List[int]
    customer_id: int
    customer_balance: Decimal



class InvoiceItemPayload(BaseModel):
    product_name: str
    volume_ml: int
    packaging_dimension: str
    box_quantity: int
    pieces_per_box: int
    unit_price_per_packet: float
    factory_id: str  # 👈 YAHAN INT KI JAGAH STR HONA ZAROORI HAI!

class DraftInvoiceRequest(BaseModel):
    customer_name: str
    factory_id: str  # 👈 YAHAN BHI STR HONA ZAROORI HAI!
    items: List[InvoiceItemPayload]    


def calculate_invoice_lines(items: List[InvoiceItemPayload]) -> tuple[List[InvoiceDraftItemResponse], Decimal, Decimal, Decimal]:
    """All invoice math is deterministic Python Decimal math; no LLM is used."""
    response_items: List[InvoiceDraftItemResponse] = []
    total_before_gst = Decimal("0.00")

    for item in items:
        total_packets = item.box_quantity * item.pieces_per_box
        taxable_amount = to_money(Decimal(total_packets) * item.unit_price_per_packet)
        gst_amount = to_money(taxable_amount * GST_RATE)
        total_amount = to_money(taxable_amount + gst_amount)
        total_before_gst += taxable_amount

        response_items.append(
            InvoiceDraftItemResponse(
                product_name=item.product_name,
                volume_ml=item.volume_ml,
                packaging_dimension=item.packaging_dimension,
                box_quantity=item.box_quantity,
                pieces_per_box=item.pieces_per_box,
                unit_price_per_packet=to_money(item.unit_price_per_packet),
                total_packets=total_packets,
                taxable_amount=taxable_amount,
                gst_amount=gst_amount,
                total_amount=total_amount,
            )
        )

    total_before_gst = to_money(total_before_gst)
    gst_amount = to_money(total_before_gst * GST_RATE)
    grand_total = to_money(total_before_gst + gst_amount)
    return response_items, total_before_gst, gst_amount, grand_total


def normalize_factory_lookup_id(factory_id: str) -> int | str:
    normalized = factory_id.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="factory_id is required.",
        )
    if isinstance(Customer.__table__.c.factory_id.type, Integer):
        if not normalized.isdigit():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Alphanumeric factory_id is accepted by the invoice API schema, but this "
                    "database model is still configured with integer factory IDs."
                ),
            )
        return int(normalized)
    return normalized


def find_customer(db: Session, factory_id: str, customer_name: str) -> Customer | None:
    normalized_name = customer_name.strip().lower()
    lookup_factory_id = normalize_factory_lookup_id(factory_id)
    return (
        db.query(Customer)
        .filter(
            Customer.factory_id == lookup_factory_id,
            sql_func.lower(Customer.name) == normalized_name,
        )
        .first()
    )


def find_packaging_profile(db: Session, factory_id: str, item: InvoiceItemPayload) -> PackagingProfile | None:
    lookup_factory_id = normalize_factory_lookup_id(factory_id)
    packaging_name = item.packaging_dimension.strip().lower()
    product_name = item.product_name.strip().lower()

    profile = (
        db.query(PackagingProfile)
        .filter(
            PackagingProfile.factory_id == lookup_factory_id,
            PackagingProfile.cup_size_ml == item.volume_ml,
            (
                (sql_func.lower(PackagingProfile.profile_name) == packaging_name)
                | (sql_func.lower(PackagingProfile.box_size_name) == packaging_name)
                | (sql_func.lower(PackagingProfile.product_name) == product_name)
            ),
        )
        .first()
    )
    if profile:
        return profile

    return (
        db.query(PackagingProfile)
        .filter(
            PackagingProfile.factory_id == lookup_factory_id,
            PackagingProfile.cup_size_ml == item.volume_ml,
        )
        .first()
    )


@router.post("/calculate-draft", response_model=CalculateDraftResponse)
def calculate_draft(payload: CalculateDraftRequest) -> CalculateDraftResponse:
    items_response, total_before_gst, gst_amount, grand_total = calculate_invoice_lines(payload.items)

    return CalculateDraftResponse(
        customer_name=payload.customer_name.strip(),
        factory_id=payload.factory_id,
        gst_rate=GST_RATE,
        items=items_response,
        total_amount_before_gst=total_before_gst,
        gst_amount=gst_amount,
        grand_total=grand_total,
    )


@router.post("/confirm-and-deduct", response_model=ConfirmInvoiceResponse)
def confirm_and_deduct(
    payload: CalculateDraftRequest,
    db: Session = Depends(get_db),
) -> ConfirmInvoiceResponse:
    lookup_factory_id = normalize_factory_lookup_id(payload.factory_id)
    customer = find_customer(db, payload.factory_id, payload.customer_name)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer '{payload.customer_name.strip()}' not found for factory {payload.factory_id}.",
        )

    items_response, total_before_gst, gst_amount, grand_total = calculate_invoice_lines(payload.items)
    invoice_ids: List[int] = []

    try:
        for item, line in zip(payload.items, items_response):
            profile = find_packaging_profile(db, payload.factory_id, item)
            if not profile:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=(
                        f"No packaging profile found for product '{item.product_name}' "
                        f"({item.volume_ml} ml, {item.packaging_dimension})."
                    ),
                )

            stock = (
                db.query(FinishedGoodsStock)
                .filter(
                    FinishedGoodsStock.factory_id == lookup_factory_id,
                    FinishedGoodsStock.packaging_profile_id == profile.id,
                )
                .with_for_update()
                .first()
            )

            available_boxes = stock.boxes_available if stock else 0
            if not stock or available_boxes < item.box_quantity:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Insufficient finished goods stock for '{item.product_name}' "
                        f"({item.packaging_dimension}). Required boxes: {item.box_quantity}, "
                        f"available boxes: {available_boxes}."
                    ),
                )

            stock.boxes_available = available_boxes - item.box_quantity

            invoice = SalesInvoice(
                factory_id=lookup_factory_id,
                customer_id=customer.id,
                date=date.today(),
                cup_size_ml=item.volume_ml,
                packaging_profile_id=profile.id,
                boxes_sold=item.box_quantity,
                total_amount=line.total_amount,
                amount_paid=Decimal("0.00"),
            )
            db.add(invoice)
            db.flush()
            invoice_ids.append(invoice.id)

        customer.balance_amount = to_money(Decimal(customer.balance_amount or 0) + grand_total)
        customer.total_due = to_money(Decimal(customer.total_due or 0) + grand_total)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invoice confirmation failed. No inventory was deducted.",
        ) from exc

    return ConfirmInvoiceResponse(
        status="success",
        message="Invoice confirmed, ledger entry saved, and finished goods stock deducted.",
        invoice_ids=invoice_ids,
        customer_id=customer.id,
        customer_name=payload.customer_name.strip(),
        factory_id=payload.factory_id,
        gst_rate=GST_RATE,
        items=items_response,
        total_amount_before_gst=total_before_gst,
        gst_amount=gst_amount,
        grand_total=grand_total,
        customer_balance=to_money(Decimal(customer.balance_amount or 0)),
    )

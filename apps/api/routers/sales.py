from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import or_, func as sql_func
from sqlalchemy.orm import Session

from dependencies import OWNER_ROLES, SALES_ROLES, check_permissions
from db import get_db
from models import BoxStock, Customer, DailySale, FinalProductStock, Payment, User
from routers.payments import customer_phone, send_n8n_whatsapp_event
from schemas import CustomerCreate, CustomerResponse, DailySaleCreate, DailySaleResponse


router = APIRouter()
MONEY_QUANT = Decimal("0.01")


def to_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def require_sold_quantity(boxes_sold: int, loose_packets_sold: int) -> None:
    if boxes_sold <= 0 and loose_packets_sold <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one sold quantity is required")


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


@router.post("/add", response_model=DailySaleResponse, status_code=status.HTTP_201_CREATED)
def add_sale_invoice(
    payload: DailySaleCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = current_user.factory_id

    try:
        customer = (
            db.query(Customer)
            .filter(Customer.factory_id == factory_id)
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

        for item in payload.items:
            require_sold_quantity(item.boxes_sold, item.loose_packets_sold)
            stock = (
                db.query(FinalProductStock)
                .filter(FinalProductStock.factory_id == factory_id)
                .filter(FinalProductStock.product_size_ml == item.product_size_ml)
                .filter(sql_func.lower(FinalProductStock.variety) == item.variety.lower())
                .filter(sql_func.lower(FinalProductStock.packaging_size_name) == item.packaging_size_name.lower())
                .with_for_update()
                .first()
            )
            if stock is None:
                box_stock = (
                    db.query(BoxStock)
                    .filter(BoxStock.factory_id == factory_id)
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
                    total_boxes=0,
                    loose_packets=0,
                    packets_per_box_limit=1,
                )
                db.add(stock)
                db.flush()

            available_packets = (stock.total_boxes or 0) * stock.packets_per_box_limit + (stock.loose_packets or 0)
            sold_packets = item.boxes_sold * stock.packets_per_box_limit + item.loose_packets_sold
            remaining_packets = available_packets - sold_packets
            stock.total_boxes = remaining_packets // stock.packets_per_box_limit
            stock.loose_packets = remaining_packets % stock.packets_per_box_limit

            line_total = to_money(
                Decimal(item.boxes_sold) * to_money(item.rate_per_box)
                + Decimal(item.loose_packets_sold) * to_money(item.rate_per_packet)
            )
            current_bill_amount = to_money(current_bill_amount + line_total)

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

        db.commit()

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
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sale invoice failed and was rolled back: {exc}",
        ) from exc


@router.post("/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_sales_customer(
    payload: CustomerCreate,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    total_due = payload.total_due if payload.total_due is not None else payload.previous_due
    phone_number = payload.phone_number.strip()
    existing = (
        db.query(Customer)
        .filter(Customer.factory_id == current_user.factory_id)
        .filter(Customer.phone_number == phone_number)
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Customer phone number already exists")

    customer = Customer(
        factory_id=current_user.factory_id,
        name=payload.name.strip(),
        phone_number=phone_number,
        place=payload.place.strip(),
        gst_number=payload.gst_number.strip() if payload.gst_number else None,
        address=payload.address or payload.place.strip(),
        phone=phone_number,
        contact_number=phone_number,
        previous_due=payload.previous_due,
        total_due=total_due,
        pending_balance=total_due,
        balance_amount=total_due,
        pending_dues=float(total_due),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/customers/search", response_model=list[CustomerSearchResponse])
def search_customers(
    q: str = Query(default="", max_length=100),
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    query_text = q.strip().lower()
    query = db.query(Customer).filter(Customer.factory_id == current_user.factory_id)
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
        )
        for customer in customers
    ]


@router.get("/customers/{customer_id}/balance", response_model=CustomerBalanceResponse)
def get_customer_balance(
    customer_id: int,
    current_user: User = Depends(check_permissions(SALES_ROLES)),
    db: Session = Depends(get_db),
):
    customer = (
        db.query(Customer)
        .filter(Customer.factory_id == current_user.factory_id)
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

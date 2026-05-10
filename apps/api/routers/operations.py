from decimal import Decimal, ROUND_HALF_UP
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from auth import get_current_user
from db import get_db
from models import (
    BlankStock,
    BottomStock,
    BoxStock,
    Customer,
    DailyProduction,
    DailySale,
    FinalProductStock,
    Machine,
    User,
    Worker,
)
from schemas import DailyProductionCreate, DailyProductionResponse, DailySaleCreate, DailySaleResponse


router = APIRouter(prefix="/api", tags=["operations"])

MONEY_QUANT = Decimal("0.01")
QTY_QUANT = Decimal("0.001")


def to_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def to_qty(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(QTY_QUANT, rounding=ROUND_HALF_UP)


def require_non_empty_work(payload_boxes: int, payload_loose: int) -> None:
    if payload_boxes == 0 and payload_loose == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one box or loose packet must be entered",
        )


@router.post("/production/daily", response_model=DailyProductionResponse, status_code=status.HTTP_201_CREATED)
def create_daily_production(
    payload: DailyProductionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    factory_id = current_user.factory_id
    require_non_empty_work(payload.total_boxes_made, payload.loose_packets_made)

    try:
        machine = (
            db.query(Machine)
            .filter(Machine.factory_id == factory_id)
            .filter(Machine.id == payload.machine_id)
            .first()
        )
        if machine is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")

        worker = (
            db.query(Worker)
            .filter(Worker.factory_id == factory_id)
            .filter(Worker.id == payload.worker_id)
            .first()
        )
        if worker is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

        product_size_ml = machine.mould_size_ml or machine.cup_size_ml
        if not product_size_ml:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Machine does not have a product mould size configured",
            )

        blank_stock = (
            db.query(BlankStock)
            .filter(BlankStock.factory_id == factory_id)
            .filter(BlankStock.blank_size_ml == product_size_ml)
            .with_for_update()
            .first()
        )
        if blank_stock is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blank stock not found")

        bottom_stock = (
            db.query(BottomStock)
            .filter(BottomStock.factory_id == factory_id)
            .filter(BottomStock.bottom_size_mm == machine.bottom_size_mm)
            .with_for_update()
            .first()
        )
        if bottom_stock is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bottom stock not found")

        blank_after = to_qty(blank_stock.total_qty_kg) - to_qty(payload.blank_used_kg)
        bottom_after = to_qty(bottom_stock.total_qty_kg) - to_qty(payload.bottom_used_kg)
        if blank_after < 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Insufficient blank stock")
        if bottom_after < 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Insufficient bottom stock")

        final_stock = (
            db.query(FinalProductStock)
            .filter(FinalProductStock.factory_id == factory_id)
            .filter(FinalProductStock.product_size_ml == product_size_ml)
            .filter(sql_func.lower(FinalProductStock.packaging_size_name) == payload.packaging_size_name.lower())
            .with_for_update()
            .first()
        )
        if final_stock is None:
            final_stock = FinalProductStock(
                factory_id=factory_id,
                product_size_ml=product_size_ml,
                packaging_size_name=payload.packaging_size_name.strip(),
                total_boxes=0,
                loose_packets=0,
                packets_per_box_limit=payload.packets_per_box_limit,
            )
            db.add(final_stock)
            db.flush()

        total_boxes_before = final_stock.total_boxes or 0
        loose_before = final_stock.loose_packets or 0
        current_loose = loose_before + payload.loose_packets_made
        boxes_from_loose = current_loose // payload.packets_per_box_limit
        final_loose_packets = current_loose % payload.packets_per_box_limit
        final_total_boxes = total_boxes_before + payload.total_boxes_made + boxes_from_loose
        boxes_packed_this_entry = payload.total_boxes_made + boxes_from_loose

        box_stock = (
            db.query(BoxStock)
            .filter(BoxStock.factory_id == factory_id)
            .filter(sql_func.lower(BoxStock.packaging_size_name) == payload.packaging_size_name.lower())
            .with_for_update()
            .first()
        )
        if box_stock is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Box stock not found")

        box_stock_after = (box_stock.total_boxes or 0) - boxes_packed_this_entry
        if box_stock_after < 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Insufficient box stock")

        blank_stock.total_qty_kg = blank_after
        bottom_stock.total_qty_kg = bottom_after
        final_stock.total_boxes = final_total_boxes
        final_stock.loose_packets = final_loose_packets
        final_stock.packets_per_box_limit = payload.packets_per_box_limit
        box_stock.total_boxes = box_stock_after

        production = DailyProduction(
            factory_id=factory_id,
            date=payload.date,
            worker_id=worker.id,
            machine_id=machine.id,
            product_size_ml=product_size_ml,
            packaging_size_name=payload.packaging_size_name.strip(),
            packets_per_box_limit=payload.packets_per_box_limit,
            total_boxes_made=payload.total_boxes_made,
            loose_packets_made=payload.loose_packets_made,
            boxes_from_loose=boxes_from_loose,
            blank_used_kg=to_qty(payload.blank_used_kg),
            bottom_used_kg=to_qty(payload.bottom_used_kg),
        )
        db.add(production)
        db.commit()
        db.refresh(production)

        return DailyProductionResponse(
            production_id=production.id,
            product_size_ml=product_size_ml,
            total_boxes_before=total_boxes_before,
            loose_packets_before=loose_before,
            boxes_from_loose=boxes_from_loose,
            total_boxes_after=final_total_boxes,
            loose_packets_after=final_loose_packets,
            blank_stock_after_kg=blank_after,
            bottom_stock_after_kg=bottom_after,
            box_stock_after=box_stock_after,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Daily production failed and was rolled back: {exc}",
        ) from exc


@router.post("/sales/daily", response_model=DailySaleResponse, status_code=status.HTTP_201_CREATED)
def create_daily_sale(
    payload: DailySaleCreate,
    current_user: User = Depends(get_current_user),
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

        sale_ids: List[int] = []
        bill_total = Decimal("0.00")
        for item in payload.items:
            require_non_empty_work(item.boxes_sold, item.loose_packets_sold)
            stock = (
                db.query(FinalProductStock)
                .filter(FinalProductStock.factory_id == factory_id)
                .filter(FinalProductStock.product_size_ml == item.product_size_ml)
                .filter(sql_func.lower(FinalProductStock.packaging_size_name) == item.packaging_size_name.lower())
                .with_for_update()
                .first()
            )
            if stock is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Final product stock not found")

            available_packets = (stock.total_boxes or 0) * stock.packets_per_box_limit + (stock.loose_packets or 0)
            sold_packets = item.boxes_sold * stock.packets_per_box_limit + item.loose_packets_sold
            if sold_packets > available_packets:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Insufficient final stock for {item.product_size_ml}ml "
                        f"{item.packaging_size_name}"
                    ),
                )

            remaining_packets = available_packets - sold_packets
            stock.total_boxes = remaining_packets // stock.packets_per_box_limit
            stock.loose_packets = remaining_packets % stock.packets_per_box_limit

            line_total = to_money(
                Decimal(item.boxes_sold) * to_money(item.rate_per_box)
                + Decimal(item.loose_packets_sold) * to_money(item.rate_per_packet)
            )
            bill_total = to_money(bill_total + line_total)
            sale = DailySale(
                factory_id=factory_id,
                date=payload.date,
                customer_id=customer.id,
                product_size_ml=item.product_size_ml,
                packaging_size_name=item.packaging_size_name.strip(),
                boxes_sold=item.boxes_sold,
                loose_packets_sold=item.loose_packets_sold,
                rate_per_box=to_money(item.rate_per_box),
                rate_per_packet=to_money(item.rate_per_packet),
                total_amount=line_total,
                amount_paid=Decimal("0.00"),
            )
            db.add(sale)
            db.flush()
            sale_ids.append(sale.id)

        if sale_ids:
            first_sale = db.query(DailySale).filter(DailySale.id == sale_ids[0]).first()
            if first_sale is not None:
                first_sale.amount_paid = to_money(payload.amount_paid)

        previous_due = to_money(customer.total_due or customer.balance_amount or 0)
        new_total_due = to_money(previous_due + bill_total - to_money(payload.amount_paid))
        if new_total_due < 0:
            new_total_due = Decimal("0.00")

        customer.previous_due = previous_due
        customer.total_due = new_total_due
        customer.balance_amount = new_total_due
        customer.pending_balance = new_total_due
        customer.pending_dues = float(new_total_due)

        db.commit()
        return DailySaleResponse(
            sale_ids=sale_ids,
            customer_id=customer.id,
            bill_total=bill_total,
            amount_paid=to_money(payload.amount_paid),
            customer_total_due=new_total_due,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Daily sale failed and was rolled back: {exc}",
        ) from exc

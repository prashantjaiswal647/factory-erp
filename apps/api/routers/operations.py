from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from dependencies import PRODUCTION_ROLES, SALES_ROLES, check_permissions
from db import get_db
from models import (
    BlankStock,
    BottomStock,
    BoxStock,
    CostingMaster,
    Customer,
    DailyProduction,
    DailySale,
    FinalProductStock,
    Machine,
    User,
    Worker,
    Payment,
    MaterialYield,
)
from routers.payments import customer_phone, send_n8n_whatsapp_event
from schemas import DailyProductionCreate, DailyProductionResponse, DailySaleCreate, DailySaleResponse


router = APIRouter(prefix="/api", tags=["operations"])

MONEY_QUANT = Decimal("0.01")
QTY_QUANT = Decimal("0.001")


def to_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def to_qty(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(QTY_QUANT, rounding=ROUND_HALF_UP)


def to_lower(value: str) -> str:
    return (value or "").strip().lower()


def require_non_empty_work(payload_boxes: int, payload_loose: int) -> None:
    if payload_boxes == 0 and payload_loose == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one box or loose packet must be entered",
        )


@router.post("/production/daily", response_model=DailyProductionResponse, status_code=status.HTTP_201_CREATED)
@router.post("/production/entry", response_model=DailyProductionResponse, status_code=status.HTTP_201_CREATED)
def create_daily_production(
    payload: DailyProductionCreate,
    current_user: User = Depends(check_permissions(PRODUCTION_ROLES)),
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

        selected_final_stock = None
        if payload.product_id is not None:
            selected_final_stock = (
                db.query(FinalProductStock)
                .filter(FinalProductStock.factory_id == factory_id)
                .filter(FinalProductStock.id == payload.product_id)
                .with_for_update()
                .first()
            )
            if selected_final_stock is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Final product stock variation not found")

        product_size_ml = (
            payload.product_size_ml
            or (selected_final_stock.product_size_ml if selected_final_stock is not None else None)
            or machine.mould_size_ml
            or machine.cup_size_ml
        )
        if not product_size_ml:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Machine does not have a product mould size configured",
            )
        packaging_size_name = (
            payload.packaging_size
            or payload.packaging_size_name
            or (selected_final_stock.packaging_size_name if selected_final_stock is not None else None)
        )
        if not packaging_size_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Packaging size variation is required",
            )
        variety = (payload.variety or (selected_final_stock.variety if selected_final_stock is not None else "") or "Standard/White").strip()

        blank_stock = (
            db.query(BlankStock)
            .filter(BlankStock.factory_id == factory_id)
            .filter(BlankStock.blank_size_ml == product_size_ml)
            .filter(sql_func.lower(BlankStock.variety) == to_lower(variety))
            .with_for_update()
            .first()
        )
        if blank_stock is None:
            blank_stock = BlankStock(
                factory_id=factory_id,
                blank_size_ml=product_size_ml,
                variety=variety,
                linked_bottom_size_mm=machine.bottom_size_mm,
                total_qty_kg=Decimal("0.000"),
            )
            db.add(blank_stock)
            db.flush()

        bottom_stock = (
            db.query(BottomStock)
            .filter(BottomStock.factory_id == factory_id)
            .filter(BottomStock.bottom_size_mm == machine.bottom_size_mm)
            .filter(sql_func.lower(BottomStock.variety) == to_lower(variety))
            .with_for_update()
            .first()
        )
        if bottom_stock is None:
            bottom_stock = BottomStock(
                factory_id=factory_id,
                bottom_size_mm=machine.bottom_size_mm,
                variety=variety,
                total_qty_kg=Decimal("0.000"),
            )
            db.add(bottom_stock)
            db.flush()

        blank_used_bori = to_qty(payload.blank_used_bori)
        blank_weight_per_bora = to_qty(blank_stock.weight_per_bora_kg)
        if blank_weight_per_bora <= 0 and blank_used_bori > 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Blank stock weight_per_bora_kg is not configured for this size",
            )
        blank_used_kg = to_qty(blank_used_bori * blank_weight_per_bora)

        bottom_used_rolls = payload.bottom_used_rolls or 0
        bottom_weight_per_roll = Decimal("0.000")
        if bottom_used_rolls > 0:
            if not bottom_stock.bag_weight_kg or not bottom_stock.rolls_per_bag:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Bottom stock bag_weight_kg and rolls_per_bag are required before deducting rolls",
                )
            bottom_weight_per_roll = to_qty(Decimal(bottom_stock.bag_weight_kg) / Decimal(bottom_stock.rolls_per_bag))
        bottom_used_kg = to_qty(Decimal(bottom_used_rolls) * bottom_weight_per_roll)

        # Calculate total pieces produced for BOM fallback
        total_pieces = Decimal(payload.total_boxes_made * payload.packets_per_box_limit + payload.loose_packets_made) * Decimal(payload.pieces_per_packet)

        # 1. Blank Stock BOM Fallback
        if blank_used_kg <= 0 and total_pieces > 0:
            blank_yield = (
                db.query(MaterialYield)
                .filter(MaterialYield.factory_id == factory_id)
                .filter(MaterialYield.material_type == "Blank")
                .filter(MaterialYield.size_ml == product_size_ml)
                .first()
            )
            if blank_yield and blank_yield.pieces_per_kg > 0:
                blank_used_kg = to_qty(total_pieces / Decimal(blank_yield.pieces_per_kg))
                if blank_stock.weight_per_bora_kg and blank_stock.weight_per_bora_kg > 0:
                    blank_used_bori = to_qty(blank_used_kg / Decimal(blank_stock.weight_per_bora_kg))

        # 2. Bottom Stock BOM Fallback
        if bottom_used_kg <= 0 and total_pieces > 0:
            bottom_yield = (
                db.query(MaterialYield)
                .filter(MaterialYield.factory_id == factory_id)
                .filter(MaterialYield.material_type == "Bottom")
                .filter(MaterialYield.size_ml == product_size_ml)
                .first()
            )
            if bottom_yield and bottom_yield.pieces_per_kg > 0:
                bottom_used_kg = to_qty(total_pieces / Decimal(bottom_yield.pieces_per_kg))
                if bottom_stock.bag_weight_kg and bottom_stock.rolls_per_bag and bottom_stock.rolls_per_bag > 0:
                    bottom_weight_per_roll = Decimal(bottom_stock.bag_weight_kg) / Decimal(bottom_stock.rolls_per_bag)
                    if bottom_weight_per_roll > 0:
                        bottom_used_rolls = int(bottom_used_kg / bottom_weight_per_roll)

        blank_after = to_qty(blank_stock.total_qty_kg) - blank_used_kg
        bottom_after = to_qty(bottom_stock.total_qty_kg) - bottom_used_kg
        blank_boras_after = to_qty(blank_stock.total_boras) - blank_used_bori if blank_stock.total_boras is not None else None
        bottom_rolls_after = (bottom_stock.total_rolls or 0) - bottom_used_rolls

        final_stock = selected_final_stock
        if final_stock is None:
            final_stock = (
                db.query(FinalProductStock)
                .filter(FinalProductStock.factory_id == factory_id)
                .filter(FinalProductStock.product_size_ml == product_size_ml)
                .filter(sql_func.lower(FinalProductStock.variety) == to_lower(variety))
                .filter(sql_func.lower(FinalProductStock.packaging_size_name) == to_lower(packaging_size_name))
                .with_for_update()
                .first()
            )
        if final_stock is None:
            final_stock = FinalProductStock(
                factory_id=factory_id,
                product_size_ml=product_size_ml,
                variety=variety,
                packaging_size_name=packaging_size_name.strip(),
                pieces_per_packet=payload.pieces_per_packet,
                current_quantity=0,
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
            .filter(sql_func.lower(BoxStock.packaging_size_name) == to_lower(packaging_size_name))
            .with_for_update()
            .first()
        )
        if box_stock is None:
            box_stock = BoxStock(
                factory_id=factory_id,
                packaging_size_name=packaging_size_name.strip(),
                total_boxes=0,
            )
            db.add(box_stock)
            db.flush()

        box_stock_after = (box_stock.total_boxes or 0) - boxes_packed_this_entry
        total_raw_material_kg = to_qty(blank_used_kg + bottom_used_kg)
        wastage_kg = to_qty(payload.wastage_kg)
        wastage_limit = to_qty(total_raw_material_kg * Decimal("0.02"))
        wastage_status = "HIGH_WASTAGE" if total_raw_material_kg > 0 and wastage_kg > wastage_limit else "NORMAL"

        costing = db.query(CostingMaster).filter(CostingMaster.factory_id == factory_id).first()
        paper_price = Decimal(costing.paper_price_per_kg or 0) if costing else Decimal("0.00")
        bottom_price = Decimal(costing.bottom_roll_price_per_kg or 0) if costing else Decimal("0.00")
        labor_per_box = Decimal(costing.labour_cost_per_box or 0) if costing else Decimal("0.00")
        electricity_per_box = Decimal(costing.electricity_cost_per_box or 0) if costing else Decimal("0.00")
        raw_material_cost = to_money(blank_used_kg * paper_price + bottom_used_kg * bottom_price)
        labor_cost = to_money(Decimal(boxes_packed_this_entry) * labor_per_box)
        if labor_cost == 0 and worker.daily_wages:
            labor_cost = to_money(worker.daily_wages)
        electricity_cost = to_money(Decimal(boxes_packed_this_entry) * electricity_per_box)
        production_cost = to_money(raw_material_cost + labor_cost + electricity_cost)

        blank_stock.total_qty_kg = blank_after
        if blank_boras_after is not None:
            blank_stock.total_boras = blank_boras_after
        bottom_stock.total_qty_kg = bottom_after
        bottom_stock.total_weight_kg = bottom_after
        bottom_stock.total_rolls = bottom_rolls_after
        final_stock.total_boxes = final_total_boxes
        final_stock.current_quantity = final_total_boxes
        final_stock.variety = variety
        final_stock.packaging_size_name = packaging_size_name.strip()
        final_stock.pieces_per_packet = payload.pieces_per_packet
        final_stock.loose_packets = final_loose_packets
        final_stock.packets_per_box_limit = payload.packets_per_box_limit
        box_stock.total_boxes = box_stock_after

        production = DailyProduction(
            factory_id=factory_id,
            date=payload.date,
            worker_id=worker.id,
            machine_id=machine.id,
            product_size_ml=product_size_ml,
            variety=variety,
            packaging_size_name=packaging_size_name.strip(),
            packets_per_box_limit=payload.packets_per_box_limit,
            total_boxes_made=payload.total_boxes_made,
            loose_packets_made=payload.loose_packets_made,
            boxes_from_loose=boxes_from_loose,
            blank_used_kg=blank_used_kg,
            bottom_used_kg=bottom_used_kg,
            wastage_kg=wastage_kg,
            wastage_status=wastage_status,
            total_raw_material_kg=total_raw_material_kg,
            raw_material_cost=raw_material_cost,
            labor_cost=labor_cost,
            electricity_cost=electricity_cost,
            production_cost=production_cost,
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
            wastage_status=wastage_status,
            total_raw_material_kg=total_raw_material_kg,
            production_cost=production_cost,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Production entry failed and was rolled back",
        ) from exc


@router.get("/production/alerts")
def production_alerts(
    current_user: User = Depends(check_permissions(PRODUCTION_ROLES)),
    db: Session = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    high_wastage_rows = (
        db.query(DailyProduction)
        .filter(DailyProduction.factory_id == current_user.factory_id)
        .filter(DailyProduction.wastage_status == "HIGH_WASTAGE")
        .filter(DailyProduction.created_at >= cutoff)
        .order_by(DailyProduction.created_at.desc())
        .all()
    )
    return {
        "high_wastage_count": len(high_wastage_rows),
        "has_high_wastage": len(high_wastage_rows) > 0,
        "alerts": [
            {
                "production_id": row.id,
                "date": row.date.isoformat(),
                "product_size_ml": row.product_size_ml,
                "variety": row.variety,
                "wastage_kg": float(row.wastage_kg or 0),
                "total_raw_material_kg": float(row.total_raw_material_kg or 0),
                "production_cost": float(row.production_cost or 0),
            }
            for row in high_wastage_rows
        ],
    }


@router.post("/sales/daily", response_model=DailySaleResponse, status_code=status.HTTP_201_CREATED)
def create_daily_sale(
    payload: DailySaleCreate,
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

        sale_ids: List[int] = []
        bill_total = Decimal("0.00")
        normalized_customer_phone = customer_phone(customer)
        for item in payload.items:
            require_non_empty_work(item.boxes_sold, item.loose_packets_sold)
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
                packets_per_box_limit = 1
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
                    current_quantity=0,
                    total_boxes=0,
                    loose_packets=0,
                    packets_per_box_limit=packets_per_box_limit,
                )
                db.add(stock)
                db.flush()

            available_packets = (stock.total_boxes or 0) * stock.packets_per_box_limit + (stock.loose_packets or 0)
            sold_packets = item.boxes_sold * stock.packets_per_box_limit + item.loose_packets_sold
            if available_packets < sold_packets:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Insufficient final product stock for {item.product_size_ml}ml {item.variety} {item.packaging_size_name}",
                )

            remaining_packets = available_packets - sold_packets
            stock.total_boxes = remaining_packets // stock.packets_per_box_limit
            stock.current_quantity = stock.total_boxes
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
        send_n8n_whatsapp_event(
            {
                "customer_name": customer.name,
                "customer_phone": normalized_customer_phone,
                "amount_just_paid": str(to_money(payload.amount_paid)),
                "total_remaining_balance": str(new_total_due),
                "type": "SALE",
            }
        )
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

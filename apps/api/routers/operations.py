from datetime import date as date_cls, datetime, time as time_cls, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy import func as sql_func, text
from sqlalchemy.orm import Session

from auth import assert_owner_delete_permission
from dependencies import PRODUCTION_ROLES, SALES_ROLES, check_permissions
from db import get_db
from models import (
    AttendanceLog,
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
    ActivityLog,
    AppUsageLog,
    MaterialYield,
)
from pydantic import BaseModel, Field
from routers.payments import customer_phone, send_n8n_whatsapp_event
from schemas import DailyProductionCreate, DailyProductionResponse, DailySaleCreate, DailySaleResponse
from services.activity_logger import log_activity
from services.n8n_sync import sync_data_to_n8n_bg


router = APIRouter(prefix="/api", tags=["operations"])

MONEY_QUANT = Decimal("0.01")
QTY_QUANT = Decimal("0.001")
VALID_ACTIVITY_EVENT_TYPES = {"production", "attendance", "expense", "payment", "machine_telemetry"}
logger = logging.getLogger(__name__)
LOCAL_TZ = ZoneInfo("Asia/Kolkata")


def to_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def to_qty(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(QTY_QUANT, rounding=ROUND_HALF_UP)


def to_lower(value) -> str:
    return str(value or "").strip().lower()


def require_non_empty_work(boxes, loose) -> None:
    if (boxes or 0) == 0 and (loose or 0) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one box or loose packet must be entered",
        )


def log_factory_operation(
    db: Session,
    *,
    factory_id: int,
    event_type: str,
    description: str,
    log_date: Optional[date_cls] = None,
    user_id: Optional[int] = None,
    user_role: Optional[str] = None,
    action_type: str = "CREATE",
) -> None:
    """Best-effort activity audit insert that must never break the caller."""
    try:
        normalized_event_type = (event_type or "").strip()
        if normalized_event_type not in VALID_ACTIVITY_EVENT_TYPES:
            normalized_event_type = "machine_telemetry"
        normalized_description = (description or "").strip()
        if not normalized_description:
            return

        created_at = datetime.now(LOCAL_TZ)
        effective_log_date = log_date or created_at.date()
        savepoint = db.connection().begin_nested()
        try:
            db.execute(
                text(
                    """
                    INSERT INTO activity_logs (
                        factory_id, event_type, description, log_date, created_at,
                        user_id, user_role, action_type, entity_name, entity_type,
                        short_statement, committed_at
                    )
                    VALUES (
                        :factory_id, :event_type, :description, :log_date, :created_at,
                        :user_id, :user_role, :action_type, :entity_name, :entity_type,
                        :short_statement, :committed_at
                    )
                    """
                ),
                {
                    "factory_id": int(factory_id),
                    "event_type": normalized_event_type,
                    "description": normalized_description,
                    "log_date": effective_log_date,
                    "created_at": created_at,
                    "user_id": user_id,
                    "user_role": user_role,
                    "action_type": (action_type or "CREATE").strip().upper(),
                    "entity_name": normalized_event_type,
                    "entity_type": normalized_event_type,
                    "short_statement": normalized_description,
                    "committed_at": created_at,
                },
            )
            savepoint.commit()
        except Exception:
            savepoint.rollback()
            raise
    except Exception as log_error:
        logger.exception("Activity logging failed and was suppressed: %s", log_error)


def log_audit_trail(
    db: Session,
    *,
    factory_id: int,
    user_id: Optional[int] = None,
    user_role: Optional[str] = None,
    action_type: Optional[str] = None,
    entity_name: Optional[str] = None,
    short_statement: Optional[str] = None,
    event_type: str = "machine_telemetry",
    description: str = "",
    log_date: Optional[date_cls] = None,
) -> None:
    """Best-effort activity audit insert that includes audit fields and must never break the caller."""
    try:
        normalized_event_type = (event_type or "").strip()
        if normalized_event_type not in VALID_ACTIVITY_EVENT_TYPES:
            normalized_event_type = "machine_telemetry"
        normalized_description = (description or short_statement or "").strip()
        if not normalized_description:
            return
        normalized_action = (action_type or "CREATE").strip().upper()

        created_at = datetime.now(LOCAL_TZ)
        savepoint = db.connection().begin_nested()
        try:
            db.execute(
                text(
                    """
                    INSERT INTO activity_logs (
                        factory_id, event_type, description, log_date, created_at,
                        user_id, user_role, action_type, entity_name, entity_type,
                        short_statement, committed_at
                    )
                    VALUES (
                        :factory_id, :event_type, :description, :log_date, :created_at,
                        :user_id, :user_role, :action_type, :entity_name, :entity_type,
                        :short_statement, :committed_at
                    )
                    """
                ),
                {
                    "factory_id": int(factory_id),
                    "event_type": normalized_event_type,
                    "description": normalized_description,
                    "log_date": log_date or created_at.date(),
                    "created_at": created_at,
                    "user_id": user_id,
                    "user_role": user_role,
                    "action_type": normalized_action,
                    "entity_name": entity_name,
                    "entity_type": entity_name or normalized_event_type,
                    "short_statement": normalized_description[:500],
                    "committed_at": created_at,
                },
            )
            savepoint.commit()
        except Exception:
            savepoint.rollback()
            raise
    except Exception as log_error:
        logger.exception("Audit trail logging failed and was suppressed: %s", log_error)


def average_bottom_weight_per_roll(bottom_stock: BottomStock) -> Decimal:
    total_rolls = int(bottom_stock.total_rolls or 0)
    if total_rolls <= 0:
        return Decimal("0.000")

    total_weight = to_qty(bottom_stock.total_qty_kg)
    if total_weight <= 0:
        total_weight = to_qty(bottom_stock.total_weight_kg)
    if total_weight <= 0:
        return Decimal("0.000")

    return to_qty(total_weight / Decimal(total_rolls))


def mark_worker_present_for_production(
    db: Session,
    *,
    factory_id: str,
    worker: Worker,
    production_date,
    production_qty: int,
) -> Optional[AttendanceLog]:
    existing_log = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.factory_id == factory_id)
        .filter(AttendanceLog.worker_id == worker.id)
        .filter(AttendanceLog.date == production_date)
        .first()
    )
    if existing_log is not None:
        print("Automatic attendance skipped; existing attendance log found:", existing_log.id)
        return None

    duty_hours = float(worker.duty_hours or worker.shift_hours or 8.0)
    if duty_hours <= 0:
        duty_hours = 8.0

    attendance_log = AttendanceLog(
        factory_id=factory_id,
        date=production_date,
        worker_id=worker.id,
        status="Present",
        is_present=True,
        duty_hours=duty_hours,
        production_qty=Decimal(production_qty or 0),
    )
    db.add(attendance_log)
    db.flush()

    try:
        log_factory_operation(
            db,
            factory_id=int(factory_id),
            event_type="attendance",
            description=f"System automatically marked attendance Present for {worker.name} (linked to production)",
            log_date=production_date,
        )
    except Exception as log_error:
        logger.exception("Suppressed activity log failure for automatic attendance: %s", log_error)

    print("Automatic attendance marked Present for production worker:", attendance_log.id)
    return attendance_log


@router.post("/production/daily", response_model=DailyProductionResponse, status_code=status.HTTP_201_CREATED)
@router.post("/production/entry", response_model=DailyProductionResponse, status_code=status.HTTP_201_CREATED)
def create_daily_production(
    payload: DailyProductionCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(PRODUCTION_ROLES)),
    db: Session = Depends(get_db),
):
    print("Incoming Payload Details: ", payload.dict())
    factory_id = str(current_user.factory_id)
    if payload.factory_id and str(payload.factory_id) != factory_id:
        print("Incoming payload factory_id ignored in favor of authenticated user factory_id:", payload.factory_id, factory_id)
    if payload.worker_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="worker_id/operator_id is required for daily production entry",
        )
    if payload.machine_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="machine_id is required for daily production entry",
        )
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
            if bottom_stock.bag_weight_kg and bottom_stock.rolls_per_bag and bottom_stock.rolls_per_bag > 0:
                bottom_weight_per_roll = to_qty(Decimal(bottom_stock.bag_weight_kg) / Decimal(bottom_stock.rolls_per_bag))
            else:
                bottom_weight_per_roll = average_bottom_weight_per_roll(bottom_stock)
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
        
        # Preserve original onboarding inputs, updating only dynamic descriptors
        final_stock.variety = variety
        final_stock.packaging_size_name = packaging_size_name.strip()
        final_stock.pieces_per_packet = payload.pieces_per_packet
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
        db.flush()
        attendance_log = mark_worker_present_for_production(
            db,
            factory_id=factory_id,
            worker=worker,
            production_date=payload.date,
            production_qty=payload.total_boxes_made + payload.loose_packets_made,
        )

        # Recalculate dynamic live stock balance and sync caches
        from routers.inventory import recalculate_and_sync_sku_stock
        live_boxes, live_loose = recalculate_and_sync_sku_stock(
            db=db,
            factory_id=str(factory_id),
            product_size_ml=product_size_ml,
            variety=variety,
            packaging_size_name=packaging_size_name,
        )

        total_boxes_completed = payload.total_boxes_made + boxes_from_loose
        wastage_percent = Decimal("0.00")
        if total_raw_material_kg > 0:
            wastage_percent = to_money((wastage_kg / total_raw_material_kg) * Decimal("100"))
        try:
            log_factory_operation(
                db,
                factory_id=int(factory_id),
            event_type="production",
            description=f"\U0001F4E6 Production Update: Machine {machine.id} completed {total_boxes_completed} boxes of {product_size_ml} cups (Wastage: {wastage_percent}%)",
            log_date=payload.date,
        )
        except Exception as log_error:
            logger.exception("Suppressed activity log failure for production entry: %s", log_error)

        db.commit()
        db.refresh(production)
        background_tasks.add_task(
            log_activity,
            db,
            int(current_user.factory_id),
            current_user.id,
            current_user.full_name or current_user.username,
            current_user.role,
            "PRODUCTION_SAVED",
            f"{total_boxes_completed} units of {product_size_ml}ml {variety} produced",
            "production",
            production.id,
            {"machine_id": machine.id, "worker_id": worker.id, "wastage_percent": str(wastage_percent)},
        )

        background_tasks.add_task(
            sync_data_to_n8n_bg,
            factory_id=str(factory_id),
            sync_type="production",
            action="insert",
            data=payload,
        )

        return DailyProductionResponse(
            production_id=production.id,
            product_size_ml=product_size_ml,
            total_boxes_before=total_boxes_before,
            loose_packets_before=loose_before,
            boxes_from_loose=boxes_from_loose,
            total_boxes_after=live_boxes,
            loose_packets_after=live_loose,
            blank_stock_after_kg=blank_after,
            bottom_stock_after_kg=bottom_after,
            box_stock_after=box_stock_after,
            wastage_status=wastage_status,
            total_raw_material_kg=total_raw_material_kg,
            production_cost=production_cost,
            attendance_auto_marked=attendance_log is not None,
            attendance_log_id=attendance_log.id if attendance_log is not None else None,
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

            # Preserve onboarding totals in stock.total_boxes. Dynamic sync helper recalculates current_quantity.

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

        # Recalculate dynamic live stock balance and sync caches for all sold SKUs
        from routers.inventory import recalculate_and_sync_sku_stock
        for item in payload.items:
            recalculate_and_sync_sku_stock(
                db=db,
                factory_id=str(factory_id),
                product_size_ml=item.product_size_ml,
                variety=item.variety,
                packaging_size_name=item.packaging_size_name,
            )

        try:
            sold_boxes = sum(int(item.boxes_sold or 0) for item in payload.items)
            log_factory_operation(
                db,
                factory_id=int(factory_id),
                event_type="payment",
                description=f"\U0001F4B0 Sale Logged: Sold {sold_boxes} boxes to {customer.name} - Value: \u20B9{bill_total:,.2f}",
                log_date=payload.date,
                user_id=current_user.id,
                user_role=current_user.role,
                action_type="CREATE",
            )
        except Exception as log_error:
            logger.exception("Suppressed activity log failure for daily sale: %s", log_error)

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


@router.delete("/production/daily/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_daily_production(
    log_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(PRODUCTION_ROLES)),
    db: Session = Depends(get_db),
):
    if current_user.role.lower() == "supervisor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Supervisor role is not authorized to edit or delete operational data",
        )
    assert_owner_delete_permission(current_user)
    production = (
        db.query(DailyProduction)
        .filter(DailyProduction.id == log_id)
        .filter(DailyProduction.factory_id == str(current_user.factory_id))
        .first()
    )
    if production is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Daily production log not found"
        )
    
    product_size_ml = production.product_size_ml
    variety = production.variety
    packaging_size_name = production.packaging_size_name
    factory_id = production.factory_id
    
    try:
        statement = f"Deleted Daily Production Log ID #{log_id} for {product_size_ml}ML {variety} ({packaging_size_name})"
        db.delete(production)
        db.flush()
        
        # Recalculate dynamic live stock balance and sync caches
        from routers.inventory import recalculate_and_sync_sku_stock
        recalculate_and_sync_sku_stock(
            db=db,
            factory_id=str(factory_id),
            product_size_ml=product_size_ml,
            variety=variety,
            packaging_size_name=packaging_size_name,
        )
        
        log_audit_trail(
            db=db,
            factory_id=int(factory_id),
            user_id=current_user.id,
            user_role=current_user.role,
            action_type="DELETE",
            entity_name="Production",
            short_statement=statement,
            event_type="production"
        )
        
        db.commit()

        background_tasks.add_task(
            sync_data_to_n8n_bg,
            factory_id=str(factory_id),
            sync_type="production",
            action="delete",
            data={"log_id": log_id}
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete production log: {exc}"
        )
    return None


class SequenceLogCreate(BaseModel):
    event_type: str
    description: str


class SequenceLogUpdate(BaseModel):
    event_type: str
    description: str


class MachineBreakdownCreate(BaseModel):
    machine_id: int
    issue_category: str
    custom_notes: Optional[str] = None


def _activity_to_dict(log: "ActivityLog") -> dict:
    local_created_at = log.created_at.astimezone(LOCAL_TZ) if log.created_at else None
    return {
        "id": log.id,
        "factory_id": log.factory_id,
        "event_type": log.event_type,
        "description": log.description,
        "log_date": log.log_date.isoformat() if getattr(log, "log_date", None) else None,
        "created_at": local_created_at.isoformat() if local_created_at else None,
        "created_time": local_created_at.strftime("%I:%M %p") if local_created_at else None,
    }


@router.get("/operations/sequence")
def list_sequence_logs(
    date: Optional[str] = None,
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner", "Supervisor"])),
    db: Session = Depends(get_db),
):
    factory_id = current_user.factory_id

    normalized_date = (date or "").strip()
    if normalized_date.lower() in {"null", "undefined", "none"}:
        normalized_date = ""

    if normalized_date:
        try:
            selected_date = datetime.strptime(normalized_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid date format. Expected YYYY-MM-DD",
            )
    else:
        selected_date = datetime.now(LOCAL_TZ).date()

    logs = (
        db.query(ActivityLog)
        .filter(ActivityLog.factory_id == factory_id)
        .filter(ActivityLog.log_date == selected_date)
        .order_by(ActivityLog.created_at.desc())
        .all()
    )
    return [_activity_to_dict(log) for log in logs]


@router.post("/operations/sequence", status_code=status.HTTP_201_CREATED)
def create_sequence_log(
    payload: SequenceLogCreate,
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner", "Supervisor"])),
    db: Session = Depends(get_db),
):
    if not payload.description or not payload.description.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="description must not be empty",
        )
    if not payload.event_type or not payload.event_type.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="event_type must not be empty",
        )

    event_type = payload.event_type.strip()
    if event_type not in VALID_ACTIVITY_EVENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid event_type",
        )

    activity = ActivityLog(
        factory_id=current_user.factory_id,
        event_type=event_type,
        description=payload.description.strip(),
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return _activity_to_dict(activity)


@router.put("/operations/sequence/{log_id}")
def update_sequence_log(
    log_id: int,
    payload: SequenceLogUpdate,
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db),
):
    if not payload.description or not payload.description.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="description must not be empty",
        )
    if not payload.event_type or not payload.event_type.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="event_type must not be empty",
        )

    activity = (
        db.query(ActivityLog)
        .filter(ActivityLog.id == log_id)
        .filter(ActivityLog.factory_id == current_user.factory_id)
        .first()
    )
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity log not found",
        )

    event_type = payload.event_type.strip()
    if event_type not in VALID_ACTIVITY_EVENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid event_type",
        )

    activity.event_type = event_type
    activity.description = payload.description.strip()
    db.commit()
    db.refresh(activity)
    return _activity_to_dict(activity)


@router.delete("/operations/sequence/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sequence_log(
    log_id: int,
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db),
):
    assert_owner_delete_permission(current_user)
    activity = (
        db.query(ActivityLog)
        .filter(ActivityLog.id == log_id)
        .filter(ActivityLog.factory_id == current_user.factory_id)
        .first()
    )
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity log not found",
        )

    db.delete(activity)
    db.commit()
    return None


@router.post("/operations/breakdown", status_code=status.HTTP_201_CREATED)
def report_machine_breakdown(
    payload: MachineBreakdownCreate,
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner", "Supervisor"])),
    db: Session = Depends(get_db),
):
    if not payload.issue_category or not payload.issue_category.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="issue_category must not be empty",
        )

    factory_id = current_user.factory_id
    machine = (
        db.query(Machine)
        .filter(Machine.id == payload.machine_id)
        .filter(Machine.factory_id == factory_id)
        .first()
    )
    if machine is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Machine not found",
        )

    machine_label = machine.name or machine.machine_number or f"ID#{machine.id}"
    desc = f"Machine Breakdown: {machine_label} - {payload.issue_category.strip()}"
    if payload.custom_notes and payload.custom_notes.strip():
        desc += f". Notes: {payload.custom_notes.strip()}"

    activity = ActivityLog(
        factory_id=int(factory_id),
        event_type="machine_telemetry",
        description=desc,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return _activity_to_dict(activity)


@router.get("/activity-logs/daily-sequence")
def get_daily_sequence_logs(
    date: Optional[str] = None,
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner", "Supervisor", "Operator"])),
    db: Session = Depends(get_db),
):
    factory_id = current_user.factory_id
    
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Expected YYYY-MM-DD."
            )
    else:
        target_date = datetime.now(LOCAL_TZ).date()

    start_at = datetime.combine(target_date, time_cls.min, tzinfo=LOCAL_TZ)
    end_at = start_at + timedelta(days=1)
    logs = (
        db.query(ActivityLog)
        .filter(ActivityLog.factory_id == factory_id)
        .filter(ActivityLog.committed_at >= start_at)
        .filter(ActivityLog.committed_at < end_at)
        .order_by(ActivityLog.committed_at.desc(), ActivityLog.id.desc())
        .all()
    )
    
    response_data = []
    for log in logs:
        local_created_at = (log.committed_at or log.created_at).astimezone(LOCAL_TZ) if (log.committed_at or log.created_at) else None
        response_data.append({
            "id": log.id,
            "factory_id": log.factory_id,
            "user_id": log.user_id,
            "user_role": log.user_role or "Owner",
            "action_type": log.action_type or "CREATE",
            "short_statement": log.short_statement or log.description,
            "created_time": local_created_at.strftime("%I:%M %p") if local_created_at else None,
            "timestamp": local_created_at.isoformat() if local_created_at else None,
        })
        
    return response_data


@router.get("/v1/operations/daily-sequence")
def get_daily_sequence_logs_v1(
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner", "Supervisor", "Operator"])),
    db: Session = Depends(get_db),
):
    if (current_user.role or "").strip().lower() == "supervisor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Supervisors are restricted from viewing operational sequence log metrics."
        )
        
    factory_id = current_user.factory_id
    current_time = datetime.now(LOCAL_TZ)
    start_date = (current_time - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)

    # 1. Fetch tracking actions from ActivityLog
    activity_logs = (
        db.query(ActivityLog)
        .filter(ActivityLog.factory_id == factory_id)
        .filter(ActivityLog.created_at >= start_date)
        .all()
    )

    # 2. Fetch tracking actions from AppUsageLog
    app_usage_logs = (
        db.query(AppUsageLog)
        .filter(AppUsageLog.factory_id == factory_id)
        .filter(AppUsageLog.created_at >= start_date)
        .all()
    )

    combined = []

    # Map ActivityLog
    for log in activity_logs:
        local_created_at = log.created_at.astimezone(LOCAL_TZ) if log.created_at else None
        local_date = local_created_at.date() if local_created_at else None
        
        if local_date == current_time.date():
            relative_day = "Today"
        elif local_date == (current_time - timedelta(days=1)).date():
            relative_day = "Yesterday"
        else:
            relative_day = local_date.isoformat() if local_date else "Past Date"

        combined.append({
            "id": log.id,
            "event_type": log.event_type,
            "description": log.description,
            "timestamp": local_created_at.isoformat() if local_created_at else None,
            "created_time": local_created_at.strftime("%I:%M %p") if local_created_at else None,
            "relative_day": relative_day,
            "user_role": log.user_role or "owner",
            "short_statement": log.short_statement or log.description,
            "created_at_obj": log.created_at
        })

    # Map AppUsageLog
    for log in app_usage_logs:
        local_created_at = log.created_at.astimezone(LOCAL_TZ) if log.created_at else None
        local_date = local_created_at.date() if local_created_at else None
        
        if local_date == current_time.date():
            relative_day = "Today"
        elif local_date == (current_time - timedelta(days=1)).date():
            relative_day = "Yesterday"
        else:
            relative_day = local_date.isoformat() if local_date else "Past Date"

        description = log.meta.get("description") if log.meta and isinstance(log.meta, dict) else None
        if not description:
            if log.event_type == "login":
                description = "User logged in to the dashboard."
            elif log.event_type == "signup":
                description = "New user signed up and validated space."
            else:
                description = f"User operation: {log.event_type.replace('_', ' ').capitalize()} in {log.route_or_module or 'system'}."

        combined.append({
            "id": log.id,
            "event_type": "production" if log.event_type not in ["production", "attendance", "expense", "payment", "machine_telemetry"] else log.event_type,
            "description": description,
            "timestamp": local_created_at.isoformat() if local_created_at else None,
            "created_time": local_created_at.strftime("%I:%M %p") if local_created_at else None,
            "relative_day": relative_day,
            "user_role": "owner",
            "short_statement": description,
            "created_at_obj": log.created_at
        })

    # Sort descending by created_at_obj
    combined.sort(key=lambda x: x["created_at_obj"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    for item in combined:
        item.pop("created_at_obj", None)

    return combined


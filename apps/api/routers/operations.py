from datetime import date as date_cls, datetime, time as time_cls, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
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
    ProductionBatch,
    ProductionBatchOutputLine,
    ProductionBatchWorkerLine,
    ShiftWastage,
)
from pydantic import BaseModel, Field, ConfigDict
from routers.payments import customer_phone, send_n8n_whatsapp_event
from schemas import DailyProductionCreate, DailyProductionResponse, DailySaleCreate, DailySaleResponse
from services.activity_logger import log_activity
from services.carton_mapping import normalize_carton_type, parse_allowed_sizes
from services.n8n_sync import sync_data_to_n8n_bg
from services.telegram_action_alerts import (
    notify_production_created,
    notify_production_deleted,
)


router = APIRouter(prefix="/api", tags=["operations"])

MONEY_QUANT = Decimal("0.01")
QTY_QUANT = Decimal("0.001")
VALID_ACTIVITY_EVENT_TYPES = {"production", "attendance", "expense", "payment", "machine_telemetry"}
logger = logging.getLogger(__name__)
LOCAL_TZ = ZoneInfo("Asia/Kolkata")
STOCK_EFFECTIVE_PRODUCTION_STATUSES = ("ACTIVE", "pending_review", "verified")
PRODUCTION_REVERSAL_WINDOW_MINUTES = 30


def to_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def to_qty(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(QTY_QUANT, rounding=ROUND_HALF_UP)


def to_lower(value) -> str:
    return str(value or "").strip().lower()


def normalized_role(user: User) -> str:
    return (getattr(user, "role", "") or "").strip().lower().replace("-", "_")


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


def require_available_stock(material: str, available, required, unit: str) -> None:
    available_value = Decimal(str(available or 0))
    required_value = Decimal(str(required or 0))
    if required_value <= available_value:
        return

    def display(value: Decimal) -> str:
        return format(value.normalize(), "f")

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Insufficient {material} Stock.\n"
            f"Available: {display(available_value)} {unit}\n"
            f"Required: {display(required_value)} {unit}\n"
            "Please update inventory first."
        ),
    )


def mark_worker_present_for_production(
    db: Session,
    *,
    factory_id: str,
    worker: Worker,
    production_date,
    production_qty: int,
) -> Optional[AttendanceLog]:
    from services.attendance_service import upsert_worker_attendance

    attendance_log, created = upsert_worker_attendance(
        db,
        factory_id=factory_id,
        worker=worker,
        attendance_date=production_date,
        attendance_status="Present",
        production_qty=production_qty or 0,
    )

    if created:
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

    logger.info("Automatic attendance marked present for production worker attendance_log_id=%s", attendance_log.id)
    return attendance_log


def _create_daily_production(
    payload: DailyProductionCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(PRODUCTION_ROLES)),
    db: Session = Depends(get_db),
    *,
    commit: bool = True,
    allow_material_fallback: bool = True,
):
    factory_id = str(current_user.factory_id)
    if payload.factory_id and str(payload.factory_id) != factory_id:
        logger.warning("Incoming production payload factory_id ignored in favor of authenticated factory_id")
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
        machine_size_ml = machine.mould_size_ml or machine.cup_size_ml
        if machine_size_ml and int(product_size_ml) != int(machine_size_ml):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "This product cannot be produced on selected machine. "
                    f"Machine size: {machine_size_ml}ml, Product size: {product_size_ml}ml."
                ),
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
        if selected_final_stock is not None:
            selected_packaging = selected_final_stock.packaging_size_name.strip()
            selected_variety = (selected_final_stock.variety or "Standard/White").strip()
            if (
                int(selected_final_stock.product_size_ml) != int(product_size_ml)
                or selected_variety.casefold() != variety.casefold()
                or selected_packaging.casefold() != packaging_size_name.strip().casefold()
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Selected packaging does not belong to the selected product size and variety.",
                )
        carton_type = (
            selected_final_stock.carton_type.strip()
            if selected_final_stock is not None and selected_final_stock.carton_type
            else ""
        )
        if not carton_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inventory mapping incomplete: finished product carton_type is missing.",
            )

        blank_stock = (
            db.query(BlankStock)
            .filter(BlankStock.factory_id == factory_id)
            .filter(BlankStock.blank_size_ml == product_size_ml)
            .filter(sql_func.lower(BlankStock.variety) == to_lower(variety))
            .with_for_update()
            .first()
        )
        if blank_stock is None:
            size_matches = (
                db.query(BlankStock)
                .filter(BlankStock.factory_id == factory_id)
                .filter(BlankStock.blank_size_ml == product_size_ml)
                .with_for_update()
                .all()
            )
            if len(size_matches) == 1:
                blank_stock = size_matches[0]
        requested_blank_bora = to_qty(payload.blank_used_bori)
        requested_bottom_rolls = payload.bottom_used_rolls or 0
        if blank_stock is None:
            raise HTTPException(status_code=400, detail="Inventory mapping incomplete for this SKU.")
        if blank_stock is not None and (
            not blank_stock.weight_per_bora_kg or blank_stock.weight_per_bora_kg <= 0
        ) and requested_blank_bora > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Blank stock weight per bora is not configured for this size. Please update inventory first.",
            )
        machine_bottom_size_mm = (
            blank_stock.linked_bottom_size_mm if blank_stock is not None else machine.bottom_size_mm
        )
        if not machine_bottom_size_mm:
            raise HTTPException(status_code=400, detail="Inventory mapping incomplete for this SKU.")
        if machine.bottom_size_mm and machine.bottom_size_mm != machine_bottom_size_mm:
            raise HTTPException(status_code=400, detail="Inventory mapping incomplete for this SKU.")
        bottom_stock = (
            db.query(BottomStock)
            .filter(BottomStock.factory_id == factory_id)
            .filter(BottomStock.bottom_size_mm == machine_bottom_size_mm)
            .filter(sql_func.lower(BottomStock.variety) == to_lower(variety))
            .with_for_update()
            .first()
        )
        if bottom_stock is None:
            bottom_matches = (
                db.query(BottomStock)
                .filter(BottomStock.factory_id == factory_id)
                .filter(BottomStock.bottom_size_mm == machine_bottom_size_mm)
                .with_for_update()
                .all()
            )
            if len(bottom_matches) == 1:
                bottom_stock = bottom_matches[0]
        if bottom_stock is None:
            raise HTTPException(status_code=400, detail="Inventory mapping incomplete for this SKU.")
        blank_used_bori = requested_blank_bora
        blank_weight_per_bora = to_qty(blank_stock.weight_per_bora_kg if blank_stock is not None else 0)
        if blank_weight_per_bora <= 0 and blank_used_bori > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Blank stock weight per bora is not configured for this size. Please update inventory first.",
            )
        blank_used_kg = to_qty(blank_used_bori * blank_weight_per_bora)

        bottom_used_rolls = requested_bottom_rolls
        bottom_weight_per_roll = Decimal("0.000")
        if bottom_used_rolls > 0:
            if bottom_stock is not None and bottom_stock.bag_weight_kg and bottom_stock.rolls_per_bag and bottom_stock.rolls_per_bag > 0:
                bottom_weight_per_roll = to_qty(Decimal(bottom_stock.bag_weight_kg) / Decimal(bottom_stock.rolls_per_bag))
            elif bottom_stock is not None:
                bottom_weight_per_roll = average_bottom_weight_per_roll(bottom_stock)
        bottom_used_kg = to_qty(Decimal(bottom_used_rolls) * bottom_weight_per_roll)

        # Calculate total pieces produced for BOM fallback
        total_pieces = Decimal(payload.total_boxes_made * payload.packets_per_box_limit + payload.loose_packets_made) * Decimal(payload.pieces_per_packet)

        # 1. Blank Stock BOM Fallback
        if allow_material_fallback and blank_used_kg <= 0 and total_pieces > 0:
            blank_yield = (
                db.query(MaterialYield)
                .filter(MaterialYield.factory_id == factory_id)
                .filter(MaterialYield.material_type == "Blank")
                .filter(MaterialYield.size_ml == product_size_ml)
                .first()
            )
            if blank_yield and blank_yield.pieces_per_kg > 0:
                blank_used_kg = to_qty(total_pieces / Decimal(blank_yield.pieces_per_kg))
                if blank_stock is not None and blank_stock.weight_per_bora_kg and blank_stock.weight_per_bora_kg > 0:
                    blank_used_bori = to_qty(blank_used_kg / Decimal(blank_stock.weight_per_bora_kg))

        # 2. Bottom Stock BOM Fallback
        if allow_material_fallback and bottom_used_kg <= 0 and total_pieces > 0:
            bottom_yield = (
                db.query(MaterialYield)
                .filter(MaterialYield.factory_id == factory_id)
                .filter(MaterialYield.material_type == "Bottom")
                .filter(MaterialYield.size_ml == product_size_ml)
                .first()
            )
            if bottom_yield and bottom_yield.pieces_per_kg > 0:
                bottom_used_kg = to_qty(total_pieces / Decimal(bottom_yield.pieces_per_kg))
                if bottom_stock is not None and bottom_stock.bag_weight_kg and bottom_stock.rolls_per_bag and bottom_stock.rolls_per_bag > 0:
                    bottom_weight_per_roll = Decimal(bottom_stock.bag_weight_kg) / Decimal(bottom_stock.rolls_per_bag)
                    if bottom_weight_per_roll > 0:
                        bottom_used_rolls = int(bottom_used_kg / bottom_weight_per_roll)

        require_available_stock(
            "Blank",
            blank_stock.total_qty_kg if blank_stock is not None else 0,
            blank_used_kg,
            "kg",
        )
        if blank_used_bori > 0:
            available_bora = Decimal(str(blank_stock.total_boras if blank_stock is not None else 0))
            if blank_used_bori > available_bora:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Insufficient blank stock. Available: {format(available_bora.normalize(), 'f')} bora, "
                        f"Required: {format(blank_used_bori.normalize(), 'f')} bora."
                    ),
                )
        require_available_stock(
            "Bottom",
            bottom_stock.total_qty_kg if bottom_stock is not None else 0,
            bottom_used_kg,
            "kg",
        )
        available_rolls = int(bottom_stock.total_rolls if bottom_stock is not None else 0)
        if bottom_used_rolls > available_rolls:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Insufficient bottom stock. Available: {available_rolls} rolls, "
                    f"Required: {bottom_used_rolls} rolls."
                ),
            )

        blank_after = to_qty(blank_stock.total_qty_kg) - blank_used_kg
        bottom_after = to_qty(bottom_stock.total_qty_kg) - bottom_used_kg
        blank_boras_after = to_qty(blank_stock.total_boras) - blank_used_bori if blank_stock.total_boras is not None else None
        bottom_rolls_after = (bottom_stock.total_rolls or 0) - bottom_used_rolls

        final_stock = selected_final_stock
        if final_stock is None:
            final_stock = (
                db.query(FinalProductStock)
                .filter(FinalProductStock.factory_id == factory_id)
                .filter(FinalProductStock.product_restore_key.isnot(None))
                .filter(FinalProductStock.product_size_ml == product_size_ml)
                .filter(sql_func.lower(FinalProductStock.variety) == to_lower(variety))
                .filter(sql_func.lower(FinalProductStock.packaging_size_name) == to_lower(packaging_size_name))
                .with_for_update()
                .first()
            )
        if final_stock is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Finished good variant is not present in the onboarding workbook.",
            )

        from routers.inventory import calculate_live_sku_stock
        total_boxes_before, loose_before = calculate_live_sku_stock(
            db=db,
            factory_id=factory_id,
            product_size_ml=product_size_ml,
            variety=variety,
            packaging_size_name=packaging_size_name,
            onboarding_boxes=final_stock.total_boxes or 0,
            onboarding_loose=final_stock.loose_packets or 0,
            packets_per_box_limit=final_stock.packets_per_box_limit or payload.packets_per_box_limit,
        )
        current_loose = loose_before + payload.loose_packets_made
        boxes_from_loose = current_loose // payload.packets_per_box_limit
        final_loose_packets = current_loose % payload.packets_per_box_limit
        final_total_boxes = total_boxes_before + payload.total_boxes_made + boxes_from_loose
        boxes_packed_this_entry = payload.total_boxes_made + boxes_from_loose

        box_stock = (
            db.query(BoxStock)
            .filter(BoxStock.factory_id == factory_id)
            .filter(sql_func.lower(sql_func.trim(BoxStock.box_type)) == normalize_carton_type(carton_type))
            .with_for_update()
            .first()
        )
        allowed_sizes = parse_allowed_sizes(
            box_stock.size_for_finished_product if box_stock is not None else ""
        )
        if box_stock is None or int(product_size_ml) not in allowed_sizes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"This carton type is not configured for product size {product_size_ml}ml. "
                    f"Add {product_size_ml} to Size For Finished Product for {carton_type}."
                ),
            )
        box_stock_available = box_stock.total_boxes if box_stock is not None else 0
        require_available_stock("Box", box_stock_available, boxes_packed_this_entry, "boxes")
        box_stock_after = box_stock_available - boxes_packed_this_entry
        stock_before_json = {
            "finished_goods": {
                "stock_id": final_stock.id,
                "product_size_ml": product_size_ml,
                "variety": variety,
                "packaging_size_name": packaging_size_name.strip(),
                "boxes": int(total_boxes_before),
                "loose_packets": int(loose_before),
            },
            "blank_stock": {
                "stock_id": blank_stock.id,
                "blank_size_ml": blank_stock.blank_size_ml,
                "variety": blank_stock.variety,
                "total_qty_kg": float(to_qty(blank_stock.total_qty_kg)),
                "total_boras": float(to_qty(blank_stock.total_boras)) if blank_stock.total_boras is not None else None,
            },
            "bottom_stock": {
                "stock_id": bottom_stock.id,
                "bottom_size_mm": bottom_stock.bottom_size_mm,
                "variety": bottom_stock.variety,
                "total_qty_kg": float(to_qty(bottom_stock.total_qty_kg)),
                "total_rolls": int(bottom_stock.total_rolls or 0),
            },
            "box_stock": {
                "stock_id": box_stock.id,
                "box_type": box_stock.box_type,
                "total_boxes": int(box_stock_available or 0),
            },
        }
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
        final_stock.carton_type = carton_type
        final_stock.pieces_per_packet = payload.pieces_per_packet
        final_stock.packets_per_box_limit = payload.packets_per_box_limit
        box_stock.total_boxes = box_stock_after
        box_stock.quantity = box_stock_after

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
            blank_used_bora=blank_used_bori,
            blank_weight_per_bora_kg=blank_weight_per_bora if blank_used_bori > 0 else None,
            blank_used_kg=blank_used_kg,
            bottom_used_rolls=bottom_used_rolls,
            bottom_used_kg=bottom_used_kg,
            wastage_kg=wastage_kg,
            wastage_status=wastage_status,
            total_raw_material_kg=total_raw_material_kg,
            raw_material_cost=raw_material_cost,
            labor_cost=labor_cost,
            electricity_cost=electricity_cost,
            production_cost=production_cost,
            shift=payload.shift,
            status="pending_review",
            created_by_user_id=current_user.id,
            stock_before_json=stock_before_json,
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
        stock_after_json = {
            "finished_goods": {
                **stock_before_json["finished_goods"],
                "boxes": int(live_boxes),
                "loose_packets": int(live_loose),
            },
            "blank_stock": {
                **stock_before_json["blank_stock"],
                "total_qty_kg": float(blank_after),
                "total_boras": float(blank_boras_after) if blank_boras_after is not None else None,
            },
            "bottom_stock": {
                **stock_before_json["bottom_stock"],
                "total_qty_kg": float(bottom_after),
                "total_rolls": int(bottom_rolls_after),
            },
            "box_stock": {
                **stock_before_json["box_stock"],
                "total_boxes": int(box_stock_after),
            },
        }
        production.stock_after_json = stock_after_json

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

        if commit:
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

        # P4.5 D1: action alert to Owner (best-effort, never raises)
        try:
            from models import Machine as _Machine, Factory as _Factory
            _f = db.query(_Factory).filter(_Factory.id == current_user.factory_id).first()
            _m = db.query(_Machine).filter(_Machine.id == production.machine_id).first() if hasattr(production, "machine_id") else None
            if _f is not None:
                notify_production_created(
                    db,
                    factory=_f,
                    actor=current_user,
                    machine_name=getattr(_m, "machine_name", None) or getattr(_m, "name", None) or "—",
                    boxes=int(production.total_boxes or production.boxes_produced or 0),
                )
        except Exception:  # noqa: BLE001
            pass

        return DailyProductionResponse(
            production_id=production.id,
            status=production.status,
            stock_before_json=stock_before_json,
            stock_after_json=stock_after_json,
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


@router.post("/production/daily", response_model=DailyProductionResponse, status_code=status.HTTP_201_CREATED)
@router.post("/production/entry", response_model=DailyProductionResponse, status_code=status.HTTP_201_CREATED)
def create_daily_production(
    payload: DailyProductionCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(PRODUCTION_ROLES)),
    db: Session = Depends(get_db),
):
    return _create_daily_production(payload, background_tasks, current_user, db)


class ProductionBatchOutputCreate(BaseModel):
    finished_good_id: int = Field(..., gt=0)
    boxes_made: int = Field(default=0, ge=0)
    loose_packets_made: int = Field(default=0, ge=0)


class ProductionBatchWorkerCardCreate(BaseModel):
    worker_id: int = Field(..., gt=0)
    blank_used_bora: Decimal = Field(default=Decimal("0.000"), ge=0)
    bottom_used_roll: int = Field(default=0, ge=0)
    note: Optional[str] = Field(default=None, max_length=1000)
    outputs: List[ProductionBatchOutputCreate] = Field(..., min_length=1)


class ProductionBatchCreate(BaseModel):
    date: date_cls
    shift: str = Field(..., min_length=1, max_length=50)
    machine_id: int = Field(..., gt=0)
    worker_cards: List[ProductionBatchWorkerCardCreate] = Field(..., min_length=1)
    shift_wastage_kg: Decimal = Field(default=Decimal("0.000"), ge=0)
    wastage_note: Optional[str] = Field(default=None, max_length=1000)


@router.post("/production/daily-batch", status_code=status.HTTP_201_CREATED)
def create_daily_production_batch(
    payload: ProductionBatchCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(PRODUCTION_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    machine = db.query(Machine).filter(
        Machine.id == payload.machine_id,
        Machine.factory_id == factory_id,
    ).first()
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")
    machine_size = machine.mould_size_ml or machine.cup_size_ml

    duplicate_workers = len({card.worker_id for card in payload.worker_cards}) != len(payload.worker_cards)
    if duplicate_workers:
        raise HTTPException(status_code=400, detail="Each worker can appear only once in a production batch.")
    worker_ids = [card.worker_id for card in payload.worker_cards]
    workers_found = db.query(Worker).filter(
        Worker.factory_id == factory_id,
        Worker.id.in_(worker_ids),
    ).count()
    if workers_found != len(worker_ids):
        raise HTTPException(status_code=404, detail="Worker not found")

    output_ids = [
        output.finished_good_id
        for card in payload.worker_cards
        for output in card.outputs
    ]
    skus = db.query(FinalProductStock).filter(
        FinalProductStock.factory_id == factory_id,
        FinalProductStock.id.in_(output_ids),
    ).with_for_update().all()
    sku_by_id = {sku.id: sku for sku in skus}
    if len(sku_by_id) != len(set(output_ids)):
        raise HTTPException(status_code=404, detail="Finished good SKU not found")
    if not any(
        output.boxes_made or output.loose_packets_made
        for card in payload.worker_cards
        for output in card.outputs
    ):
        raise HTTPException(status_code=400, detail="At least one output line must contain production.")

    carton_requirements: dict[str, int] = {}
    converted_by_sku: dict[int, int] = {}
    remaining_by_sku: dict[int, int] = {}
    totals_by_sku: dict[int, dict[str, int]] = {}
    for card in payload.worker_cards:
        duplicate_outputs = len({output.finished_good_id for output in card.outputs}) != len(card.outputs)
        if duplicate_outputs:
            raise HTTPException(status_code=400, detail="A worker card cannot repeat the same finished good SKU.")
        for output in card.outputs:
            sku = sku_by_id[output.finished_good_id]
            if machine_size and int(machine_size) != int(sku.product_size_ml):
                raise HTTPException(status_code=400, detail="Product size does not match selected machine mould size.")
            if not sku.carton_type:
                raise HTTPException(status_code=400, detail="Inventory mapping incomplete: finished product carton_type is missing.")
            totals = totals_by_sku.setdefault(sku.id, {"boxes": 0, "loose": 0})
            totals["boxes"] += output.boxes_made
            totals["loose"] += output.loose_packets_made

    for sku_id, totals in totals_by_sku.items():
        sku = sku_by_id[sku_id]
        packets_per_box = int(sku.packets_per_box_limit)
        from routers.inventory import calculate_live_sku_stock
        _, loose_before = calculate_live_sku_stock(
            db=db,
            factory_id=factory_id,
            product_size_ml=sku.product_size_ml,
            variety=sku.variety,
            packaging_size_name=sku.packaging_size_name,
            onboarding_boxes=sku.total_boxes or 0,
            onboarding_loose=sku.loose_packets or 0,
            packets_per_box_limit=packets_per_box,
        )
        converted = (loose_before + totals["loose"]) // packets_per_box - (loose_before // packets_per_box)
        converted_by_sku[sku_id] = converted
        remaining_by_sku[sku_id] = (loose_before + totals["loose"]) % packets_per_box
        carton_key = normalize_carton_type(sku.carton_type)
        carton_requirements[carton_key] = carton_requirements.get(carton_key, 0) + totals["boxes"] + converted

    for carton_key, required in carton_requirements.items():
        carton_stock = db.query(BoxStock).filter(
            BoxStock.factory_id == factory_id,
            sql_func.lower(sql_func.trim(BoxStock.box_type)) == carton_key,
        ).with_for_update().first()
        related_sizes = {
            int(sku.product_size_ml)
            for sku in skus
            if normalize_carton_type(sku.carton_type) == carton_key
        }
        allowed_sizes = parse_allowed_sizes(carton_stock.size_for_finished_product if carton_stock else "")
        if carton_stock is None or not related_sizes.issubset(allowed_sizes):
            raise HTTPException(status_code=400, detail="Carton type is not configured for every selected product size.")
        if int(carton_stock.total_boxes or 0) < required:
            raise HTTPException(status_code=400, detail=f"Insufficient Box Stock. Available: {int(carton_stock.total_boxes or 0)}, Required: {required}.")

    total_boxes = sum(value["boxes"] for value in totals_by_sku.values())
    total_loose = sum(value["loose"] for value in totals_by_sku.values())
    total_blank = sum((card.blank_used_bora for card in payload.worker_cards), Decimal("0.000"))
    total_bottom = sum(card.bottom_used_roll for card in payload.worker_cards)
    first_sku = sku_by_id[output_ids[0]]

    batch = ProductionBatch(
        factory_id=factory_id,
        date=payload.date,
        shift=payload.shift.strip(),
        machine_id=machine.id,
        finished_good_id=first_sku.id,
        carton_type="MULTIPLE" if len(carton_requirements) > 1 else first_sku.carton_type,
        total_boxes=total_boxes,
        total_loose_packets=total_loose,
        converted_boxes_from_loose=sum(converted_by_sku.values()),
        remaining_loose_packets=sum(remaining_by_sku.values()),
        total_blank_bora=total_blank,
        total_bottom_roll=total_bottom,
        shift_wastage_kg=payload.shift_wastage_kg,
        wastage_note=payload.wastage_note,
        created_by=current_user.id,
    )
    db.add(batch)
    db.flush()

    responses: list[DailyProductionResponse] = []
    try:
        for worker_card in payload.worker_cards:
            worker_line = ProductionBatchWorkerLine(
                factory_id=factory_id,
                batch_id=batch.id,
                worker_id=worker_card.worker_id,
                boxes_made=sum(output.boxes_made for output in worker_card.outputs),
                loose_packets_made=sum(output.loose_packets_made for output in worker_card.outputs),
                blank_used_bora=worker_card.blank_used_bora,
                bottom_used_roll=worker_card.bottom_used_roll,
                note=worker_card.note,
            )
            db.add(worker_line)
            db.flush()
            for output_index, output in enumerate(worker_card.outputs):
                sku = sku_by_id[output.finished_good_id]
                response = _create_daily_production(
                    DailyProductionCreate(
                        date=payload.date,
                        worker_id=worker_card.worker_id,
                        machine_id=payload.machine_id,
                        product_id=sku.id,
                        product_size_ml=sku.product_size_ml,
                        variety=sku.variety,
                        packaging_size_name=sku.packaging_size_name,
                        pieces_per_packet=sku.pieces_per_packet,
                        packets_per_box_limit=sku.packets_per_box_limit,
                        shift="Night" if payload.shift.strip().casefold() == "night" else "Day",
                        total_boxes_made=output.boxes_made,
                        loose_packets_made=output.loose_packets_made,
                        blank_used_bori=worker_card.blank_used_bora if output_index == 0 else Decimal("0.000"),
                        bottom_used_rolls=worker_card.bottom_used_roll if output_index == 0 else 0,
                        wastage_kg=Decimal("0.000"),
                        remarks=worker_card.note,
                    ),
                    background_tasks,
                    current_user,
                    db,
                    commit=False,
                    allow_material_fallback=False,
                )
                responses.append(response)
                if output_index == 0:
                    worker_line.daily_production_id = response.production_id
                db.add(ProductionBatchOutputLine(
                    factory_id=factory_id,
                    worker_line_id=worker_line.id,
                    finished_good_id=sku.id,
                    daily_production_id=response.production_id,
                    boxes_made=output.boxes_made,
                    loose_packets_made=output.loose_packets_made,
                    boxes_from_loose=response.boxes_from_loose,
                ))
        existing_wastage = db.query(ShiftWastage).filter(
            ShiftWastage.factory_id == factory_id,
            ShiftWastage.date == payload.date,
            ShiftWastage.shift == payload.shift.strip(),
        ).first()
        if existing_wastage is None:
            db.add(ShiftWastage(
                factory_id=factory_id,
                date=payload.date,
                shift=payload.shift.strip(),
                wastage_kg=payload.shift_wastage_kg,
                note=payload.wastage_note,
            ))
        else:
            existing_wastage.wastage_kg = payload.shift_wastage_kg
            existing_wastage.note = payload.wastage_note
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "batch_id": batch.id,
        "worker_line_count": len(payload.worker_cards),
        "output_line_count": len(responses),
        "daily_production_ids": [response.production_id for response in responses],
        "total_boxes_made": total_boxes,
        "total_loose_packets_made": total_loose,
        "converted_boxes_from_loose": sum(converted_by_sku.values()),
        "remaining_loose_packets": sum(remaining_by_sku.values()),
        "finished_boxes_added": total_boxes + sum(converted_by_sku.values()),
        "blank_bora_deducted": float(total_blank),
        "bottom_rolls_deducted": total_bottom,
        "cartons_deducted": sum(carton_requirements.values()),
        "cartons_deducted_by_type": carton_requirements,
        "shift_wastage_kg": float(payload.shift_wastage_kg),
    }


@router.get("/production/daily-batches")
def list_daily_production_batches(
    production_date: Optional[date_cls] = Query(default=None, alias="date"),
    current_user: User = Depends(check_permissions(PRODUCTION_ROLES)),
    db: Session = Depends(get_db),
):
    query = db.query(ProductionBatch).filter(
        ProductionBatch.factory_id == str(current_user.factory_id)
    )
    if production_date is not None:
        query = query.filter(ProductionBatch.date == production_date)
    batches = query.order_by(ProductionBatch.date.desc(), ProductionBatch.created_at.desc()).limit(200).all()
    worker_ids = {
        line.worker_id
        for batch in batches
        for line in batch.worker_lines
        if line.worker_id is not None
    }
    worker_names = {
        worker.id: worker.name
        for worker in db.query(Worker).filter(
            Worker.factory_id == str(current_user.factory_id),
            Worker.id.in_(worker_ids),
        ).all()
    } if worker_ids else {}
    sku_ids = {
        output.finished_good_id
        for batch in batches
        for line in batch.worker_lines
        for output in line.outputs
    }
    sku_by_id = {
        sku.id: sku
        for sku in db.query(FinalProductStock).filter(
            FinalProductStock.factory_id == str(current_user.factory_id),
            FinalProductStock.id.in_(sku_ids),
        ).all()
    } if sku_ids else {}
    return [{
        "id": batch.id,
        "date": batch.date.isoformat(),
        "shift": batch.shift,
        "machine_id": batch.machine_id,
        "finished_good_id": batch.finished_good_id,
        "carton_type": batch.carton_type,
        "total_boxes": batch.total_boxes,
        "total_loose_packets": batch.total_loose_packets,
        "converted_boxes_from_loose": batch.converted_boxes_from_loose,
        "remaining_loose_packets": batch.remaining_loose_packets,
        "total_blank_bora": float(batch.total_blank_bora or 0),
        "total_bottom_roll": batch.total_bottom_roll,
        "shift_wastage_kg": float(batch.shift_wastage_kg or 0),
        "wastage_note": batch.wastage_note,
        "worker_lines": [{
            "id": line.id,
            "worker_id": line.worker_id,
            "worker_name": worker_names.get(line.worker_id, "Unknown worker"),
            "boxes_made": line.boxes_made,
            "loose_packets_made": line.loose_packets_made,
            "blank_used_bora": float(line.blank_used_bora or 0),
            "bottom_used_roll": line.bottom_used_roll,
            "note": line.note,
            "outputs": [{
                "id": output.id,
                "finished_good_id": output.finished_good_id,
                "product_size_ml": sku_by_id[output.finished_good_id].product_size_ml if output.finished_good_id in sku_by_id else None,
                "variety": sku_by_id[output.finished_good_id].variety if output.finished_good_id in sku_by_id else None,
                "packaging_size_name": sku_by_id[output.finished_good_id].packaging_size_name if output.finished_good_id in sku_by_id else None,
                "carton_type": sku_by_id[output.finished_good_id].carton_type if output.finished_good_id in sku_by_id else None,
                "boxes_made": output.boxes_made,
                "loose_packets_made": output.loose_packets_made,
                "boxes_from_loose": output.boxes_from_loose,
                "daily_production_id": output.daily_production_id,
            } for output in line.outputs],
        } for line in batch.worker_lines],
    } for batch in batches]


class ProductionRejectRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class ProductionReverseRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class ProductionUpdateRequest(BaseModel):
    date: Optional[date_cls] = None
    worker_id: Optional[int] = Field(default=None, gt=0)
    machine_id: Optional[int] = Field(default=None, gt=0)
    product_size_ml: Optional[int] = Field(default=None, gt=0)
    product_type: Optional[str] = Field(default=None, min_length=1, max_length=100)
    packaging_size_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    shift: Optional[str] = Field(default=None, pattern="^(Day|Night)$")
    total_boxes_made: Optional[int] = Field(default=None, ge=0)
    loose_packets_made: Optional[int] = Field(default=None, ge=0)


def _production_row(db: Session, factory_id: int, production_id: int) -> DailyProduction:
    row = (
        db.query(DailyProduction)
        .filter(DailyProduction.id == production_id, DailyProduction.factory_id == factory_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Production entry not found")
    return row


def _production_to_dict(db: Session, row: DailyProduction) -> dict:
    worker = db.query(Worker).filter(Worker.id == row.worker_id).first() if row.worker_id else None
    machine = db.query(Machine).filter(Machine.id == row.machine_id).first()
    creator = db.query(User).filter(User.id == row.created_by_user_id).first() if row.created_by_user_id else None
    rejector = db.query(User).filter(User.id == row.rejected_by_user_id).first() if row.rejected_by_user_id else None
    verifier = db.query(User).filter(User.id == row.verified_by_user_id).first() if row.verified_by_user_id else None
    reverser = db.query(User).filter(User.id == row.reversed_by_user_id).first() if row.reversed_by_user_id else None
    quantity_pieces = (
        (int(row.total_boxes_made or 0) + int(row.boxes_from_loose or 0))
        * int(row.packets_per_box_limit or 0)
        + int(row.loose_packets_made or 0)
    )
    return {
        "id": row.id,
        "date": row.date.isoformat(),
        "worker_id": row.worker_id,
        "worker_name": worker.name if worker else "Worker removed",
        "product_size_ml": row.product_size_ml,
        "product_type": row.variety,
        "packaging_size_name": row.packaging_size_name,
        "quantity_boxes": int(row.total_boxes_made or 0) + int(row.boxes_from_loose or 0),
        "loose_packets_made": int(row.loose_packets_made or 0),
        "blank_used_bora": float(row.blank_used_bora or 0),
        "blank_used_kg": float(row.blank_used_kg or 0),
        "blank_weight_per_bora_kg": float(row.blank_weight_per_bora_kg) if row.blank_weight_per_bora_kg is not None else None,
        "bottom_used_rolls": int(row.bottom_used_rolls or 0),
        "quantity_pieces": quantity_pieces,
        "machine_id": row.machine_id,
        "machine_name": (
            getattr(machine, "machine_name", None) or getattr(machine, "name", None) or f"Machine-{row.machine_id}"
        ),
        "shift": row.shift,
        "status": row.status,
        "stock_before_json": row.stock_before_json or {},
        "stock_after_json": row.stock_after_json or {},
        "created_by": creator.full_name or creator.username if creator else None,
        "created_by_user_id": row.created_by_user_id,
        "created_by_role": creator.role if creator else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "verified_by": verifier.full_name or verifier.username if verifier else None,
        "verified_by_user_id": row.verified_by_user_id,
        "verified_at": row.verified_at.isoformat() if row.verified_at else None,
        "reversed_by": reverser.full_name or reverser.username if reverser else None,
        "reversed_by_user_id": row.reversed_by_user_id,
        "reversed_at": row.reversed_at.isoformat() if row.reversed_at else None,
        "reversal_reason": row.reversal_reason,
        "rejected_by": rejector.full_name or rejector.username if rejector else None,
        "rejected_at": row.rejected_at.isoformat() if row.rejected_at else None,
        "rejection_reason": row.rejection_reason,
    }


@router.get("/production/daily")
def list_daily_production(
    production_date: Optional[date_cls] = Query(default=None, alias="date"),
    include_rejected: bool = True,
    current_user: User = Depends(check_permissions(PRODUCTION_ROLES)),
    db: Session = Depends(get_db),
):
    query = db.query(DailyProduction).filter(DailyProduction.factory_id == current_user.factory_id)
    if production_date:
        query = query.filter(DailyProduction.date == production_date)
    if not include_rejected:
        query = query.filter(DailyProduction.status == "ACTIVE")
    rows = query.order_by(DailyProduction.date.desc(), DailyProduction.created_at.desc()).limit(500).all()
    return [_production_to_dict(db, row) for row in rows]


@router.get("/production/worker-summary")
def production_worker_summary(
    production_date: date_cls = Query(default_factory=lambda: datetime.now(LOCAL_TZ).date(), alias="date"),
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(DailyProduction)
        .filter(
            DailyProduction.factory_id == current_user.factory_id,
            DailyProduction.date == production_date,
            DailyProduction.status.in_(STOCK_EFFECTIVE_PRODUCTION_STATUSES),
        )
        .order_by(DailyProduction.worker_id.asc(), DailyProduction.product_size_ml.asc())
        .all()
    )
    grouped: dict[int, dict] = {}
    for row in rows:
        worker_id = int(row.worker_id or 0)
        worker = db.query(Worker).filter(Worker.id == row.worker_id).first() if row.worker_id else None
        item = grouped.setdefault(
            worker_id,
            {
                "worker_id": row.worker_id,
                "worker_name": worker.name if worker else "Worker removed",
                "total_quantity": 0,
                "products": [],
            },
        )
        quantity = int(row.total_boxes_made or 0) + int(row.boxes_from_loose or 0)
        item["total_quantity"] += quantity
        item["products"].append({
            "production_id": row.id,
            "product_size_ml": row.product_size_ml,
            "product_type": row.variety,
            "quantity": quantity,
            "packaging_size_name": row.packaging_size_name,
        })
    return {"date": production_date.isoformat(), "total_quantity": sum(x["total_quantity"] for x in grouped.values()), "workers": list(grouped.values())}


@router.patch("/production/daily/{production_id}")
def update_daily_production(
    production_id: int,
    payload: ProductionUpdateRequest,
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db),
):
    row = _production_row(db, int(current_user.factory_id), production_id)
    if row.status not in STOCK_EFFECTIVE_PRODUCTION_STATUSES or row.status == "verified":
        raise HTTPException(status_code=409, detail="Only unverified active production can be edited")

    old_sku = (row.product_size_ml, row.variety, row.packaging_size_name)
    updates = payload.model_dump(exclude_unset=True)
    if "product_type" in updates:
        updates["variety"] = updates.pop("product_type").strip()
    for field, value in updates.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(row, field, value)
    if (row.total_boxes_made or 0) == 0 and (row.loose_packets_made or 0) == 0:
        raise HTTPException(status_code=422, detail="At least one box or loose packet must be entered")
    db.flush()

    from routers.inventory import recalculate_and_sync_sku_stock
    for size, variety, packaging in {old_sku, (row.product_size_ml, row.variety, row.packaging_size_name)}:
        recalculate_and_sync_sku_stock(db, str(current_user.factory_id), size, variety, packaging)
    log_audit_trail(
        db=db,
        factory_id=int(current_user.factory_id),
        user_id=current_user.id,
        user_role=current_user.role,
        action_type="UPDATE",
        entity_name="Production",
        short_statement=f"Updated production #{row.id}",
        event_type="production",
        log_date=row.date,
    )
    db.commit()
    db.refresh(row)
    return _production_to_dict(db, row)


@router.post("/production/daily/{production_id}/reject")
def reject_daily_production(
    production_id: int,
    payload: ProductionRejectRequest,
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    row = _production_row(db, int(current_user.factory_id), production_id)
    if row.status == "REJECTED":
        return _production_to_dict(db, row)
    if row.status == "verified":
        raise HTTPException(status_code=409, detail="Verified production is finalized and cannot be rejected")

    row.status = "REJECTED"
    row.rejected_by_user_id = current_user.id
    row.rejected_at = datetime.now(timezone.utc)
    row.rejection_reason = payload.reason.strip()
    db.flush()

    from routers.inventory import recalculate_and_sync_sku_stock
    recalculate_and_sync_sku_stock(
        db,
        str(current_user.factory_id),
        row.product_size_ml,
        row.variety,
        row.packaging_size_name,
    )
    log_audit_trail(
        db=db,
        factory_id=int(current_user.factory_id),
        user_id=current_user.id,
        user_role=current_user.role,
        action_type="REJECT",
        entity_name="Production",
        short_statement=f"Rejected production #{row.id}: {payload.reason.strip()}",
        event_type="production",
        log_date=row.date,
    )
    db.commit()
    db.refresh(row)
    return _production_to_dict(db, row)


def _entry_creator_role(db: Session, row: DailyProduction) -> str:
    if not row.created_by_user_id:
        return ""
    creator = db.query(User).filter(User.id == row.created_by_user_id).first()
    return normalized_role(creator) if creator is not None else ""


def _supervisor_latest_reverse_blocker(row: DailyProduction, user: User, db: Session) -> str | None:
    latest = (
        db.query(DailyProduction.id)
        .filter(
            DailyProduction.factory_id == row.factory_id,
            DailyProduction.created_by_user_id == user.id,
            DailyProduction.status.in_(STOCK_EFFECTIVE_PRODUCTION_STATUSES),
        )
        .order_by(DailyProduction.created_at.desc(), DailyProduction.id.desc())
        .first()
    )
    if latest is None or latest[0] != row.id:
        return "Supervisor can reverse only their latest production entry."
    return None


def _reversal_window_blocker(row: DailyProduction) -> str | None:
    created_at = row.created_at
    if created_at is None:
        return "Production entry creation time is missing."
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created_at.astimezone(timezone.utc) > timedelta(minutes=PRODUCTION_REVERSAL_WINDOW_MINUTES):
        return "Supervisor reversal window has expired."
    return None


def can_verify_production_entry(user: User, entry: DailyProduction) -> bool:
    role = normalized_role(user)
    return (
        role in {"owner", "sub_owner"}
        and str(entry.factory_id) == str(user.factory_id)
        and entry.status in STOCK_EFFECTIVE_PRODUCTION_STATUSES
        and entry.status != "verified"
    )


def can_reverse_production_entry(user: User, entry: DailyProduction, db: Session) -> bool:
    if str(entry.factory_id) != str(user.factory_id):
        return False
    if entry.status not in STOCK_EFFECTIVE_PRODUCTION_STATUSES or entry.status == "verified":
        return False
    role = normalized_role(user)
    creator_role = _entry_creator_role(db, entry)
    if role == "owner":
        return True
    if role == "sub_owner":
        return entry.created_by_user_id == user.id or creator_role == "supervisor"
    if role == "supervisor":
        return (
            entry.created_by_user_id == user.id
            and _supervisor_latest_reverse_blocker(entry, user, db) is None
            and _reversal_window_blocker(entry) is None
        )
    return False


def _can_supervisor_reverse(row: DailyProduction, user: User, db: Session) -> None:
    if row.created_by_user_id != user.id:
        raise HTTPException(status_code=403, detail="Supervisor can reverse only their own production entry.")
    if row.verified_at is not None or row.status == "verified":
        raise HTTPException(status_code=403, detail="Verified production cannot be reversed by Supervisor.")
    blocker = _supervisor_latest_reverse_blocker(row, user, db) or _reversal_window_blocker(row)
    if blocker:
        raise HTTPException(status_code=403, detail=blocker)


def _restore_production_stock_effects(db: Session, row: DailyProduction) -> None:
    stock_before = row.stock_before_json or {}
    blank_info = stock_before.get("blank_stock") or {}
    bottom_info = stock_before.get("bottom_stock") or {}
    box_info = stock_before.get("box_stock") or {}

    blank_stock = db.query(BlankStock).filter(
        BlankStock.factory_id == row.factory_id,
        BlankStock.id == blank_info.get("stock_id"),
    ).with_for_update().first()
    if blank_stock is not None:
        blank_stock.total_qty_kg = to_qty(blank_stock.total_qty_kg) + to_qty(row.blank_used_kg)
        if blank_stock.total_boras is not None:
            blank_stock.total_boras = to_qty(blank_stock.total_boras) + to_qty(row.blank_used_bora)

    bottom_stock = db.query(BottomStock).filter(
        BottomStock.factory_id == row.factory_id,
        BottomStock.id == bottom_info.get("stock_id"),
    ).with_for_update().first()
    if bottom_stock is not None:
        bottom_stock.total_qty_kg = to_qty(bottom_stock.total_qty_kg) + to_qty(row.bottom_used_kg)
        bottom_stock.total_weight_kg = to_qty(bottom_stock.total_weight_kg) + to_qty(row.bottom_used_kg)
        bottom_stock.total_rolls = int(bottom_stock.total_rolls or 0) + int(row.bottom_used_rolls or 0)

    box_stock = db.query(BoxStock).filter(
        BoxStock.factory_id == row.factory_id,
        BoxStock.id == box_info.get("stock_id"),
    ).with_for_update().first()
    if box_stock is not None:
        boxes_to_restore = int(row.total_boxes_made or 0) + int(row.boxes_from_loose or 0)
        box_stock.total_boxes = int(box_stock.total_boxes or 0) + boxes_to_restore
        box_stock.quantity = int(box_stock.quantity or 0) + boxes_to_restore


def _adjust_auto_attendance_after_reversal(db: Session, row: DailyProduction) -> None:
    if not row.worker_id:
        return
    other_count = db.query(DailyProduction.id).filter(
        DailyProduction.factory_id == row.factory_id,
        DailyProduction.worker_id == row.worker_id,
        DailyProduction.date == row.date,
        DailyProduction.id != row.id,
        DailyProduction.status.in_(STOCK_EFFECTIVE_PRODUCTION_STATUSES),
    ).count()
    if other_count:
        return
    attendance = db.query(AttendanceLog).filter(
        AttendanceLog.factory_id == row.factory_id,
        AttendanceLog.worker_id == row.worker_id,
        AttendanceLog.date == row.date,
        AttendanceLog.status == "Present",
    ).with_for_update().first()
    if attendance is not None and Decimal(str(attendance.production_qty or 0)) > 0:
        attendance.status = "Absent"
        attendance.is_present = False
        attendance.production_qty = Decimal("0")


def verify_production_entry(entry_id: int, user_id: int, db: Session, *, current_user: User | None = None) -> dict:
    user = current_user or db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if normalized_role(user) not in {"owner", "sub_owner"}:
        raise HTTPException(status_code=403, detail="Only Owner/Sub-owner can verify production.")
    row = _production_row(db, int(user.factory_id), entry_id)
    if not can_verify_production_entry(user, row) and row.status != "verified":
        raise HTTPException(status_code=403, detail="User cannot verify this production entry.")
    if row.status == "reversed":
        raise HTTPException(status_code=409, detail="Reversed production cannot be verified.")
    if row.status == "verified":
        return _production_to_dict(db, row)
    row.status = "verified"
    row.verified_by_user_id = user.id
    row.verified_at = datetime.now(timezone.utc)
    log_audit_trail(
        db=db,
        factory_id=int(user.factory_id),
        user_id=user.id,
        user_role=user.role,
        action_type="VERIFY",
        entity_name="Production",
        short_statement=f"Verified production #{row.id}",
        event_type="production",
        log_date=row.date,
    )
    db.commit()
    db.refresh(row)
    return _production_to_dict(db, row)


def reverse_production_entry(entry_id: int, user_id: int, reason: str, db: Session, *, current_user: User | None = None) -> dict:
    user = current_user or db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    row = _production_row(db, int(user.factory_id), entry_id)
    if row.status == "reversed":
        return _production_to_dict(db, row)
    if row.status not in STOCK_EFFECTIVE_PRODUCTION_STATUSES:
        raise HTTPException(status_code=409, detail="Only stock-effective production can be reversed.")
    role = normalized_role(user)
    clean_reason = (reason or "").strip()
    if len(clean_reason) < 3:
        raise HTTPException(status_code=422, detail="Reversal reason is required.")
    if role == "supervisor":
        _can_supervisor_reverse(row, user, db)
    elif role == "owner":
        if row.status == "verified":
            raise HTTPException(status_code=409, detail="Verified production is finalized and cannot be reversed.")
    elif role == "sub_owner":
        if row.status == "verified":
            raise HTTPException(status_code=409, detail="Verified production is finalized and cannot be reversed.")
        creator_role = _entry_creator_role(db, row)
        if not (row.created_by_user_id == user.id or creator_role == "supervisor"):
            raise HTTPException(status_code=403, detail="Sub-owner can reverse only own or Supervisor production entries.")
    else:
        raise HTTPException(status_code=403, detail="User cannot reverse production.")
    if not can_reverse_production_entry(user, row, db):
        raise HTTPException(status_code=403, detail="User cannot reverse this production entry.")

    _restore_production_stock_effects(db, row)
    row.status = "reversed"
    row.reversed_by_user_id = user.id
    row.reversed_at = datetime.now(timezone.utc)
    row.reversal_reason = clean_reason
    _adjust_auto_attendance_after_reversal(db, row)
    db.flush()

    from routers.inventory import recalculate_and_sync_sku_stock
    recalculate_and_sync_sku_stock(
        db,
        str(user.factory_id),
        row.product_size_ml,
        row.variety,
        row.packaging_size_name,
    )
    log_audit_trail(
        db=db,
        factory_id=int(user.factory_id),
        user_id=user.id,
        user_role=user.role,
        action_type="REVERSE",
        entity_name="Production",
        short_statement=f"Reversed production #{row.id}: {clean_reason}",
        event_type="production",
        log_date=row.date,
    )
    db.commit()
    db.refresh(row)
    return _production_to_dict(db, row)


def list_today_production_entries(
    factory_id: int,
    production_date: date_cls,
    shift: str | None,
    db: Session,
    current_user: User | None = None,
) -> list[dict]:
    query = db.query(DailyProduction).filter(
        DailyProduction.factory_id == str(factory_id),
        DailyProduction.date == production_date,
    )
    if shift:
        query = query.filter(sql_func.lower(DailyProduction.shift) == shift.strip().lower())
    rows = query.order_by(DailyProduction.created_at.desc(), DailyProduction.id.desc()).all()
    if current_user is None:
        return [_production_to_dict(db, row) for row in rows]
    return [_production_review_to_dict(db, row, current_user) for row in rows]


@router.post("/production/daily/{production_id}/verify")
def verify_daily_production(
    production_id: int,
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db),
):
    return verify_production_entry(production_id, current_user.id, db, current_user=current_user)


@router.post("/production/daily/{production_id}/reverse")
def reverse_daily_production(
    production_id: int,
    payload: ProductionReverseRequest,
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner", "Supervisor"])),
    db: Session = Depends(get_db),
):
    return reverse_production_entry(production_id, current_user.id, payload.reason, db, current_user=current_user)


@router.get("/production/review")
def list_production_review_entries(
    production_date: date_cls = Query(default_factory=lambda: datetime.now(LOCAL_TZ).date(), alias="date"),
    shift: Optional[str] = Query(default=None),
    current_user: User = Depends(check_permissions(PRODUCTION_ROLES)),
    db: Session = Depends(get_db),
):
    return {
        "date": production_date.isoformat(),
        "shift": shift,
        "entries": list_today_production_entries(
            int(current_user.factory_id),
            production_date,
            shift,
            db,
            current_user=current_user,
        ),
    }


def _production_review_to_dict(db: Session, row: DailyProduction, user: User) -> dict:
    item = _production_to_dict(db, row)
    item["allowed_actions"] = {
        "can_reverse": can_reverse_production_entry(user, row, db),
        "can_verify": can_verify_production_entry(user, row),
        "reason_required": True,
    }
    return item


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
                .filter(FinalProductStock.product_restore_key.isnot(None))
                .filter(FinalProductStock.product_size_ml == item.product_size_ml)
                .filter(sql_func.lower(FinalProductStock.variety) == item.variety.lower())
                .filter(sql_func.lower(FinalProductStock.packaging_size_name) == item.packaging_size_name.lower())
                .with_for_update()
                .first()
            )
            if stock is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Finished good variant is not present in the onboarding workbook.",
                )

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

        # P4.5 D1: action alert to Owner (best-effort, never raises)
        try:
            from models import Machine as _Machine, Factory as _Factory
            _f = db.query(_Factory).filter(_Factory.id == current_user.factory_id).first()
            _m = db.query(_Machine).filter(_Machine.id == production.machine_id).first() if hasattr(production, "machine_id") else None
            if _f is not None:
                notify_production_deleted(
                    db,
                    factory=_f,
                    actor=current_user,
                    machine_name=getattr(_m, "machine_name", None) or getattr(_m, "name", None) or "—",
                    boxes=int(production.total_boxes or production.boxes_produced or 0),
                )
        except Exception:  # noqa: BLE001
            pass

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


class ShiftWastageCreate(BaseModel):
    date: date_cls
    shift: str = Field(..., min_length=1, max_length=50)
    wastage_kg: Decimal = Field(..., ge=0)
    note: Optional[str] = Field(default=None, max_length=1000)


class ShiftWastageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    factory_id: int
    date: date_cls
    shift: str
    wastage_kg: float
    note: Optional[str] = None


@router.post("/production/wastage", response_model=ShiftWastageResponse, status_code=status.HTTP_201_CREATED)
def save_shift_wastage(
    payload: ShiftWastageCreate,
    current_user: User = Depends(check_permissions(PRODUCTION_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    existing = (
        db.query(ShiftWastage)
        .filter(
            ShiftWastage.factory_id == factory_id,
            ShiftWastage.date == payload.date,
            ShiftWastage.shift == payload.shift.strip()
        )
        .first()
    )
    if existing:
        existing.wastage_kg = payload.wastage_kg
        existing.note = payload.note
        db.commit()
        db.refresh(existing)
        return existing

    new_row = ShiftWastage(
        factory_id=factory_id,
        date=payload.date,
        shift=payload.shift.strip(),
        wastage_kg=payload.wastage_kg,
        note=payload.note
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)
    return new_row


@router.get("/production/wastage", response_model=Optional[ShiftWastageResponse])
def get_shift_wastage(
    date: date_cls = Query(...),
    shift: str = Query(...),
    current_user: User = Depends(check_permissions(PRODUCTION_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    row = (
        db.query(ShiftWastage)
        .filter(
            ShiftWastage.factory_id == factory_id,
            ShiftWastage.date == date,
            ShiftWastage.shift == shift.strip()
        )
        .first()
    )
    return row


class ShiftWastageSummaryResponse(BaseModel):
    date: date_cls
    day_wastage_kg: Decimal = Decimal("0.0")
    night_wastage_kg: Decimal = Decimal("0.0")
    total_wastage_kg: Decimal = Decimal("0.0")
    notes: List[str] = Field(default_factory=list)


def get_wastage_summary(factory_id: str, date_val: date_cls, db: Session) -> dict:
    rows = (
        db.query(ShiftWastage)
        .filter(
            ShiftWastage.factory_id == str(factory_id),
            ShiftWastage.date == date_val
        )
        .all()
    )
    day = Decimal("0.0")
    night = Decimal("0.0")
    notes = []
    for r in rows:
        val = Decimal(str(r.wastage_kg or 0))
        if r.shift.strip().lower() == "day":
            day = val
        elif r.shift.strip().lower() == "night":
            night = val
        if r.note and r.note.strip():
            notes.append(f"{r.shift}: {r.note.strip()}")
    return {
        "date": date_val,
        "day_wastage_kg": day,
        "night_wastage_kg": night,
        "total_wastage_kg": day + night,
        "notes": notes
    }


@router.get("/production/wastage/summary", response_model=ShiftWastageSummaryResponse)
def get_shift_wastage_summary(
    date: date_cls = Query(...),
    current_user: User = Depends(check_permissions(PRODUCTION_ROLES)),
    db: Session = Depends(get_db),
):
    return get_wastage_summary(str(current_user.factory_id), date, db)


class DailyWastageSummaryRow(BaseModel):
    date: date_cls
    wastage_kg: Decimal


class ShiftWastageWeeklySummaryResponse(BaseModel):
    start_date: date_cls
    end_date: date_cls
    daily_totals: List[DailyWastageSummaryRow]
    weekly_total_kg: Decimal


@router.get("/production/wastage/weekly-summary", response_model=ShiftWastageWeeklySummaryResponse)
def get_shift_wastage_weekly_summary(
    start_date: date_cls = Query(...),
    end_date: date_cls = Query(...),
    current_user: User = Depends(check_permissions(PRODUCTION_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    rows = (
        db.query(ShiftWastage)
        .filter(
            ShiftWastage.factory_id == factory_id,
            ShiftWastage.date >= start_date,
            ShiftWastage.date <= end_date
        )
        .all()
    )
    by_date = {}
    curr = start_date
    while curr <= end_date:
        by_date[curr] = Decimal("0.0")
        curr += timedelta(days=1)
        
    for r in rows:
        by_date[r.date] = by_date.get(r.date, Decimal("0.0")) + Decimal(str(r.wastage_kg or 0))
        
    daily_totals = [DailyWastageSummaryRow(date=d, wastage_kg=v) for d, v in sorted(by_date.items())]
    weekly_total_kg = sum((item.wastage_kg for item in daily_totals), Decimal("0.0"))
    
    return ShiftWastageWeeklySummaryResponse(
        start_date=start_date,
        end_date=end_date,
        daily_totals=daily_totals,
        weekly_total_kg=weekly_total_kg
    )

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import get_current_user
from db import get_db
from models import (
    CostingMaster,
    CostingOutputMaster,
    FactorySettings,
    Machine,
    MaterialYield,
    PackagingMetrics,
    RawMaterialMetrics,
    User,
)
from schemas import CalculateCostRequest, CalculateCostResponse, DailyCapacityResponse


router = APIRouter(prefix="/api/calculator", tags=["calculator"])

WASTAGE_FACTOR = Decimal("1.02")
MONEY_QUANT = Decimal("0.01")
PIECE_QUANT = Decimal("0.0001")


def to_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def to_piece(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(PIECE_QUANT, rounding=ROUND_HALF_UP)


# =============================================================================
# LEGACY PROFIT CALCULATOR (Backward Compatible)
# =============================================================================

class ProfitCalculatorRequest:
    pass


@router.post("/profit")
def calculate_profit_legacy():
    # Placeholder to avoid breaking imports; actual legacy endpoint is in main.py
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Use /api/calculator/calculate-cost")


# =============================================================================
# LEVEL 4 — MASTER COSTING CALCULATOR
# =============================================================================

@router.post("/calculate-cost", response_model=CalculateCostResponse)
def calculate_cost(
    payload: CalculateCostRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    factory_id = current_user.factory_id

    blank_metric = (
        db.query(RawMaterialMetrics)
        .filter(RawMaterialMetrics.factory_id == factory_id)
        .filter(RawMaterialMetrics.id == payload.blank_metric_id)
        .first()
    )
    if blank_metric is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blank metric not found")

    bottom_metric = (
        db.query(RawMaterialMetrics)
        .filter(RawMaterialMetrics.factory_id == factory_id)
        .filter(RawMaterialMetrics.id == payload.bottom_metric_id)
        .first()
    )
    if bottom_metric is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bottom metric not found")

    packaging_metric = (
        db.query(PackagingMetrics)
        .filter(PackagingMetrics.factory_id == factory_id)
        .filter(PackagingMetrics.id == payload.packaging_metric_id)
        .first()
    )
    if packaging_metric is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Packaging metric not found")

    costing = db.query(CostingMaster).filter(CostingMaster.factory_id == factory_id).first()
    if costing is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Costing master is not configured for this factory",
        )

    # ----- Cost Calculations -----
    blank_weight_per_piece = Decimal(blank_metric.weight_per_sack_kg) / Decimal(blank_metric.pieces_per_sack)
    bottom_weight_per_piece = Decimal(bottom_metric.weight_per_sack_kg) / Decimal(bottom_metric.pieces_per_sack)

    blank_cost_per_piece = to_money(Decimal(costing.paper_price_per_kg) * blank_weight_per_piece)
    bottom_cost_per_piece = to_money(Decimal(costing.bottom_roll_price_per_kg) * bottom_weight_per_piece)

    # Apply generic wastage factor to raw material
    material_cost_per_piece = (blank_cost_per_piece + bottom_cost_per_piece) * WASTAGE_FACTOR

    cups_per_box = packaging_metric.cups_per_box
    raw_material_cost_per_box = to_money(material_cost_per_piece * Decimal(cups_per_box))

    labour_electricity_per_box = to_money(costing.labour_cost_per_box + costing.electricity_cost_per_box)
    total_cost_price_per_box = to_money(raw_material_cost_per_box + labour_electricity_per_box)

    cost_per_piece = to_piece(total_cost_price_per_box / Decimal(cups_per_box))
    selling_price_per_box = to_money(payload.selling_price_per_box)
    selling_price_per_piece = to_piece(selling_price_per_box / Decimal(cups_per_box))
    profit_per_box = to_money(selling_price_per_box - total_cost_price_per_box)
    profit_per_piece = to_piece(profit_per_box / Decimal(cups_per_box))

    # ----- Persist Snapshot -----
    snapshot = CostingOutputMaster(
        factory_id=factory_id,
        product_cup_size_ml=packaging_metric.cup_size_ml,
        selected_blank_metric_id=blank_metric.id,
        selected_bottom_metric_id=bottom_metric.id,
        selected_packaging_metric_id=packaging_metric.id,
        total_cost_price_per_box=total_cost_price_per_box,
        cost_per_piece=cost_per_piece,
        selling_price_per_box=selling_price_per_box,
        selling_price_per_piece=selling_price_per_piece,
        profit_per_box=profit_per_box,
        profit_per_piece=profit_per_piece,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    return CalculateCostResponse(
        id=snapshot.id,
        factory_id=snapshot.factory_id,
        product_cup_size_ml=snapshot.product_cup_size_ml,
        total_cost_price_per_box=snapshot.total_cost_price_per_box,
        cost_per_piece=snapshot.cost_per_piece,
        selling_price_per_box=snapshot.selling_price_per_box,
        selling_price_per_piece=snapshot.selling_price_per_piece,
        profit_per_box=snapshot.profit_per_box,
        profit_per_piece=snapshot.profit_per_piece,
    )


# =============================================================================
# UTILITY: Daily Capacity Estimator
# =============================================================================

def calculate_daily_capacity(
    db: Session,
    machine_id: int,
    factory_id: int,
) -> DailyCapacityResponse:
    machine = (
        db.query(Machine)
        .filter(Machine.factory_id == factory_id)
        .filter(Machine.id == machine_id)
        .first()
    )
    if machine is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")

    settings = db.query(FactorySettings).filter(FactorySettings.factory_id == factory_id).first()
    shift_hours = settings.default_shift_hours if settings else 8.0

    total_cups = int(machine.speed_cups_per_minute * 60 * shift_hours)

    blank_metric = (
        db.query(RawMaterialMetrics)
        .filter(RawMaterialMetrics.factory_id == factory_id)
        .filter(RawMaterialMetrics.material_type == "Blank")
        .filter(RawMaterialMetrics.size_ml_or_mm == machine.cup_size_ml)
        .first()
    )
    bottom_metric = (
        db.query(RawMaterialMetrics)
        .filter(RawMaterialMetrics.factory_id == factory_id)
        .filter(RawMaterialMetrics.material_type == "Bottom")
        .filter(RawMaterialMetrics.size_ml_or_mm == machine.bottom_size_mm)
        .first()
    )

    blank_sacks = Decimal("0")
    if blank_metric and blank_metric.pieces_per_sack:
        blank_sacks = Decimal(total_cups) / Decimal(blank_metric.pieces_per_sack)

    bottom_sacks = Decimal("0")
    if bottom_metric and bottom_metric.pieces_per_sack:
        bottom_sacks = Decimal(total_cups) / Decimal(bottom_metric.pieces_per_sack)

    return DailyCapacityResponse(
        machine_id=machine.id,
        machine_sequence_number=machine.machine_sequence_number or "N/A",
        speed_cups_per_minute=machine.speed_cups_per_minute,
        shift_hours=shift_hours,
        total_cups_per_day=total_cups,
        estimated_blank_sacks_needed=blank_sacks.quantize(Decimal("0.01")),
        estimated_bottom_sacks_needed=bottom_sacks.quantize(Decimal("0.01")),
    )


@router.get("/daily-capacity/{machine_id}", response_model=DailyCapacityResponse)
def get_daily_capacity(
    machine_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return calculate_daily_capacity(db, machine_id, current_user.factory_id)

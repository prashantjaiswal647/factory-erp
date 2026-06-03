import json
import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from ai_agent import initialize_groq_llm
from dependencies import OWNER_ROLES, check_permissions
from db import get_db
from models import DailyProduction, FinalProductStock, User


router = APIRouter(prefix="/api/calculator", tags=["calculator"])
logger = logging.getLogger(__name__)

MONEY_QUANT = Decimal("0.01")
PIECE_QUANT = Decimal("0.0001")


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def piece(value: Decimal) -> Decimal:
    return Decimal(value).quantize(PIECE_QUANT, rounding=ROUND_HALF_UP)


def resolve_box_cost(
    direct_value: Optional[Decimal],
    per_piece_value: Optional[Decimal],
    pieces_per_box: int,
    label: str,
) -> Decimal:
    if direct_value is not None:
        return money(direct_value)
    if per_piece_value is not None:
        return money(per_piece_value * Decimal(pieces_per_box))
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Provide either {label}_price_per_box or {label}_cost_per_piece",
    )


class IdealCostRequest(BaseModel):
    blank_size_ml: int = Field(..., gt=0)
    pieces_per_box: int = Field(default=1000, gt=0)
    yield_pieces_per_kg_blank: Decimal = Field(..., gt=0)
    blank_price_per_kg: Decimal = Field(..., ge=0)
    bottom_price_per_kg: Optional[Decimal] = Field(default=None, ge=0)
    bottom_yield_pieces_per_kg: Optional[Decimal] = Field(default=None, gt=0)
    direct_bottom_cost_per_cup: Optional[Decimal] = Field(default=None, ge=0)
    daily_labor_cost: Decimal = Field(..., ge=0)
    expected_daily_production_pieces: Decimal = Field(..., gt=0)
    packaging_box_price: Optional[Decimal] = Field(default=None, ge=0)
    packaging_cost_per_piece: Optional[Decimal] = Field(default=None, ge=0)
    plastic_price_per_box: Optional[Decimal] = Field(default=None, ge=0)
    plastic_price_per_piece: Optional[Decimal] = Field(default=None, ge=0)
    electricity_flat_cost_per_box: Optional[Decimal] = Field(default=None, ge=0)
    electricity_cost_per_piece: Optional[Decimal] = Field(default=None, ge=0)
    desired_profit_per_box: Decimal = Field(..., ge=0)


class IdealCostResponse(BaseModel):
    blank_size_ml: int
    pieces_per_box: int
    per_piece_blank_cost: Decimal
    per_piece_bottom_cost: Decimal
    labor_cost_per_piece: Decimal
    total_raw_cost_per_box: Decimal
    packaging_box_price: Decimal
    plastic_price_per_box: Decimal
    electricity_flat_cost_per_box: Decimal
    final_cost_per_box: Decimal
    desired_profit_per_box: Decimal
    suggested_selling_price: Decimal
    profit_margin_percent: Decimal
    breakdown: Dict[str, Decimal]


class ComparisonRow(BaseModel):
    metric: str
    ideal_value: str
    actual_value: str
    difference: str


class AiCompareRequest(BaseModel):
    ideal_calculation_results: Dict[str, Any]
    actual_monthly_data: Optional[Dict[str, Any]] = None


class AiCompareResponse(BaseModel):
    ai_insights: str
    comparison_table_data: List[ComparisonRow]
    actual_monthly_data: Dict[str, Any]


@router.post("/ideal-cost", response_model=IdealCostResponse)
def calculate_ideal_cost(
    payload: IdealCostRequest,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
):
    per_piece_blank_cost = piece(payload.blank_price_per_kg / payload.yield_pieces_per_kg_blank)
    if payload.direct_bottom_cost_per_cup is not None:
        per_piece_bottom_cost = piece(payload.direct_bottom_cost_per_cup)
    else:
        if payload.bottom_price_per_kg is None or payload.bottom_yield_pieces_per_kg is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Provide either direct_bottom_cost_per_cup or both bottom_price_per_kg and bottom_yield_pieces_per_kg",
            )
        per_piece_bottom_cost = piece(payload.bottom_price_per_kg / payload.bottom_yield_pieces_per_kg)
    packaging_box_price = resolve_box_cost(
        direct_value=payload.packaging_box_price,
        per_piece_value=payload.packaging_cost_per_piece,
        pieces_per_box=payload.pieces_per_box,
        label="packaging",
    )
    plastic_price_per_box = resolve_box_cost(
        direct_value=payload.plastic_price_per_box,
        per_piece_value=payload.plastic_price_per_piece,
        pieces_per_box=payload.pieces_per_box,
        label="plastic",
    )
    electricity_cost_per_box = resolve_box_cost(
        direct_value=payload.electricity_flat_cost_per_box,
        per_piece_value=payload.electricity_cost_per_piece,
        pieces_per_box=payload.pieces_per_box,
        label="electricity",
    )
    labor_cost_per_piece = piece(payload.daily_labor_cost / payload.expected_daily_production_pieces)
    total_raw_cost_per_box = money(
        (per_piece_blank_cost + per_piece_bottom_cost + labor_cost_per_piece)
        * Decimal(payload.pieces_per_box)
    )
    final_cost_per_box = money(
        total_raw_cost_per_box
        + packaging_box_price
        + plastic_price_per_box
        + electricity_cost_per_box
    )
    suggested_selling_price = money(final_cost_per_box + payload.desired_profit_per_box)
    profit_margin_percent = Decimal("0.00")
    if suggested_selling_price > 0:
        profit_margin_percent = money((payload.desired_profit_per_box / suggested_selling_price) * Decimal("100"))

    return IdealCostResponse(
        blank_size_ml=payload.blank_size_ml,
        pieces_per_box=payload.pieces_per_box,
        per_piece_blank_cost=per_piece_blank_cost,
        per_piece_bottom_cost=per_piece_bottom_cost,
        labor_cost_per_piece=labor_cost_per_piece,
        total_raw_cost_per_box=total_raw_cost_per_box,
        packaging_box_price=money(packaging_box_price),
        plastic_price_per_box=money(plastic_price_per_box),
        electricity_flat_cost_per_box=money(electricity_cost_per_box),
        final_cost_per_box=final_cost_per_box,
        desired_profit_per_box=money(payload.desired_profit_per_box),
        suggested_selling_price=suggested_selling_price,
        profit_margin_percent=profit_margin_percent,
        breakdown={
            "blank_cost_per_box": money(per_piece_blank_cost * Decimal(payload.pieces_per_box)),
            "bottom_cost_per_box": money(per_piece_bottom_cost * Decimal(payload.pieces_per_box)),
            "labor_cost_per_box": money(labor_cost_per_piece * Decimal(payload.pieces_per_box)),
            "packaging_box_price": money(packaging_box_price),
            "plastic_price_per_box": money(plastic_price_per_box),
            "electricity_flat_cost_per_box": money(electricity_cost_per_box),
        },
    )


@router.post("/ai-compare", response_model=AiCompareResponse)
def compare_ideal_vs_actual(
    payload: AiCompareRequest,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = current_user.factory_id
    actual_data = payload.actual_monthly_data or build_actual_monthly_data(db, factory_id)
    ideal = payload.ideal_calculation_results
    comparison_rows = build_comparison_rows(ideal, actual_data)
    ai_insights = generate_ai_insights(ideal, actual_data, comparison_rows)
    return AiCompareResponse(
        ai_insights=ai_insights,
        comparison_table_data=comparison_rows,
        actual_monthly_data=actual_data,
    )


@router.get("/actual-monthly")
def get_actual_monthly_data(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    return build_actual_monthly_data(db, current_user.factory_id)


def build_actual_monthly_data(db: Session, factory_id: int) -> Dict[str, Any]:
    month_start = date.today().replace(day=1)
    production_rows = (
        db.query(DailyProduction)
        .filter(DailyProduction.factory_id == factory_id)
        .filter(DailyProduction.date >= month_start)
        .all()
    )
    total_boxes = sum(row.total_boxes_made or 0 for row in production_rows)
    total_loose_packets = sum(row.loose_packets_made or 0 for row in production_rows)
    boxes_from_loose = sum(row.boxes_from_loose or 0 for row in production_rows)
    blank_used_kg = sum(Decimal(row.blank_used_kg or 0) for row in production_rows)
    bottom_used_kg = sum(Decimal(row.bottom_used_kg or 0) for row in production_rows)
    estimated_pieces = sum(
        Decimal((row.total_boxes_made or 0) * (row.packets_per_box_limit or 0) + (row.loose_packets_made or 0))
        for row in production_rows
    )
    final_stock_boxes = (
        db.query(sql_func.coalesce(sql_func.sum(FinalProductStock.total_boxes), 0))
        .filter(FinalProductStock.factory_id == factory_id)
        .scalar()
        or 0
    )

    actual_blank_kg_per_box = Decimal("0")
    actual_bottom_kg_per_box = Decimal("0")
    if total_boxes > 0:
        actual_blank_kg_per_box = blank_used_kg / Decimal(total_boxes)
        actual_bottom_kg_per_box = bottom_used_kg / Decimal(total_boxes)

    return {
        "month_start": month_start.isoformat(),
        "production_entries": len(production_rows),
        "actual_boxes_made": total_boxes,
        "loose_packets_made": total_loose_packets,
        "boxes_from_loose": boxes_from_loose,
        "estimated_pieces_made": int(estimated_pieces),
        "blank_used_kg": float(blank_used_kg),
        "bottom_used_kg": float(bottom_used_kg),
        "actual_blank_kg_per_box": float(actual_blank_kg_per_box.quantize(Decimal("0.001"))),
        "actual_bottom_kg_per_box": float(actual_bottom_kg_per_box.quantize(Decimal("0.001"))),
        "final_stock_boxes": int(final_stock_boxes),
    }


def build_comparison_rows(ideal: Dict[str, Any], actual: Dict[str, Any]) -> List[ComparisonRow]:
    final_cost = Decimal(str(ideal.get("final_cost_per_box", 0)))
    suggested_price = Decimal(str(ideal.get("suggested_selling_price", 0)))
    desired_profit = Decimal(str(ideal.get("desired_profit_per_box", 0)))
    boxes = Decimal(str(actual.get("actual_boxes_made", 0)))
    blank_kg_per_box = Decimal(str(actual.get("actual_blank_kg_per_box", 0)))
    bottom_kg_per_box = Decimal(str(actual.get("actual_bottom_kg_per_box", 0)))

    return [
        ComparisonRow(metric="Cost per box", ideal_value=f"₹{final_cost}", actual_value="Needs sales costing data", difference="Track via monthly sale rates"),
        ComparisonRow(metric="Selling price per box", ideal_value=f"₹{suggested_price}", actual_value="Not available in production table", difference="Connect sales average next"),
        ComparisonRow(metric="Profit per box", ideal_value=f"₹{desired_profit}", actual_value="Not available", difference="Depends on actual sale price"),
        ComparisonRow(metric="Monthly boxes made", ideal_value="As per production plan", actual_value=str(int(boxes)), difference=f"{int(boxes)} boxes recorded"),
        ComparisonRow(metric="Blank usage per box", ideal_value="Ideal yield based", actual_value=f"{blank_kg_per_box} kg/box", difference="Higher value means blank wastage or low yield"),
        ComparisonRow(metric="Bottom usage per box", ideal_value="Ideal yield based", actual_value=f"{bottom_kg_per_box} kg/box", difference="Higher value means bottom wastage"),
    ]


def generate_ai_insights(ideal: Dict[str, Any], actual: Dict[str, Any], rows: List[ComparisonRow]) -> str:
    fallback = (
        "Ideal cost aur actual production data compare karne par primary focus raw material usage per box, "
        "monthly boxes output, aur actual selling rate tracking par hona chahiye. Agar blank/bottom kg per box "
        "ideal se upar ja raha hai to wastage, machine setting, ya operator handling review karein. Sales average "
        "rate connect karne ke baad exact profit leakage aur recovery clear dikhegi."
    )
    llm = initialize_groq_llm()
    if llm is None:
        return fallback

    prompt = (
        "You are a Factory Financial Analyst. Compare the theoretical ideal cost per box with the actual monthly "
        "production data. Highlight where we lost money, such as high wastage or low speed, or gained profit. "
        "Keep it strictly professional, in Hinglish. Return only one concise paragraph.\n\n"
        f"Ideal calculation JSON:\n{json.dumps(ideal, default=str)}\n\n"
        f"Actual monthly data JSON:\n{json.dumps(actual, default=str)}\n\n"
        f"Comparison rows JSON:\n{json.dumps([row.model_dump() for row in rows], default=str)}"
    )
    try:
        response = llm.invoke(prompt)
        return str(getattr(response, "content", response)).strip() or fallback
    except Exception as exc:
        logger.warning("AI comparison insight generation failed", exc_info=True)
        return fallback


def calculate_daily_capacity(*_args, **_kwargs):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="Daily capacity calculator has moved to production planning.")


@router.get("/daily-capacity/{machine_id}")
def get_daily_capacity(machine_id: int):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="Daily capacity calculator has moved to production planning.")

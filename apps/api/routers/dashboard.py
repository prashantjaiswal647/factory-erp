import json
import os
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends
from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from ai_agent import initialize_groq_llm
from dependencies import OWNER_ROLES, check_permissions
from db import get_db
from models import BlankStock, BottomStock, BoxStock, Customer, DailyProduction, DailySale, Payment, User


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
MONEY_QUANT = Decimal("0.01")


def to_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


class AiDashboardStats(BaseModel):
    total_sales_last_7_days: Decimal
    total_collection_last_7_days: Decimal
    current_total_market_outstanding: Decimal
    average_wastage_percent_last_7_days: Decimal
    raw_material_low_stock_alerts: int


class AiInsightsResponse(BaseModel):
    stats: AiDashboardStats
    insights: str
    source: str


def fallback_insights(stats: dict) -> str:
    return (
        f"1. Malik, last 7 din ki sale Rs {stats['total_sales_last_7_days']} aur collection Rs {stats['total_collection_last_7_days']} hai; collection ko daily follow-up se tight rakhiye.\n"
        f"2. Malik, market outstanding Rs {stats['current_total_market_outstanding']} hai; bade udhaar walon ko aaj reminder bhejna sahi rahega.\n"
        f"3. Malik, average wastage {stats['average_wastage_percent_last_7_days']}% hai; agar yeh 2% se upar rahe to machine setting aur raw material handling check karein."
    )


def generate_llm_insights(stats: dict) -> tuple[str, str]:
    system_prompt = (
        "You are Munshi AI, a loyal, sharp, and traditional Indian accountant for a paper cup factory. "
        "Based on the provided JSON stats, give exactly 3 short, actionable insights or warnings in friendly "
        "business Hinglish (Hindi written in English alphabet). Address the user as Malik."
    )
    user_prompt = f"Stats JSON:\n{json.dumps(stats, default=str)}"

    llm = initialize_groq_llm()
    if llm is not None:
        try:
            response = llm.invoke(f"{system_prompt}\n\n{user_prompt}")
            text = str(getattr(response, "content", response)).strip()
            if text:
                return text, "groq"
        except Exception as exc:
            print(f"DASHBOARD GROQ ERROR: {exc}")

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            client = OpenAI(api_key=openai_key)
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL") or "gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
            )
            text = response.choices[0].message.content or ""
            if text.strip():
                return text.strip(), "openai"
        except Exception as exc:
            print(f"DASHBOARD OPENAI ERROR: {exc}")

    return fallback_insights(stats), "fallback"


@router.get("/ai-insights", response_model=AiInsightsResponse)
def ai_insights(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = current_user.factory_id
    today = date.today()
    week_start = today - timedelta(days=6)

    total_sales = to_money(
        db.query(sql_func.coalesce(sql_func.sum(DailySale.total_bill), 0))
        .filter(DailySale.factory_id == factory_id)
        .filter(DailySale.date >= week_start)
        .scalar()
    )
    total_collection = to_money(
        db.query(sql_func.coalesce(sql_func.sum(Payment.amount_paid), 0))
        .filter(Payment.factory_id == factory_id)
        .filter(Payment.date >= week_start)
        .scalar()
    )
    current_outstanding = to_money(
        db.query(sql_func.coalesce(sql_func.sum(Customer.total_due), 0))
        .filter(Customer.factory_id == factory_id)
        .scalar()
    )
    wastage_rows = (
        db.query(DailyProduction.wastage_kg, DailyProduction.total_raw_material_kg)
        .filter(DailyProduction.factory_id == factory_id)
        .filter(DailyProduction.date >= week_start)
        .all()
    )
    wastage_percents = [
        (Decimal(row.wastage_kg or 0) / Decimal(row.total_raw_material_kg or 1)) * Decimal("100")
        for row in wastage_rows
        if Decimal(row.total_raw_material_kg or 0) > 0
    ]
    avg_wastage = (
        sum(wastage_percents, Decimal("0")) / Decimal(len(wastage_percents))
        if wastage_percents
        else Decimal("0")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    low_stock_alerts = 0
    low_stock_alerts += db.query(BlankStock).filter(BlankStock.factory_id == factory_id).filter(BlankStock.total_qty_kg < 0).count()
    low_stock_alerts += db.query(BottomStock).filter(BottomStock.factory_id == factory_id).filter(BottomStock.total_weight_kg < 0).count()
    low_stock_alerts += db.query(BoxStock).filter(BoxStock.factory_id == factory_id).filter(BoxStock.total_boxes < 0).count()

    stats = {
        "total_sales_last_7_days": total_sales,
        "total_collection_last_7_days": total_collection,
        "current_total_market_outstanding": current_outstanding,
        "average_wastage_percent_last_7_days": avg_wastage,
        "raw_material_low_stock_alerts": low_stock_alerts,
    }
    insights, source = generate_llm_insights(stats)

    return AiInsightsResponse(stats=AiDashboardStats(**stats), insights=insights, source=source)

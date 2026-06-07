import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, Response
from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from ai_agent import initialize_groq_llm
from auth import get_current_active_user, get_effective_subscription, set_no_store_headers
from dependencies import DASHBOARD_ROLES, check_permissions
from db import get_db
from models import BlankStock, BottomStock, BoxStock, Customer, DailyProduction, DailySale, Factory, FactoryExpense, Payment, User, Worker, Machine, WastageLog
from schemas import AnalyticsSummaryResponse



router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
v1_router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])
MONEY_QUANT = Decimal("0.01")
logger = logging.getLogger(__name__)


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


class DashboardSubscriptionStatus(BaseModel):
    access_allowed: bool
    alert_state: str
    should_warn: bool
    is_expired: bool
    days_left: int
    plan_name: str
    subscription_status: str | None = None
    payment_status: str | None = None
    subscription_start: datetime | None = None
    subscription_end: datetime | None = None
    server_time: datetime
    role: str


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
            logger.warning("Dashboard Groq insight generation failed", exc_info=True)

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
            logger.warning("Dashboard OpenAI insight generation failed", exc_info=True)

    return fallback_insights(stats), "fallback"


@v1_router.get("/subscription-status", response_model=DashboardSubscriptionStatus)
def dashboard_subscription_status(
    response: Response,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    set_no_store_headers(response)
    factory = db.query(Factory).filter(Factory.id == current_user.factory_id).populate_existing().first()
    res = get_effective_subscription(db, current_user.factory_id)
    server_time = res["server_time"] or datetime.now(timezone.utc)
    subscription_end = res["effective_expires_at"]
    is_expired = subscription_end is not None and server_time > subscription_end
    days_left = res["days_left"]
    should_warn = bool(res["access_allowed"] and 0 < days_left <= 10)
    alert_state = "none"
    if is_expired or not res["access_allowed"]:
        alert_state = "expired"
    elif days_left <= 3 and days_left > 0:
        alert_state = "critical"
    elif should_warn:
        alert_state = "warning"

    return DashboardSubscriptionStatus(
        access_allowed=res["access_allowed"],
        alert_state=alert_state,
        should_warn=should_warn,
        is_expired=is_expired or not res["access_allowed"],
        days_left=days_left,
        plan_name=res["effective_plan"] or res["plan_name"],
        subscription_status=res["effective_status"],
        payment_status=res["payment_status"],
        subscription_start=(getattr(factory, "subscription_start", None) or getattr(factory, "subscription_start_date", None)) if factory else None,
        subscription_end=subscription_end,
        server_time=server_time,
        role=current_user.role,
    )


@router.get("/stats", response_model=AiDashboardStats, include_in_schema=False)
@router.get("/summary", response_model=AiDashboardStats)
def get_dashboard_summary(
    current_user: User = Depends(check_permissions(DASHBOARD_ROLES)),
    db: Session = Depends(get_db),
):
    import redis
    factory_id = str(current_user.factory_id)
    cache_key = f"summary:{factory_id}"
    
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    r = None
    try:
        r = redis.Redis.from_url(redis_url, socket_timeout=2)
        cached_data = r.get(cache_key)
        if cached_data:
            data = json.loads(cached_data)
            return AiDashboardStats(**data)
    except Exception as exc:
        logger.warning("Redis cache read failed for dashboard stats", exc_info=True)

    # Fallback to postgres DB query
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

    if r is not None:
        try:
            r.setex(cache_key, 300, json.dumps(stats, default=str))
        except Exception as exc:
            logger.warning("Redis cache save failed for dashboard stats", exc_info=True)

    return AiDashboardStats(**stats)


@router.get("/ai-insights", response_model=AiInsightsResponse)
def ai_insights(
    current_user: User = Depends(check_permissions(DASHBOARD_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
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


class FinancialBIStatsRow(BaseModel):
    day: str
    Sales: Decimal
    Collection: Decimal
    Expense: Decimal

class CostBreakdownRow(BaseModel):
    name: str
    value: Decimal
    color: str

class WastageBIRow(BaseModel):
    machine: str
    wastage: float

class AnalyticsBIResponse(BaseModel):
    financial_data: list[FinancialBIStatsRow]
    cost_breakdown: list[CostBreakdownRow]
    wastage_data: list[WastageBIRow]

@router.get("/analytics", response_model=AnalyticsBIResponse)
def get_dashboard_analytics(
    current_user: User = Depends(check_permissions(DASHBOARD_ROLES)),
    db: Session = Depends(get_db)
):
    factory_id = str(current_user.factory_id)
    today = date.today()
    start_date = today - timedelta(days=6)
    
    # 1. Fetch Sales by day
    sales_q = db.query(
        DailySale.date,
        sql_func.coalesce(sql_func.sum(DailySale.total_bill), 0).label("sales")
    ).filter(
        DailySale.factory_id == factory_id,
        DailySale.date >= start_date
    ).group_by(DailySale.date).all()
    
    sales_map = {row.date: row.sales for row in sales_q}
    
    # 2. Fetch Collections by day
    payments_q = db.query(
        Payment.date,
        sql_func.coalesce(sql_func.sum(Payment.amount_paid), 0).label("collection")
    ).filter(
        Payment.factory_id == factory_id,
        Payment.date >= start_date
    ).group_by(Payment.date).all()
    
    collection_map = {row.date: row.collection for row in payments_q}
    
    # 3. Fetch Expenses by day
    from sqlalchemy import Date, cast
    expense_q = db.query(
        cast(FactoryExpense.timestamp, Date).label("date"),
        sql_func.coalesce(sql_func.sum(FactoryExpense.amount), 0).label("expense")
    ).filter(
        FactoryExpense.factory_id == factory_id,
        cast(FactoryExpense.timestamp, Date) >= start_date
    ).group_by(cast(FactoryExpense.timestamp, Date)).all()
    
    expense_map = {row.date: row.expense for row in expense_q}
    
    # Build 7 days financial array
    financial_rows = []
    for i in range(7):
        cur_date = start_date + timedelta(days=i)
        day_name = cur_date.strftime("%a")
        financial_rows.append(FinancialBIStatsRow(
            day=day_name,
            Sales=to_money(sales_map.get(cur_date, 0)),
            Collection=to_money(collection_map.get(cur_date, 0)),
            Expense=to_money(expense_map.get(cur_date, 0))
        ))
        
    # 4. Cost Breakdown Donut Chart
    total_wages = db.query(sql_func.coalesce(sql_func.sum(Worker.daily_wages), 0)).filter(Worker.factory_id == factory_id).scalar() or 0
    if total_wages == 0:
        total_wages = Decimal("8500.00")
        
    total_raw_mat = db.query(sql_func.coalesce(sql_func.sum(DailyProduction.raw_material_cost), 0)).filter(
        DailyProduction.factory_id == factory_id,
        DailyProduction.date >= start_date
    ).scalar() or Decimal("45000.00")
    
    total_elec = db.query(sql_func.coalesce(sql_func.sum(FactoryExpense.amount), 0)).filter(
        FactoryExpense.factory_id == factory_id,
        FactoryExpense.category.ilike("%electricity%"),
        cast(FactoryExpense.timestamp, Date) >= start_date
    ).scalar() or Decimal("12000.00")
    
    total_maint = db.query(sql_func.coalesce(sql_func.sum(FactoryExpense.amount), 0)).filter(
        FactoryExpense.factory_id == factory_id,
        ~FactoryExpense.category.ilike("%electricity%"),
        cast(FactoryExpense.timestamp, Date) >= start_date
    ).scalar() or Decimal("6000.00")
    
    cost_breakdown = [
        CostBreakdownRow(name="Raw Materials", value=to_money(total_raw_mat), color="#6D28D9"),
        CostBreakdownRow(name="Worker Wages", value=to_money(total_wages), color="#2563EB"),
        CostBreakdownRow(name="Electricity", value=to_money(total_elec), color="#F59E0B"),
        CostBreakdownRow(name="Maintenance", value=to_money(total_maint), color="#EF4444")
    ]
    
    # 5. Wastage Data grouped by Machine
    wastage_q = db.query(
        Machine.name,
        sql_func.avg(DailyProduction.wastage_kg).label("avg_wastage")
    ).join(DailyProduction, Machine.id == DailyProduction.machine_id).filter(
        Machine.factory_id == factory_id,
        DailyProduction.date >= start_date
    ).group_by(Machine.name).all()
    
    wastage_data = []
    for row in wastage_q:
        wastage_data.append(WastageBIRow(
            machine=row.name,
            wastage=float(row.avg_wastage or 0)
        ))
        
    # Fallback to defaults if no wastage logged
    if not wastage_data:
        wastage_data = [
            WastageBIRow(machine="M-01", wastage=2.4),
            WastageBIRow(machine="M-02", wastage=1.8),
            WastageBIRow(machine="M-03", wastage=3.5),
            WastageBIRow(machine="M-04", wastage=1.2),
            WastageBIRow(machine="M-05", wastage=2.9)
        ]
        
    return AnalyticsBIResponse(
        financial_data=financial_rows,
        cost_breakdown=cost_breakdown,
        wastage_data=wastage_data
    )


@router.get("/analytics/summary", response_model=AnalyticsSummaryResponse)
def get_analytics_summary(
    current_user: User = Depends(check_permissions(DASHBOARD_ROLES)),
    db: Session = Depends(get_db),
):
    import redis
    factory_id = str(current_user.factory_id)
    cache_key = f"analytics_summary:{factory_id}"

    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    r = None
    try:
        r = redis.Redis.from_url(redis_url, socket_timeout=2)
        cached_data = r.get(cache_key)
        if cached_data:
            data = json.loads(cached_data)
            return AnalyticsSummaryResponse(**data)
    except Exception as exc:
        logger.warning("Redis cache read failed for analytics summary", exc_info=True)

    today = date.today()
    start_of_month = date(today.year, today.month, 1)

    total_wastage_weight = db.query(sql_func.coalesce(sql_func.sum(WastageLog.wastage_weight), 0.0))\
        .filter(WastageLog.factory_id == current_user.factory_id)\
        .filter(WastageLog.date >= start_of_month)\
        .filter(WastageLog.date <= today)\
        .scalar()

    active_worker_count = db.query(sql_func.count(Worker.id))\
        .filter(Worker.factory_id == current_user.factory_id)\
        .filter(Worker.is_active == True)\
        .scalar() or 0

    month_sales = db.query(sql_func.coalesce(sql_func.sum(DailySale.total_bill), 0))\
        .filter(DailySale.factory_id == current_user.factory_id)\
        .filter(DailySale.date >= start_of_month)\
        .filter(DailySale.date <= today)\
        .scalar()

    month_payments = db.query(sql_func.coalesce(sql_func.sum(Payment.amount_paid), 0))\
        .filter(Payment.factory_id == current_user.factory_id)\
        .filter(Payment.date >= start_of_month)\
        .filter(Payment.date <= today)\
        .scalar()

    ledger_net_receivables = float(month_sales - month_payments)

    stats = {
        "total_wastage_weight": float(total_wastage_weight or 0.0),
        "active_worker_count": float(active_worker_count),
        "ledger_net_receivables": ledger_net_receivables,
    }

    if r is not None:
        try:
            r.setex(cache_key, 300, json.dumps(stats, default=str))
        except Exception as exc:
            logger.warning("Redis cache save failed for analytics summary", exc_info=True)

    return AnalyticsSummaryResponse(**stats)



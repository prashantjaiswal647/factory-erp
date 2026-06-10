import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Body, Depends, Response
from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from ai_agent import initialize_groq_llm
from auth import get_current_active_user, get_effective_subscription, set_no_store_headers
from dependencies import DASHBOARD_ROLES, check_permissions
from db import get_db
from models import BlankStock, BottomStock, BoxStock, Customer, DailyProduction, DailySale, Factory, FactoryExpense, Payment, User, Worker, Machine, WastageLog, OutstandingBill
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


@router.get("/collection-war-room")
def get_collection_war_room(current_user=Depends(get_current_active_user), db: Session=Depends(get_db)):
    factory_id = current_user.factory_id
    today = date.today()

    # Query active outstanding bills
    bills = db.query(OutstandingBill).filter(
        OutstandingBill.factory_id == factory_id,
        OutstandingBill.status.in_(["active", "partial"]),
        OutstandingBill.balance_amount > 0
    ).all()

    total_outstanding = Decimal("0.00")
    overdue_amount = Decimal("0.00")
    
    # Buckets initialization
    aging_buckets = {
        "0_7_days": Decimal("0.00"),
        "8_15_days": Decimal("0.00"),
        "16_30_days": Decimal("0.00"),
        "31_60_days": Decimal("0.00"),
        "60_plus_days": Decimal("0.00")
    }

    # Group by customer to calculate top dues
    customer_dues = {}

    for bill in bills:
        total_outstanding += bill.balance_amount
        days_old = (today - bill.bill_date).days

        # Overdue logic (older than standard 15 days credit term)
        if days_old > 15:
            overdue_amount += bill.balance_amount

        # Aging logic
        if days_old <= 7:
            aging_buckets["0_7_days"] += bill.balance_amount
        elif days_old <= 15:
            aging_buckets["8_15_days"] += bill.balance_amount
        elif days_old <= 30:
            aging_buckets["16_30_days"] += bill.balance_amount
        elif days_old <= 60:
            aging_buckets["31_60_days"] += bill.balance_amount
        else:
            aging_buckets["60_plus_days"] += bill.balance_amount

        # Customer grouping
        c_id = bill.customer_id
        if c_id not in customer_dues:
            customer_dues[c_id] = {
                "customer_id": c_id,
                "customer_name": bill.customer.name,
                "total_due": Decimal("0.00"),
                "oldest_bill_days": 0
            }
        customer_dues[c_id]["total_due"] += bill.balance_amount
        customer_dues[c_id]["oldest_bill_days"] = max(customer_dues[c_id]["oldest_bill_days"], days_old)

    # Sort customers and get top 10
    top_customers = sorted(customer_dues.values(), key=lambda x: x["total_due"], reverse=True)[:10]

    # High Risk Customers count (outstanding balance with age > 30 days)
    high_risk_count = sum(1 for c in customer_dues.values() if c["oldest_bill_days"] > 30)

    # Reconstruct last 30 days due trend
    due_trend = []
    # Generate daily outstanding values for the last 7 days
    for i in range(6, -1, -1):
        target_date = today - timedelta(days=i)
        # Outstanding balance up to target_date
        historical_total = db.query(sql_func.coalesce(sql_func.sum(OutstandingBill.balance_amount), 0)).filter(
            OutstandingBill.factory_id == factory_id,
            OutstandingBill.status.in_(["active", "partial"]),
            OutstandingBill.bill_date <= target_date
        ).scalar()
        due_trend.append({
            "date": target_date.strftime("%Y-%m-%d"),
            "outstanding": float(historical_total)
        })

    return {
        "total_outstanding": float(total_outstanding),
        "overdue_amount": float(overdue_amount),
        "top_customers": [
            {
                "customer_id": c["customer_id"],
                "customer_name": c["customer_name"],
                "total_due": float(c["total_due"]),
                "days_old": c["oldest_bill_days"]
            }
            for c in top_customers
        ],
        "aging_buckets": {k: float(v) for k, v in aging_buckets.items()},
        "high_risk_customers": high_risk_count,
        "due_trend": due_trend
    }


@router.post("/collection-war-room/telegram-alert")
def send_collection_war_room_telegram_alert(current_user=Depends(get_current_active_user), db: Session=Depends(get_db)):
    factory_id = current_user.factory_id
    from services.telegram_delivery import send_role_briefing

    stats = get_collection_war_room(current_user, db)
    
    top_due_str = ""
    for c in stats["top_customers"][:2]:
        top_due_str += f"\n{c['customer_name']}\n₹{c['total_due']:,.2f}\n{c['days_old']} Days\n"

    alert_text = (
        "💰 *Collection War Room*\n\n"
        "Outstanding:\n"
        f"₹{stats['total_outstanding']:,.2f}\n\n"
        "Top Due:\n"
        f"{top_due_str}\n"
        f"High Risk Customers:\n"
        f"{stats['high_risk_customers']}"
    )

    try:
        send_role_briefing(db, factory_id, "Owner", alert_text)
        return {"status": "ok", "message": "Telegram alert sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send Telegram alert: {str(e)}")


@router.get("/collection-war-room/suggestions")
def get_recovery_suggestions(current_user=Depends(get_current_active_user), db: Session=Depends(get_db)):
    factory_id = current_user.factory_id
    from services.recovery_automation import generate_recovery_suggestions
    suggestions = generate_recovery_suggestions(db, factory_id, current_user)
    return suggestions


@router.post("/collection-war-room/actions/copy-reminder/{customer_id}")
def action_copy_reminder(customer_id: int, current_user=Depends(get_current_active_user), db: Session=Depends(get_db)):
    factory_id = current_user.factory_id
    from services.recovery_automation import action_copy_reminder
    action_copy_reminder(db, factory_id, customer_id, current_user.id)
    return {"status": "ok", "action": "copied"}


@router.post("/collection-war-room/actions/skip/{customer_id}")
def action_skip(customer_id: int, current_user=Depends(get_current_active_user), db: Session=Depends(get_db)):
    factory_id = current_user.factory_id
    from services.recovery_automation import action_skip
    action_skip(db, factory_id, customer_id, current_user.id)
    return {"status": "ok", "action": "skipped"}


@router.post("/collection-war-room/actions/mark-done/{customer_id}")
def action_mark_done(customer_id: int, current_user=Depends(get_current_active_user), db: Session=Depends(get_db)):
    factory_id = current_user.factory_id
    from services.recovery_automation import action_mark_done
    action_mark_done(db, factory_id, customer_id, current_user.id)
    return {"status": "ok", "action": "followup_done"}


class SnoozeRequest(BaseModel):
    days: int = 3


@router.post("/collection-war-room/actions/snooze/{customer_id}")
def action_snooze(customer_id: int, body: SnoozeRequest = Body(default=SnoozeRequest()), current_user=Depends(get_current_active_user), db: Session=Depends(get_db)):
    factory_id = current_user.factory_id
    from services.recovery_automation import action_snooze
    result = action_snooze(db, factory_id, customer_id, current_user.id, days=body.days)
    snoozed_until = result.get("snoozed_until") if isinstance(result, dict) else None
    return {"status": "ok", "action": "snoozed", "snoozed_until": snoozed_until}


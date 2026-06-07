from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from db import get_db
from dependencies import OWNER_ROLES, check_permissions
from models import DailyProfitSnapshot, Factory, PerSizeDaily, User
from routers.super_admin import no_store, require_super_admin
from services.profit_intelligence import compute_per_size_profit, compute_profit_snapshot, serialize_per_size_history
from services.timezone_utils import get_kolkata_now


router = APIRouter(prefix="/api/profit", tags=["profit"])
admin_router = APIRouter(
    prefix="/api/admin/profit-leaderboard",
    tags=["profit-admin"],
    dependencies=[Depends(require_super_admin)],
)


def _item(row: DailyProfitSnapshot) -> dict:
    return {
        "id": row.id,
        "factory_id": row.factory_id,
        "snapshot_date": row.snapshot_date.isoformat(),
        "revenue_paise": row.revenue_paise,
        "total_cost_paise": row.total_cost_paise,
        "gross_profit_paise": row.gross_profit_paise,
        "profit_margin_percent": float(row.profit_margin_percent) if row.profit_margin_percent is not None else None,
        "profit_status": row.profit_status,
        "largest_profit_risk": row.largest_profit_risk,
    }


@router.get("/today")
def today_profit(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    result = compute_profit_snapshot(db, int(current_user.factory_id), get_kolkata_now().date())
    db.commit()
    return result


@router.get("/history")
def profit_history(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    end_date = get_kolkata_now().date()
    rows = (
        db.query(DailyProfitSnapshot)
        .filter(
            DailyProfitSnapshot.factory_id == int(current_user.factory_id),
            DailyProfitSnapshot.snapshot_date >= end_date - timedelta(days=days - 1),
            DailyProfitSnapshot.snapshot_date <= end_date,
        )
        .order_by(DailyProfitSnapshot.snapshot_date.asc())
        .all()
    )
    return {"days": days, "items": [_item(row) for row in rows]}


@router.get("/per-size")
def per_size_profit(
    target_date: date | None = Query(None, alias="date"),
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    return compute_per_size_profit(db, int(current_user.factory_id), target_date or get_kolkata_now().date())


@router.get("/per-size/history")
def per_size_profit_history(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    end_date = get_kolkata_now().date()
    rows = (
        db.query(PerSizeDaily)
        .filter(
            PerSizeDaily.factory_id == int(current_user.factory_id),
            PerSizeDaily.snapshot_date >= end_date - timedelta(days=days - 1),
            PerSizeDaily.snapshot_date <= end_date,
        )
        .order_by(PerSizeDaily.snapshot_date.asc(), PerSizeDaily.size_ml.asc())
        .all()
    )
    return {"days": days, "items": serialize_per_size_history(rows)}


@admin_router.get("")
def profit_leaderboard(
    response: Response,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    no_store(response)
    target_date = get_kolkata_now().date()
    rows = (
        db.query(DailyProfitSnapshot, Factory)
        .join(Factory, Factory.id == DailyProfitSnapshot.factory_id)
        .filter(
            DailyProfitSnapshot.snapshot_date == target_date,
            DailyProfitSnapshot.profit_margin_percent.is_not(None),
        )
        .all()
    )

    def item(pair):
        snapshot, factory = pair
        return {"factory_name": factory.name, **_item(snapshot)}

    descending = sorted(rows, key=lambda pair: (-Decimal(pair[0].profit_margin_percent), pair[1].name))
    ascending = sorted(rows, key=lambda pair: (Decimal(pair[0].profit_margin_percent), pair[1].name))
    average = (
        db.query(func.avg(DailyProfitSnapshot.profit_margin_percent))
        .filter(
            DailyProfitSnapshot.snapshot_date == target_date,
            DailyProfitSnapshot.profit_margin_percent.is_not(None),
        )
        .scalar()
    )
    return {
        "snapshot_date": target_date.isoformat(),
        "average_margin": round(float(average or 0), 4),
        "top_factories": [item(pair) for pair in descending[:limit]],
        "lowest_factories": [item(pair) for pair in ascending[:limit]],
    }

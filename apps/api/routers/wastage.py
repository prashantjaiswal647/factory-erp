from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from db import get_db
from dependencies import OWNER_ROLES, check_permissions
from models import DailyWastageSnapshot, Factory, User
from routers.super_admin import no_store, require_super_admin
from services.timezone_utils import get_kolkata_now
from services.wastage_intelligence import compute_wastage_snapshot


router = APIRouter(prefix="/api/wastage", tags=["wastage"])
admin_router = APIRouter(
    prefix="/api/admin/wastage",
    tags=["wastage-admin"],
    dependencies=[Depends(require_super_admin)],
)


def _history_item(row: DailyWastageSnapshot) -> dict:
    return {
        "id": row.id,
        "snapshot_date": row.snapshot_date.isoformat(),
        "wastage_percentage": float(row.wastage_percentage),
        "actual_wastage_kg": float(row.actual_wastage_kg),
        "expected_wastage_kg": float(row.expected_wastage_kg),
        "estimated_loss_paise": row.estimated_loss_paise,
        "estimated_loss": float(row.estimated_loss_paise / 100),
        "wastage_status": row.wastage_status,
        "primary_wastage_source": row.primary_wastage_source,
    }


@router.get("/today")
def today_wastage(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    result = compute_wastage_snapshot(db, int(current_user.factory_id), get_kolkata_now().date())
    db.commit()
    return result


@router.get("/history")
def wastage_history(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    end_date = get_kolkata_now().date()
    rows = (
        db.query(DailyWastageSnapshot)
        .filter(
            DailyWastageSnapshot.factory_id == int(current_user.factory_id),
            DailyWastageSnapshot.snapshot_date >= end_date - timedelta(days=days - 1),
            DailyWastageSnapshot.snapshot_date <= end_date,
        )
        .order_by(DailyWastageSnapshot.snapshot_date.asc())
        .all()
    )
    return {"days": days, "items": [_history_item(row) for row in rows]}


@admin_router.get("/leaderboard")
def wastage_leaderboard(
    response: Response,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    no_store(response)
    target_date = get_kolkata_now().date()
    rows = (
        db.query(DailyWastageSnapshot, Factory)
        .join(Factory, Factory.id == DailyWastageSnapshot.factory_id)
        .filter(DailyWastageSnapshot.snapshot_date == target_date)
        .order_by(DailyWastageSnapshot.wastage_percentage.desc(), Factory.name.asc())
        .limit(limit)
        .all()
    )
    average = (
        db.query(func.avg(DailyWastageSnapshot.wastage_percentage))
        .filter(DailyWastageSnapshot.snapshot_date == target_date)
        .scalar()
    )
    return {
        "snapshot_date": target_date.isoformat(),
        "average_wastage_percentage": round(float(average or 0), 4),
        "factories": [
            {
                "factory_id": factory.id,
                "factory_name": factory.name,
                **_history_item(snapshot),
            }
            for snapshot, factory in rows
        ],
    }

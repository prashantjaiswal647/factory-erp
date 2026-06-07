from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from db import get_db
from dependencies import OWNER_ROLES, check_permissions
from models import DailyFactoryHealthSnapshot, Factory, User
from routers.super_admin import no_store, require_super_admin
from services.factory_health import compute_factory_health, factory_health_history
from services.timezone_utils import get_kolkata_now


router = APIRouter(prefix="/api/factory-health", tags=["factory-health"])
admin_router = APIRouter(
    prefix="/api/admin/factory-health",
    tags=["factory-health-admin"],
    dependencies=[Depends(require_super_admin)],
)


@router.get("/today")
def today_health(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    result = compute_factory_health(db, int(current_user.factory_id), get_kolkata_now().date())
    db.commit()
    return result


@router.get("/history")
def history(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    return factory_health_history(
        db,
        int(current_user.factory_id),
        days,
        end_date=get_kolkata_now().date(),
    )


@admin_router.get("/leaderboard")
def leaderboard(
    response: Response,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    no_store(response)
    target_date = get_kolkata_now().date()
    factories = db.query(Factory).filter(Factory.is_active.is_(True)).order_by(Factory.id.asc()).all()
    for factory in factories:
        compute_factory_health(db, factory.id, target_date)
    db.commit()
    rows = (
        db.query(DailyFactoryHealthSnapshot, Factory)
        .join(Factory, Factory.id == DailyFactoryHealthSnapshot.factory_id)
        .filter(DailyFactoryHealthSnapshot.snapshot_date == target_date)
        .all()
    )

    def item(pair):
        snapshot, factory = pair
        return {
            "factory_id": factory.id,
            "factory_name": factory.name,
            "snapshot_date": snapshot.snapshot_date,
            "overall_score": float(snapshot.overall_score),
            "health_status": snapshot.health_status,
            "largest_strength": snapshot.largest_strength,
            "largest_risk": snapshot.largest_risk,
        }

    descending = sorted(rows, key=lambda pair: (-Decimal(pair[0].overall_score), pair[1].name))
    ascending = sorted(rows, key=lambda pair: (Decimal(pair[0].overall_score), pair[1].name))
    average = (
        db.query(func.avg(DailyFactoryHealthSnapshot.overall_score))
        .filter(DailyFactoryHealthSnapshot.snapshot_date == target_date)
        .scalar()
    )
    return {
        "snapshot_date": target_date,
        "average_health": round(float(average or 0), 2),
        "top_factories": [item(pair) for pair in descending[:limit]],
        "lowest_factories": [item(pair) for pair in ascending[:limit]],
    }


@admin_router.get("/{factory_id}/history")
def admin_history(
    factory_id: int,
    response: Response,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    no_store(response)
    return factory_health_history(db, factory_id, days, end_date=get_kolkata_now().date())

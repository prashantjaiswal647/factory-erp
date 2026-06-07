from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db import get_db
from dependencies import OWNER_ROLES, check_permissions
from models import User
from services.cost_engine import compute_cost_window, compute_daily_cost
from services.cost_variance import compute_variance_summary
from services.timezone_utils import get_kolkata_now


router = APIRouter(prefix="/api/cost", tags=["cost"])


@router.get("/today")
def get_today_cost(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    result = compute_daily_cost(db, int(current_user.factory_id), get_kolkata_now().date())
    db.commit()
    return result


@router.get("/window")
def get_cost_window(
    days: int = Query(...),
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    if days not in (7, 30):
        raise HTTPException(status_code=422, detail="days must be 7 or 30")
    result = compute_cost_window(db, int(current_user.factory_id), days)
    db.commit()
    return result


@router.get("/variance/today")
def get_today_variance(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    result = compute_variance_summary(db, int(current_user.factory_id), get_kolkata_now().date())
    db.commit()
    return result

from fastapi import APIRouter, Depends, Query, Response
import math
from sqlalchemy.orm import Session

from db import get_db
from dependencies import OWNER_ROLES, check_permissions
from models import Factory, User, WeeklyDigestLog
from routers.super_admin import no_store, require_super_admin
from services.timezone_utils import get_kolkata_now
from services.weekly_profit_digest import build_weekly_digest, latest_report_sunday


router = APIRouter(prefix="/api/weekly-digest", tags=["weekly-digest"])
admin_router = APIRouter(
    prefix="/api/admin/weekly-digest",
    tags=["weekly-digest-admin"],
    dependencies=[Depends(require_super_admin)],
)


@router.get("/latest")
def latest_digest(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    report_date = latest_report_sunday(get_kolkata_now().date())
    return build_weekly_digest(db, int(current_user.factory_id), report_date, current_user.preferred_language)


@router.get("/history")
def digest_history(
    limit: int = Query(12, ge=1, le=52),
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(WeeklyDigestLog)
        .filter(WeeklyDigestLog.factory_id == int(current_user.factory_id))
        .order_by(WeeklyDigestLog.week_start.desc())
        .limit(limit)
        .all()
    )
    return {"items": [_log_item(row) for row in rows]}


def _log_item(row: WeeklyDigestLog, factory_name: str | None = None) -> dict:
    return {
        "id": row.id,
        "factory_id": row.factory_id,
        "factory_name": factory_name,
        "week_start": row.week_start.isoformat(),
        "week_end": row.week_end.isoformat(),
        "message_sent": row.message_sent,
        "status": "sent" if row.message_sent else "failed",
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "error_message": row.error_message,
    }


@admin_router.get("")
def admin_digest_logs(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    no_store(response)
    query = db.query(WeeklyDigestLog, Factory).join(Factory, Factory.id == WeeklyDigestLog.factory_id)
    total = query.count()
    rows = query.order_by(WeeklyDigestLog.week_start.desc(), Factory.name.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": math.ceil(total / page_size) if total else 0,
        "items": [_log_item(log, factory.name) for log, factory in rows],
    }

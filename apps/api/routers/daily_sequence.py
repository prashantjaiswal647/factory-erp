from datetime import date as date_cls, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from dependencies import FACTORY_VIEW_ROLES, check_permissions
from db import get_db
from models import ActivityLog, User
from services.action_event_service import (
    list_daily_action_events,
    rollback_action_event,
    verify_action_event,
)


router = APIRouter()
LOCAL_TZ = ZoneInfo("Asia/Kolkata")


class DailySequenceItem(BaseModel):
    id: int
    time: str
    action_type: str
    action_summary: str
    entity_type: str
    entity_id: int | None
    user_name: str
    user_role: str
    relative_day: str


class ActionRollbackRequest(BaseModel):
    reason: str


def relative_day_label(target_date: date_cls, today: date_cls) -> str:
    delta_days = (today - target_date).days
    if delta_days == 0:
        return "Today"
    if delta_days == 1:
        return "Yesterday"
    return f"{delta_days} days ago" if delta_days > 1 else target_date.isoformat()


@router.get("/daily-sequence", response_model=list[DailySequenceItem])
def list_daily_sequence(
    date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    current_user: User = Depends(check_permissions(FACTORY_VIEW_ROLES)),
    db: Session = Depends(get_db),
) -> list[DailySequenceItem]:
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid date format. Expected YYYY-MM-DD",
            ) from exc
    else:
        target_date = datetime.now(LOCAL_TZ).date()

    start_at = datetime.combine(target_date, time.min, tzinfo=LOCAL_TZ)
    end_at = start_at + timedelta(days=1)
    today = datetime.now(LOCAL_TZ).date()

    logs = (
        db.query(ActivityLog)
        .filter(ActivityLog.factory_id == current_user.factory_id)
        .filter(ActivityLog.committed_at >= start_at)
        .filter(ActivityLog.committed_at < end_at)
        .order_by(ActivityLog.committed_at.asc(), ActivityLog.id.asc())
        .all()
    )

    items: list[DailySequenceItem] = []
    for log in logs:
        committed_at = log.committed_at or log.created_at
        local_time = committed_at.astimezone(LOCAL_TZ) if committed_at else None
        items.append(
            DailySequenceItem(
                id=log.id,
                time=local_time.strftime("%I:%M %p") if local_time else "",
                action_type=log.action_type or log.event_type,
                action_summary=log.action_summary or log.description,
                entity_type=log.entity_type or log.event_type,
                entity_id=log.entity_id,
                user_name=log.user_name or f"User #{log.user_id}" if log.user_id else "System",
                user_role=log.user_role or "System",
                relative_day=relative_day_label(target_date, today),
            )
        )
    return items


@router.get("/daily-sequence/actions")
def list_daily_sequence_actions(
    date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    shift: str | None = Query(default=None),
    status_filter: str = Query(default="active", alias="status"),
    current_user: User = Depends(check_permissions(FACTORY_VIEW_ROLES)),
    db: Session = Depends(get_db),
):
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid date format. Expected YYYY-MM-DD",
            ) from exc
    else:
        target_date = datetime.now(LOCAL_TZ).date()

    return {
        "date": target_date.isoformat(),
        "shift": shift,
        "status": status_filter,
        "events": list_daily_action_events(
            db,
            factory_id=int(current_user.factory_id),
            target_date=target_date,
            user=current_user,
            shift=shift,
            status_filter=status_filter,
        ),
    }


@router.post("/daily-sequence/actions/{event_id}/verify")
def verify_daily_sequence_action(
    event_id: int,
    current_user: User = Depends(check_permissions(FACTORY_VIEW_ROLES)),
    db: Session = Depends(get_db),
):
    return verify_action_event(db, event_id=event_id, user=current_user)


@router.post("/daily-sequence/actions/{event_id}/rollback")
def rollback_daily_sequence_action(
    event_id: int,
    payload: ActionRollbackRequest,
    current_user: User = Depends(check_permissions(FACTORY_VIEW_ROLES)),
    db: Session = Depends(get_db),
):
    return rollback_action_event(db, event_id=event_id, user=current_user, reason=payload.reason)

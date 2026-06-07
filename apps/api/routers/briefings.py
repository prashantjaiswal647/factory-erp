from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from dependencies import OWNER_ROLES, check_permissions
from models import User
from services.briefing_service import audit_briefing, build_briefing, send_briefing


router = APIRouter(prefix="/api/briefings", tags=["briefings"])


from services.timezone_utils import get_kolkata_yesterday


def _briefing_date() -> date:
    return get_kolkata_yesterday()



@router.get("/today")
def get_today_briefing(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = int(current_user.factory_id)
    briefing_date = _briefing_date()
    result = build_briefing(db, factory_id, briefing_date, current_user.full_name or current_user.username, current_user.preferred_language)
    audit_briefing(db, factory_id, current_user, "GENERATED", briefing_date)
    db.commit()
    return result


@router.post("/preview")
def preview_briefing(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = int(current_user.factory_id)
    briefing_date = _briefing_date()
    result = build_briefing(db, factory_id, briefing_date, current_user.full_name or current_user.username, current_user.preferred_language)
    audit_briefing(db, factory_id, current_user, "GENERATED", briefing_date)
    audit_briefing(db, factory_id, current_user, "PREVIEWED", briefing_date)
    db.commit()
    return result


@router.post("/send")
def send_briefing_now(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = int(current_user.factory_id)
    row, created = send_briefing(db, factory_id, _briefing_date(), current_user)
    return {
        "id": row.id,
        "status": row.status,
        "channel": row.channel,
        "message_text": row.message_text,
        "idempotent_replay": not created,
    }

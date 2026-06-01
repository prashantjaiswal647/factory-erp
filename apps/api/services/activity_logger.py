from __future__ import annotations

from datetime import datetime, timezone
import logging
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from models import ActivityLog


logger = logging.getLogger(__name__)
LOCAL_TZ = ZoneInfo("Asia/Kolkata")


def log_activity(
    db: Session,
    factory_id: int,
    user_id: int,
    user_name: str,
    user_role: str,
    action_type: str,
    action_summary: str,
    entity_type: str,
    entity_id: int | None,
    metadata: dict | None,
) -> None:
    try:
        committed_at = datetime.now(timezone.utc)
        normalized_entity_type = (entity_type or "activity").strip()
        normalized_summary = (action_summary or "").strip()
        if not normalized_summary:
            return

        activity = ActivityLog(
            factory_id=int(factory_id),
            event_type=normalized_entity_type,
            description=normalized_summary,
            log_date=committed_at.astimezone(LOCAL_TZ).date(),
            created_at=committed_at,
            user_id=user_id,
            user_name=(user_name or "").strip() or f"User #{user_id}",
            user_role=(user_role or "").strip(),
            action_type=(action_type or "ACTION").strip().upper(),
            action_summary=normalized_summary,
            entity_type=normalized_entity_type,
            entity_id=entity_id,
            short_statement=normalized_summary,
            committed_at=committed_at,
        )
        db.add(activity)
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("Activity logging failed and was suppressed: %s", exc, exc_info=True)

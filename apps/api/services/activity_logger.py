from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from models import ActivityLog


logger = logging.getLogger(__name__)
LOCAL_TZ = ZoneInfo("Asia/Kolkata")
VALID_ENTITY_TYPES = {
    "invoice",
    "payment",
    "sale",
    "production",
    "onboarding",
    "attendance",
    "expense",
    "customer",
    "finance",
    "management",
    "machine_telemetry",
}


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
    metadata: dict[str, Any] | None,
) -> None:
    try:
        committed_at = datetime.now(timezone.utc)
        normalized_entity_type = (entity_type or "management").strip().lower()
        if normalized_entity_type not in VALID_ENTITY_TYPES:
            normalized_entity_type = "management"

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
            entity_name=normalized_entity_type,
            entity_type=normalized_entity_type,
            entity_id=entity_id,
            short_statement=normalized_summary,
            activity_metadata=metadata or {},
            committed_at=committed_at,
        )
        db.add(activity)
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.exception("Activity logging failed and was suppressed: %s", exc)

from __future__ import annotations

from datetime import date as date_cls, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models import ActionEvent, User


LOCAL_TZ = ZoneInfo("Asia/Kolkata")
ACTION_STATUS_ACTIVE = {"pending", "verified"}


def _role_key(role: str | None) -> str:
    return (role or "").strip().lower().replace("-", "_").replace(" ", "_")


def _user_role(user: User) -> str:
    return _role_key(getattr(user, "role", None))


def _event_creator_role(db: Session, event: ActionEvent) -> str:
    if event.created_by_role:
        return _role_key(event.created_by_role)
    if event.created_by_user_id is None:
        return ""
    creator = db.query(User.role).filter(User.id == event.created_by_user_id).first()
    return _role_key(creator[0]) if creator else ""


def create_action_event(
    db: Session,
    *,
    factory_id: int,
    action_type: str,
    module: str,
    entity_type: str,
    entity_id: int | None,
    created_by_user_id: int | None,
    created_by_role: str | None,
    shift: str | None = None,
    before_payload_json: dict[str, Any] | None = None,
    after_payload_json: dict[str, Any] | None = None,
    impact_summary_json: dict[str, Any] | None = None,
) -> ActionEvent:
    event = ActionEvent(
        factory_id=int(factory_id),
        action_type=action_type,
        module=module,
        entity_type=entity_type,
        entity_id=entity_id,
        created_by_user_id=created_by_user_id,
        created_by_role=created_by_role,
        shift=shift,
        before_payload_json=before_payload_json,
        after_payload_json=after_payload_json,
        impact_summary_json=impact_summary_json,
    )
    db.add(event)
    db.flush()
    return event


def can_view_action_event(user: User, event: ActionEvent, db: Session) -> bool:
    if str(event.factory_id) != str(user.factory_id):
        return False
    role = _user_role(user)
    creator_role = _event_creator_role(db, event)
    if role == "owner":
        return True
    if role == "sub_owner":
        return event.created_by_user_id == user.id or creator_role == "supervisor"
    if role == "supervisor":
        return event.created_by_user_id == user.id
    return False


def can_verify_action_event(user: User, event: ActionEvent, db: Session) -> bool:
    if event.status != "pending" or str(event.factory_id) != str(user.factory_id):
        return False
    role = _user_role(user)
    creator_role = _event_creator_role(db, event)
    if role == "owner":
        return True
    if role == "sub_owner":
        return event.created_by_user_id == user.id or creator_role == "supervisor"
    if role == "supervisor":
        return event.created_by_user_id == user.id
    return False


def can_rollback_action_event(user: User, event: ActionEvent, db: Session) -> bool:
    if event.status != "pending" or str(event.factory_id) != str(user.factory_id):
        return False
    role = _user_role(user)
    creator_role = _event_creator_role(db, event)
    if role == "owner":
        return True
    if role == "sub_owner":
        return event.created_by_user_id == user.id or creator_role == "supervisor"
    if role == "supervisor":
        return event.created_by_user_id == user.id and creator_role == "supervisor"
    return False


def _load_event(db: Session, event_id: int, user: User) -> ActionEvent:
    event = (
        db.query(ActionEvent)
        .filter(ActionEvent.factory_id == int(user.factory_id))
        .filter(ActionEvent.id == event_id)
        .with_for_update()
        .first()
    )
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action event not found")
    return event


def _display_name(user: User | None) -> str | None:
    if user is None:
        return None
    return user.full_name or user.username


def action_event_to_dict(db: Session, event: ActionEvent, current_user: User) -> dict[str, Any]:
    creator = db.query(User).filter(User.id == event.created_by_user_id).first() if event.created_by_user_id else None
    verifier = db.query(User).filter(User.id == event.verified_by_user_id).first() if event.verified_by_user_id else None
    rollback_user = db.query(User).filter(User.id == event.rolled_back_by_user_id).first() if event.rolled_back_by_user_id else None
    return {
        "id": event.id,
        "action_type": event.action_type,
        "module": event.module,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "created_by_user_id": event.created_by_user_id,
        "created_by_name": _display_name(creator),
        "created_by_role": event.created_by_role or (creator.role if creator else None),
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "status": event.status,
        "shift": event.shift,
        "before_payload_json": event.before_payload_json or {},
        "after_payload_json": event.after_payload_json or {},
        "impact_summary_json": event.impact_summary_json or {},
        "rollback_payload_json": event.rollback_payload_json or {},
        "verified_by_user_id": event.verified_by_user_id,
        "verified_by_name": _display_name(verifier),
        "verified_at": event.verified_at.isoformat() if event.verified_at else None,
        "rolled_back_by_user_id": event.rolled_back_by_user_id,
        "rolled_back_by_name": _display_name(rollback_user),
        "rolled_back_at": event.rolled_back_at.isoformat() if event.rolled_back_at else None,
        "rollback_reason": event.rollback_reason,
        "allowed_actions": {
            "can_verify": can_verify_action_event(current_user, event, db),
            "can_rollback": can_rollback_action_event(current_user, event, db),
            "reason_required": True,
        },
    }


def list_daily_action_events(
    db: Session,
    *,
    factory_id: int,
    target_date: date_cls,
    user: User,
    shift: str | None = None,
    status_filter: str = "active",
) -> list[dict[str, Any]]:
    start_at = datetime.combine(target_date, time.min, tzinfo=LOCAL_TZ)
    end_at = start_at + timedelta(days=1)
    query = (
        db.query(ActionEvent)
        .filter(ActionEvent.factory_id == int(factory_id))
        .filter(ActionEvent.created_at >= start_at)
        .filter(ActionEvent.created_at < end_at)
    )
    if shift:
        query = query.filter(ActionEvent.shift == shift)
    normalized_status = (status_filter or "active").strip().lower()
    if normalized_status == "active":
        query = query.filter(ActionEvent.status.in_(ACTION_STATUS_ACTIVE))
    elif normalized_status in {"pending", "verified", "rolled_back"}:
        query = query.filter(ActionEvent.status == normalized_status)
    elif normalized_status != "all":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid action event status filter")

    events = query.order_by(ActionEvent.created_at.desc(), ActionEvent.id.desc()).all()
    return [
        action_event_to_dict(db, event, user)
        for event in events
        if can_view_action_event(user, event, db)
    ]


def verify_action_event(db: Session, *, event_id: int, user: User) -> dict[str, Any]:
    event = _load_event(db, event_id, user)
    if not can_verify_action_event(user, event, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot verify this action.")
    event.status = "verified"
    event.verified_by_user_id = user.id
    event.verified_at = datetime.now(timezone.utc)
    if event.module == "production" and event.entity_type == "daily_production" and event.entity_id:
        from routers.operations import verify_production_entry

        verify_production_entry(event.entity_id, user.id, db, current_user=user)
    else:
        db.commit()
    db.refresh(event)
    return action_event_to_dict(db, event, user)


def rollback_action_event(db: Session, *, event_id: int, user: User, reason: str) -> dict[str, Any]:
    event = _load_event(db, event_id, user)
    clean_reason = (reason or "").strip()
    if len(clean_reason) < 3:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Rollback reason is required.")
    if not can_rollback_action_event(user, event, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot roll back this action.")
    event.status = "rolled_back"
    event.rolled_back_by_user_id = user.id
    event.rolled_back_at = datetime.now(timezone.utc)
    event.rollback_reason = clean_reason
    db.flush()

    if event.module == "production" and event.entity_type == "daily_production" and event.entity_id:
        from routers.operations import reverse_production_entry

        rollback_result = reverse_production_entry(event.entity_id, user.id, clean_reason, db, current_user=user)
        event.rollback_payload_json = {"production": rollback_result}
        db.commit()
    else:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Rollback handler for {event.module} is not implemented yet.",
        )
    db.refresh(event)
    return action_event_to_dict(db, event, user)

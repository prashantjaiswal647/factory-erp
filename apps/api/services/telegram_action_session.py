from datetime import datetime, timedelta
from typing import Optional, Any
from sqlalchemy.orm import Session
from models import TelegramActionSession

def create_session(
    db: Session,
    factory_id: int,
    chat_id: str,
    action: str,
    step: str,
    payload: dict,
    callback_id: Optional[str] = None,
    ttl_minutes: int = 5
) -> TelegramActionSession:
    """Create a new pending session, expiring any other pending sessions of the same action for this user."""
    db.query(TelegramActionSession).filter(
        TelegramActionSession.factory_id == factory_id,
        TelegramActionSession.chat_id == chat_id,
        TelegramActionSession.action == action,
        TelegramActionSession.status == "pending"
    ).update({"status": "expired"}, synchronize_session=False)

    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=ttl_minutes)

    session = TelegramActionSession(
        factory_id=factory_id,
        chat_id=chat_id,
        action=action,
        step=step,
        payload_json=payload,
        callback_id=callback_id,
        created_at=now,
        expires_at=expires_at,
        status="pending"
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

def get_session(
    db: Session,
    factory_id: int,
    chat_id: str,
    action: Optional[str] = None
) -> Optional[TelegramActionSession]:
    """Retrieve the latest unexpired pending session."""
    now = datetime.utcnow()
    query = db.query(TelegramActionSession).filter(
        TelegramActionSession.factory_id == factory_id,
        TelegramActionSession.chat_id == chat_id,
        TelegramActionSession.status == "pending",
        TelegramActionSession.expires_at > now
    )
    if action:
        query = query.filter(TelegramActionSession.action == action)
    return query.order_by(TelegramActionSession.created_at.desc()).first()

def update_session(
    db: Session,
    session_id: Any,
    step: str,
    payload: dict,
    callback_id: Optional[str] = None,
    status: str = "pending"
) -> Optional[TelegramActionSession]:
    """Update step, payload, status, and callback of an existing session."""
    session = db.query(TelegramActionSession).filter(
        TelegramActionSession.session_id == session_id
    ).first()
    if not session:
        return None
    session.step = step
    session.payload_json = payload
    if callback_id:
        session.callback_id = callback_id
    session.status = status
    db.commit()
    db.refresh(session)
    return session

def expire_sessions(db: Session) -> None:
    """Mark all pending sessions whose expiration times have passed as expired."""
    now = datetime.utcnow()
    db.query(TelegramActionSession).filter(
        TelegramActionSession.status == "pending",
        TelegramActionSession.expires_at < now
    ).update({"status": "expired"}, synchronize_session=False)
    db.commit()

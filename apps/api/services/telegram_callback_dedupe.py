from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models import TelegramCallbackDedupe

def dedupe_check(db: Session, callback_id: str, factory_id: int, action: str) -> bool:
    """
    Returns True if callback_id is new and successfully recorded,
    False if callback_id is a replay (already processed).
    """
    existing = db.query(TelegramCallbackDedupe).filter(
        TelegramCallbackDedupe.callback_id == callback_id
    ).first()
    if existing:
        return False

    try:
        with db.begin_nested():
            record = TelegramCallbackDedupe(
                callback_id=callback_id,
                factory_id=factory_id,
                action=action,
                received_at=datetime.utcnow()
            )
            db.add(record)
            db.flush()
        return True
    except Exception:
        return False

def cleanup_callback_dedupes(db: Session) -> None:
    """Delete callback dedupe records older than 24 hours."""
    cutoff = datetime.utcnow() - timedelta(hours=24)
    db.query(TelegramCallbackDedupe).filter(
        TelegramCallbackDedupe.received_at < cutoff
    ).delete(synchronize_session=False)
    db.commit()

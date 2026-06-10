from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db import get_db
from dependencies import check_permissions
from models import UnifiedAlert, User
from services.unified_alerts import sync_factory_alerts, top_alerts


router = APIRouter(prefix="/api/alerts", tags=["alerts"])
ALLOWED_SEVERITIES = {"INFO", "WARNING", "CRITICAL"}
ALLOWED_STATUSES = {"OPEN", "ACKNOWLEDGED", "RESOLVED"}


def _serialize(row: UnifiedAlert) -> dict:
    return {
        "id": row.id, "title": row.title, "message": row.message,
        "severity": row.severity, "status": row.status, "source_module": row.source_module,
        "related_entity_type": row.related_entity_type, "related_entity_id": row.related_entity_id,
        "related_route": row.related_route, "suggested_action": row.suggested_action,
        "assigned_role": row.assigned_role, "first_detected_at": row.first_detected_at,
        "last_detected_at": row.last_detected_at,
    }


@router.get("")
def list_alerts(
    severity: str | None = Query(default=None),
    module: str | None = Query(default=None),
    alert_status: str | None = Query(default=None, alias="status"),
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db),
):
    sync_factory_alerts(db, current_user.factory_id, send_critical=True)
    query = db.query(UnifiedAlert).filter(UnifiedAlert.factory_id == current_user.factory_id)
    if severity:
        severity = severity.upper()
        if severity not in ALLOWED_SEVERITIES:
            raise HTTPException(status_code=422, detail="Invalid severity")
        query = query.filter(UnifiedAlert.severity == severity)
    if alert_status:
        alert_status = alert_status.upper()
        if alert_status not in ALLOWED_STATUSES:
            raise HTTPException(status_code=422, detail="Invalid status")
        query = query.filter(UnifiedAlert.status == alert_status)
    if module:
        query = query.filter(UnifiedAlert.source_module == module)
    rows = query.order_by(UnifiedAlert.last_detected_at.desc()).limit(200).all()
    db.commit()
    return {"items": [_serialize(row) for row in rows]}


@router.get("/top")
def get_top_alerts(
    limit: int = Query(default=5, ge=1, le=20),
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db),
):
    sync_factory_alerts(db, current_user.factory_id, send_critical=True)
    rows = top_alerts(db, current_user.factory_id, limit)
    db.commit()
    return {"items": [_serialize(row) for row in rows]}


def _change_status(db: Session, current_user: User, alert_id: int, new_status: str) -> dict:
    row = db.query(UnifiedAlert).filter(
        UnifiedAlert.id == alert_id,
        UnifiedAlert.factory_id == current_user.factory_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    now = datetime.now(timezone.utc)
    row.status = new_status
    if new_status == "ACKNOWLEDGED":
        row.acknowledged_at = now
        row.acknowledged_by_user_id = current_user.id
    else:
        row.resolved_at = now
        row.resolved_by_user_id = current_user.id
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.patch("/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db),
):
    return _change_status(db, current_user, alert_id, "ACKNOWLEDGED")


@router.patch("/{alert_id}/resolve")
def resolve_alert(
    alert_id: int,
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db),
):
    return _change_status(db, current_user, alert_id, "RESOLVED")

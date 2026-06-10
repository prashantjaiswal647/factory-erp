from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from dependencies import OWNER_ROLES, check_permissions
from models import User
from services.briefing_recovery_merge import compose_daily_briefing_with_recovery
from services.briefing_scheduler import deliver_factory_briefing
from services.telegram_delivery import send_telegram_message


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
    result = compose_daily_briefing_with_recovery(
        db, factory_id, briefing_date, current_user,
    )
    return result


@router.post("/preview")
def preview_briefing(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = int(current_user.factory_id)
    briefing_date = _briefing_date()
    result = compose_daily_briefing_with_recovery(
        db, factory_id, briefing_date, current_user,
    )
    return result


@router.post("/send")
def send_briefing_now(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    from models import Factory
    factory_id = int(current_user.factory_id)
    briefing_date = _briefing_date()
    factory = db.query(Factory).filter(Factory.id == factory_id).one()
    row, created = deliver_factory_briefing(
        db, factory, current_user, briefing_date,
        sender=send_telegram_message,
    )
    return {
        "id": row.id,
        "status": row.status,
        "channel": row.channel,
        "message_text": row.message_text,
        "idempotent_replay": not created,
    }


@router.get("/history")
def get_briefings_history(
    days: int = 30,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    from models import BriefingSnapshot
    from datetime import date, timedelta
    
    factory_id = int(current_user.factory_id)
    cutoff = date.today() - timedelta(days=days)
    
    # Retrieve briefings for the current factory, user's role (or user_id if specific)
    # Filter strictly by user's role: Sub-Owners see only Sub-Owner briefings. Owners see Owner briefings.
    role = current_user.role
    
    query = db.query(BriefingSnapshot).filter(
        BriefingSnapshot.factory_id == factory_id,
        BriefingSnapshot.role == role,
        BriefingSnapshot.briefing_date >= cutoff
    )
    
    # If Sub-Owner, mask or don't include user_id filter if they connects to the same subowner roles,
    # but to be safe, filter by the role "Sub-Owner"
    if role == "Sub-Owner":
        query = query.filter(BriefingSnapshot.user_id == current_user.id)

    snapshots = query.order_by(BriefingSnapshot.briefing_date.desc()).all()
    
    result = []
    for s in snapshots:
        js = s.snapshot_json or {}
        snap = js.get("snapshot") or {}
        rec = js.get("recovery_snapshot") or {}
        
        # Calculate summary values
        prod_total = None
        sales_total = None
        col_total = None
        out_total = None
        
        # Health score
        health_score = float(s.health_score) if s.health_score is not None else None
        
        # Extract operational summary metrics
        if "production" in snap:
            prod_total = snap["production"].get("total_boxes")
            
        if role == "Owner":
            if "sales" in snap:
                sales_total = snap["sales"].get("amount")
                out_total = snap["sales"].get("outstanding_amount")
            if rec:
                col_total = float(rec.get("yesterday_collections_paise", 0)) / 100.0
        else:
            # Sub-Owner is strictly operational (financial metrics are masked)
            sales_total = None
            col_total = None
            out_total = None
            
        # Top warning
        top_warning = None
        risk_items = snap.get("risk_items")
        if risk_items and len(risk_items) > 0:
            top_warning = risk_items[0].get("label") or risk_items[0].get("type")

        result.append({
            "id": s.id,
            "date": s.briefing_date.isoformat(),
            "status": s.status,
            "role_version": s.role,
            "message_text": s.message_text,
            "health_score": health_score,
            "production_total": prod_total,
            "sales_total": sales_total,
            "collections_total": col_total,
            "outstanding_total": out_total,
            "top_warning": top_warning,
            "sent_at": s.sent_at.isoformat() if s.sent_at else None,
        })
        
    return result


@router.get("/history/{briefing_id}")
def get_briefing_detail(
    briefing_id: int,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    from models import BriefingSnapshot
    from fastapi import HTTPException
    
    s = db.query(BriefingSnapshot).filter(
        BriefingSnapshot.id == briefing_id
    ).first()
    
    if not s:
        raise HTTPException(status_code=404, detail="Briefing not found.")
        
    # Enforce factory isolation
    if s.factory_id != current_user.factory_id:
        raise HTTPException(status_code=403, detail="Forbidden.")
        
    # Enforce role access limit
    if s.role != current_user.role:
        raise HTTPException(status_code=403, detail="Forbidden.")
        
    js = s.snapshot_json or {}
    
    # Enforce Sub-Owner financial masking
    if current_user.role == "Sub-Owner":
        # Mask financial fields in snapshot
        if "snapshot" in js and "sales" in js["snapshot"]:
            js["snapshot"]["sales"] = {
                "invoice_count": js["snapshot"]["sales"].get("invoice_count"),
                "amount": None,
                "collections_received": None,
                "outstanding_amount": None,
            }
        if "recovery_snapshot" in js:
            js["recovery_snapshot"] = {
                "yesterday_collections_paise": None,
                "total_outstanding_paise": None,
                "overdue_outstanding_paise": None,
                "aging_buckets": {},
                "top_due_customers": [],
            }

    return {
        "id": s.id,
        "factory_id": s.factory_id,
        "user_id": s.user_id,
        "role": s.role,
        "briefing_date": s.briefing_date.isoformat(),
        "message_text": s.message_text,
        "snapshot_json": js,
        "health_score": float(s.health_score) if s.health_score is not None else None,
        "status": s.status,
        "sent_at": s.sent_at.isoformat() if s.sent_at else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }

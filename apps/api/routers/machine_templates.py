from typing import Any, Dict, List, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, sessionmaker

from auth import check_permissions, get_current_user
from db import SessionLocal, get_db
from machine_template_verifier import verify_machine_template_submission
from models import MachineTemplate, User


router = APIRouter(tags=["machine-templates"])

TemplateStatus = Literal["processing", "pending", "approved", "rejected"]


class MachineTemplateCreate(BaseModel):
    machine_type: str = Field(..., min_length=1, max_length=100)
    base_config: Dict[str, Any] = Field(default_factory=dict)
    custom_fields: Dict[str, Any] = Field(default_factory=dict)


class MachineTemplateResponse(MachineTemplateCreate):
    id: int
    creator_id: int
    status: TemplateStatus
    ai_confidence: float | None = None
    ai_review: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


def notify_admin_for_manual_review(template: MachineTemplate) -> None:
    # Hook for email, Slack, n8n, or internal notification creation.
    print(f"Machine template {template.id} requires manual review.")


def run_ai_template_verification(template_id: int, session_factory: sessionmaker = SessionLocal) -> None:
    db = session_factory()
    try:
        template = db.query(MachineTemplate).filter(MachineTemplate.id == template_id).first()
        if template is None:
            return

        result = verify_machine_template_submission(db, template)
        template.ai_confidence = result.confidence_score
        template.ai_review = {"decision": result.decision, "reasons": result.reasons}
        template.status = "approved" if result.confidence_score > 0.9 else "pending"
        db.commit()
        db.refresh(template)

        if template.status == "pending":
            notify_admin_for_manual_review(template)
    finally:
        db.close()


def get_template_verification_runner():
    return run_ai_template_verification


@router.post("/templates/submit", response_model=MachineTemplateResponse, status_code=status.HTTP_201_CREATED)
def submit_template(
    payload: MachineTemplateCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db),
    verification_runner=Depends(get_template_verification_runner),
):
    template = MachineTemplate(
        creator_id=current_user.id,
        machine_type=payload.machine_type,
        base_config=payload.base_config,
        custom_fields=payload.custom_fields,
        status="processing",
        ai_review={},
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    background_tasks.add_task(verification_runner, template.id)
    return template


@router.get("/templates/{template_id}", response_model=MachineTemplateResponse)
def get_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    template = db.query(MachineTemplate).filter(MachineTemplate.id == template_id).first()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine template not found")
    if current_user.role != "Owner" and template.status != "approved" and template.creator_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine template not found")
    return template


@router.get("/templates", response_model=List[MachineTemplateResponse])
def list_templates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(MachineTemplate)
    if current_user.role != "Owner":
        query = query.filter(MachineTemplate.status == "approved")
    return query.order_by(MachineTemplate.created_at.desc(), MachineTemplate.id.desc()).all()


@router.patch("/admin/templates/{template_id}/approve", response_model=MachineTemplateResponse)
def approve_template(
    template_id: int,
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    template = db.query(MachineTemplate).filter(MachineTemplate.id == template_id).first()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine template not found")

    template.status = "approved"
    template.ai_review = {
        **(template.ai_review or {}),
        "manual_approval": True,
        "approved_by": current_user.id,
    }
    db.commit()
    db.refresh(template)
    return template

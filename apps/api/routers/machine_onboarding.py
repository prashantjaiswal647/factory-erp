from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from auth import get_current_user
from db import get_db
from models import MachineOnboarding, User


router = APIRouter(prefix="/api/machine-onboardings", tags=["machine-onboardings"])


class MachineOnboardingCreate(BaseModel):
    machine_type: str = Field(..., min_length=1, max_length=100)
    base_config: Dict[str, Any] = Field(default_factory=dict)
    custom_fields: Dict[str, Any] = Field(default_factory=dict)


class MachineOnboardingResponse(MachineOnboardingCreate):
    id: int
    factory_id: int

    model_config = ConfigDict(from_attributes=True)


@router.post("", response_model=MachineOnboardingResponse, status_code=status.HTTP_201_CREATED)
def create_machine_onboarding(
    payload: MachineOnboardingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    machine = MachineOnboarding(
        factory_id=current_user.factory_id,
        machine_type=payload.machine_type,
        base_config=payload.base_config,
        custom_fields=payload.custom_fields,
    )
    db.add(machine)
    db.commit()
    db.refresh(machine)
    return machine


@router.get("", response_model=List[MachineOnboardingResponse])
def list_machine_onboardings(
    custom_field_key: Optional[str] = Query(default=None, max_length=100),
    custom_field_value: Optional[str] = Query(default=None, max_length=255),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(MachineOnboarding).filter(MachineOnboarding.factory_id == current_user.factory_id)

    if custom_field_key and custom_field_value is not None:
        query = query.filter(MachineOnboarding.custom_fields[custom_field_key].as_string() == custom_field_value)

    return query.order_by(MachineOnboarding.created_at.desc(), MachineOnboarding.id.desc()).all()


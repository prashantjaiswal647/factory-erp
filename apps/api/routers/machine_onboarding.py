from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from auth import get_current_user
from dependencies import MACHINE_VIEW_ROLES, OWNER_ROLES, check_permissions
from db import get_db
from models import Machine, MachineOnboarding, User


router = APIRouter(prefix="/api/machine-onboardings", tags=["machine-onboardings"])
machines_router = APIRouter(prefix="/api/machines", tags=["machines"])


class MachineOnboardingCreate(BaseModel):
    machine_type: str = Field(..., min_length=1, max_length=100)
    base_config: Dict[str, Any] = Field(default_factory=dict)
    custom_fields: Dict[str, Any] = Field(default_factory=dict)


class MachineOnboardingResponse(MachineOnboardingCreate):
    id: int
    factory_id: int

    model_config = ConfigDict(from_attributes=True)


class DynamicMachineSetupCreate(BaseModel):
    machine_name: str = Field(..., min_length=1, max_length=255)
    default_speed: float = Field(default=0, ge=0)
    target_output_per_shift: int = Field(default=0, ge=0)
    raw_materials_mapped: List[str] = Field(default_factory=list)
    is_active: bool = True


class DynamicMachineSetupResponse(DynamicMachineSetupCreate):
    id: int
    factory_id: int


def _clean_materials(materials: List[str]) -> List[str]:
    return [item.strip() for item in materials if item and item.strip()]


def _dynamic_machine_response(machine: Machine) -> Dict[str, Any]:
    machine_name = machine.machine_name or machine.machine_type or machine.name
    return {
        "id": machine.id,
        "factory_id": int(machine.factory_id),
        "machine_name": machine_name,
        "default_speed": float(machine.default_speed or machine.speed_per_minute or machine.speed_cups_per_minute or machine.speed_bpm or 0),
        "target_output_per_shift": int(machine.target_output_per_shift or 0),
        "raw_materials_mapped": machine.raw_materials_mapped or [],
        "is_active": bool(machine.is_active),
    }


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


@machines_router.post("/setup", response_model=DynamicMachineSetupResponse, status_code=status.HTTP_201_CREATED)
def setup_dynamic_machine(
    payload: DynamicMachineSetupCreate,
    current_user: User = Depends(check_permissions(MACHINE_VIEW_ROLES)),
    db: Session = Depends(get_db),
):
    machine_name = " ".join(payload.machine_name.strip().split())
    factory_id = current_user.factory_id
    existing = (
        db.query(Machine)
        .filter(Machine.factory_id == factory_id)
        .filter(
            (sql_func.lower(Machine.machine_name) == machine_name.lower())
            | (sql_func.lower(Machine.name) == machine_name.lower())
        )
        .first()
    )
    speed_int = int(payload.default_speed or 0)
    materials = _clean_materials(payload.raw_materials_mapped)

    if existing is None:
        existing = Machine(
            factory_id=factory_id,
            name=machine_name,
            machine_type=machine_name,
            machine_name=machine_name,
            machine_number=None,
            machine_sequence_number=None,
        )
        db.add(existing)

    existing.machine_type = machine_name
    existing.machine_name = machine_name
    existing.default_speed = payload.default_speed or 0
    existing.speed_per_minute = speed_int
    existing.speed_bpm = speed_int
    existing.speed_cups_per_minute = speed_int
    existing.target_output_per_shift = payload.target_output_per_shift or 0
    existing.raw_materials_mapped = materials
    existing.is_active = payload.is_active

    db.commit()
    db.refresh(existing)
    return _dynamic_machine_response(existing)


@machines_router.get("/active", response_model=List[DynamicMachineSetupResponse])
def list_active_dynamic_machines(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    machines = (
        db.query(Machine)
        .filter(Machine.factory_id == current_user.factory_id)
        .filter(Machine.is_active.is_(True))
        .order_by(Machine.machine_name.asc(), Machine.id.asc())
        .all()
    )
    return [_dynamic_machine_response(machine) for machine in machines]

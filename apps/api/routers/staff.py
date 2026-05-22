from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func as sql_func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import get_user_by_phone, hash_password, normalize_phone_number, require_owner
from db import get_db
from models import User


router = APIRouter(prefix="/api/staff", tags=["staff"])
v1_router = APIRouter(prefix="/api/v1/users", tags=["staff"])


class StaffCreateRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    country_code: str = Field(default="+91", min_length=1, max_length=8)
    phone_number: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6, max_length=255)
    role: Literal["sub_owner", "supervisor", "worker"]


class StaffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str | None = None
    full_name: str | None = None
    phone_number: str | None = None
    role: str
    factory_id: int


def normalize_staff_role(role: str) -> str:
    if role == "sub_owner":
        return "Sub-Owner"
    if role == "supervisor":
        return "Supervisor"
    return "Operator"


def ensure_primary_owner(current_user: User) -> None:
    if current_user.role != "Owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Owner can manage Sub-Owners",
        )


@router.get("", response_model=list[StaffResponse])
def list_staff(
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    return (
        db.query(User)
        .filter(User.factory_id == current_user.factory_id)
        .filter(User.role.in_(["Sub-Owner", "Supervisor", "Operator"]))
        .order_by(User.full_name.asc().nullslast(), User.username.asc())
        .all()
    )


@router.post("/create", response_model=StaffResponse, status_code=status.HTTP_201_CREATED)
@v1_router.post("/create-staff", response_model=StaffResponse, status_code=status.HTTP_201_CREATED)
def create_staff(
    payload: StaffCreateRequest,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    if payload.role == "sub_owner":
        ensure_primary_owner(current_user)

    phone_number, phone_number_normalized = normalize_phone_number(payload.phone_number, payload.country_code)
    full_name = payload.full_name.strip()

    if not phone_number:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="phone_number cannot be blank",
        )
    if not full_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="full_name cannot be blank",
        )

    existing_user = get_user_by_phone(db, phone_number)
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phone number already exists",
        )

    staff_user = User(
        user_id=str(uuid4()),
        factory_id=current_user.factory_id,
        username=phone_number,
        phone_number=phone_number,
        phone_number_normalized=phone_number_normalized,
        full_name=full_name,
        password_hash=hash_password(payload.password),
        role=normalize_staff_role(payload.role),
        is_verified=True,
    )

    try:
        db.add(staff_user)
        db.commit()
        db.refresh(staff_user)
        return staff_user
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phone number already exists",
        ) from exc


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_staff(
    user_id: int,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    staff_user = (
        db.query(User)
        .filter(User.id == user_id)
        .filter(User.factory_id == current_user.factory_id)
        .first()
    )
    if staff_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if staff_user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot delete your own account")

    if staff_user.role == "Owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Original Owner cannot be deleted")

    if staff_user.role == "Sub-Owner":
        ensure_primary_owner(current_user)

    if staff_user.role not in {"Sub-Owner", "Supervisor", "Operator"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This user cannot be deleted here")

    db.delete(staff_user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from dependencies import check_permissions
from models import User
from services.go_live_reset import confirm_go_live_reset, preview_go_live_reset


router = APIRouter(prefix="/api/admin/go-live-reset", tags=["go-live-reset"])


class PreviewRequest(BaseModel):
    scope: Literal["sales", "production", "all"]


class OpeningOutstanding(BaseModel):
    customer_id: int
    amount: Decimal = Field(ge=0)


class InvoiceStarts(BaseModel):
    tax_invoice: int = Field(default=1, ge=1)
    bill_of_supply: int = Field(default=1, ge=1)
    simple_bill: int = Field(default=1, ge=1)


class ConfirmRequest(PreviewRequest):
    confirmation: str
    reason: str = Field(min_length=5, max_length=1000)
    inventory_mode: Literal["keep_current", "restore_baseline"] = "keep_current"
    invoice_starts: InvoiceStarts = Field(default_factory=InvoiceStarts)
    opening_outstanding: list[OpeningOutstanding] = Field(default_factory=list)


@router.post("/preview")
def preview_reset(
    payload: PreviewRequest,
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    return preview_go_live_reset(db, int(current_user.factory_id), payload.scope)


@router.post("/confirm")
def confirm_reset(
    payload: ConfirmRequest,
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    if payload.confirmation != "RESET LIVE START":
        raise HTTPException(status_code=422, detail="Type RESET LIVE START to confirm")
    try:
        return confirm_go_live_reset(
            db,
            int(current_user.factory_id),
            int(current_user.id),
            scope=payload.scope,
            inventory_mode=payload.inventory_mode,
            reason=payload.reason.strip(),
            invoice_starts=payload.invoice_starts.model_dump(),
            opening_outstanding=[item.model_dump() for item in payload.opening_outstanding],
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Go-live reset failed and all database changes were rolled back.",
        ) from exc

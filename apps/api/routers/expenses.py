from datetime import datetime
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from dependencies import EXPENSE_ROLES, check_permissions
from db import get_db
from models import FactoryExpense, User


router = APIRouter(prefix="/api/expenses", tags=["expenses"])


class ExpenseCreate(BaseModel):
    expense_name: str = Field(..., min_length=1, max_length=255)
    amount: Decimal = Field(..., ge=0)
    category: str = Field(default="General", min_length=1, max_length=100)


class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factory_id: int
    expense_name: str
    amount: Decimal
    category: str
    timestamp: datetime


@router.post("", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
def create_expense(
    payload: ExpenseCreate,
    current_user: User = Depends(check_permissions(EXPENSE_ROLES)),
    db: Session = Depends(get_db),
):
    expense_name = payload.expense_name.strip()
    category = payload.category.strip() or "General"
    if not expense_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="expense_name cannot be blank",
        )

    expense = FactoryExpense(
        factory_id=current_user.factory_id,
        expense_name=expense_name,
        amount=payload.amount,
        category=category,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


@router.get("", response_model=List[ExpenseResponse])
def list_expenses(
    current_user: User = Depends(check_permissions(EXPENSE_ROLES)),
    db: Session = Depends(get_db),
):
    try:
        res = (
            db.query(FactoryExpense)
            .filter(FactoryExpense.factory_id == current_user.factory_id)
            .order_by(FactoryExpense.timestamp.desc(), FactoryExpense.id.desc())
            .limit(50)
            .all()
        )
        return res if res else []
    except Exception:
        return []

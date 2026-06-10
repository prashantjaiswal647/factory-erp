from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from dependencies import EXPENSE_ROLES, check_permissions
from db import get_db
from models import FactoryExpense, User, UnifiedAlert
from services.activity_logger import log_activity
from services.telegram_action_alerts import notify_expense_above_threshold

router = APIRouter(prefix="/api/expenses", tags=["expenses"])

class ExpenseCreate(BaseModel):
    expense_name: str = Field(..., min_length=1, max_length=255)
    amount: Decimal = Field(..., ge=0)
    category: str = Field(default="General", min_length=1, max_length=100)
    machine_id: Optional[int] = None

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
    background_tasks: BackgroundTasks,
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
        machine_id=payload.machine_id,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)

    # P4.5 D1: high-amount expense alert (best-effort, never raises)
    try:
        from models import Factory as _Factory
        from services.telegram_action_alerts import DEFAULT_EXPENSE_THRESHOLD_PAISE
        threshold_paise = int(
            __import__("os").getenv("EXPENSE_ALERT_THRESHOLD_PAISE", str(DEFAULT_EXPENSE_THRESHOLD_PAISE))
        )
        amount_paise = int(round(float(payload.amount) * 100))
        if amount_paise >= threshold_paise:
            _f = db.query(_Factory).filter(_Factory.id == current_user.factory_id).first()
            if _f is not None:
                notify_expense_above_threshold(
                    db,
                    factory=_f,
                    actor=current_user,
                    category=category,
                    amount_paise=amount_paise,
                    threshold_paise=threshold_paise,
                )
    except Exception:  # noqa: BLE001
        pass

    background_tasks.add_task(
        log_activity,
        db,
        int(current_user.factory_id),
        current_user.id,
        current_user.full_name or current_user.username,
        current_user.role,
        "EXPENSE_RECORDED",
        f"₹{payload.amount:,.2f} for {category}",
        "expense",
        expense.id,
        {"expense_name": expense_name, "category": category},
    )
    return expense

@router.get("", response_model=List[ExpenseResponse])
def list_expenses(
    current_user: User = Depends(check_permissions(EXPENSE_ROLES)),
    db: Session = Depends(get_db),
):
    return db.query(FactoryExpense)\
        .filter(FactoryExpense.factory_id == current_user.factory_id)\
        .order_by(FactoryExpense.timestamp.desc(), FactoryExpense.id.desc())\
        .limit(50)\
        .all()

@router.get("/alerts", response_model=None)
def get_expense_alerts(
    current_user: User = Depends(check_permissions(EXPENSE_ROLES)),
    db: Session = Depends(get_db),
):
    return db.query(UnifiedAlert)\
        .filter(UnifiedAlert.factory_id == current_user.factory_id,
                UnifiedAlert.source_module == "expenses",
                UnifiedAlert.status == "OPEN")\
        .all()

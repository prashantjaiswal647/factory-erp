from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from auth import get_current_user
from db import get_db
from models import Customer, User
from schemas import CustomerCreate, CustomerResponse


router = APIRouter()


@router.post("/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_sales_customer(
    payload: CustomerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total_due = payload.total_due if payload.total_due is not None else payload.previous_due
    customer = Customer(
        factory_id=current_user.factory_id,
        name=payload.name.strip(),
        address=payload.address,
        phone=payload.phone,
        contact_number=payload.phone,
        previous_due=payload.previous_due,
        total_due=total_due,
        pending_balance=total_due,
        balance_amount=total_due,
        pending_dues=float(total_due),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer

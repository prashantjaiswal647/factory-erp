from decimal import Decimal
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from dependencies import OWNER_ROLES, check_permissions
from db import get_db
from models import (
    BlankStock,
    BottomStock,
    BoxStock,
    Customer,
    Factory,
    FinalProductStock,
    Machine,
    PolybagStock,
    User,
    Worker,
)
from schemas import (
    BlankStockBatchCreate,
    BlankStockResponse,
    BottomStockCreate,
    BottomStockResponse,
    BoxStockCreate,
    BoxStockResponse,
    CustomerCreate,
    CustomerResponse,
    FactoryInfoCreate,
    FactoryInfoResponse,
    FinalProductStockCreate,
    FinalProductStockResponse,
    MachineCreate,
    MachineResponse,
    PolybagStockCreate,
    PolybagStockResponse,
    WorkerCreate,
    WorkerResponse,
)


router = APIRouter(prefix="/api/setup", tags=["phase-1-setup"])


def normalize_name(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Name fields cannot be blank",
        )
    return normalized


@router.post("/factory", response_model=FactoryInfoResponse, status_code=status.HTTP_201_CREATED)
def create_or_update_factory_info(
    payload: FactoryInfoCreate,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    factory_name = normalize_name(payload.factory_name)
    factory = None
    if current_user.factory_id and current_user.factory_id > 0:
        factory = db.query(Factory).filter(Factory.id == current_user.factory_id).first()

    if factory is None:
        factory = Factory(name=factory_name, factory_name=factory_name, owner_id=current_user.id)
        db.add(factory)
        db.flush()
        current_user.factory_id = factory.id
    else:
        factory.name = factory_name
        factory.factory_name = factory_name
        factory.owner_id = current_user.id

    db.commit()
    db.refresh(factory)
    return FactoryInfoResponse(id=factory.id, factory_name=factory.factory_name or factory.name, owner_id=factory.owner_id)


@router.post("/machines", response_model=MachineResponse, status_code=status.HTTP_201_CREATED)
def create_machine(
    payload: MachineCreate,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = current_user.factory_id
    machine_number = normalize_name(payload.machine_number).upper()
    existing = (
        db.query(Machine)
        .filter(Machine.factory_id == factory_id)
        .filter(sql_func.lower(Machine.machine_number) == machine_number.lower())
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Machine number already exists")

    machine = Machine(
        factory_id=factory_id,
        name=machine_number,
        machine_type=payload.machine_type,
        machine_number=machine_number,
        machine_sequence_number=machine_number,
        mould_size_ml=payload.mould_size_ml,
        cup_size_ml=payload.mould_size_ml,
        bottom_size_mm=payload.bottom_size_mm,
        speed_per_minute=payload.speed_per_minute,
        speed_bpm=payload.speed_per_minute,
        speed_cups_per_minute=payload.speed_per_minute,
    )
    db.add(machine)
    db.commit()
    db.refresh(machine)
    return machine


@router.post("/stock/blanks", response_model=List[BlankStockResponse])
def upsert_blank_stock_batches(
    payload: BlankStockBatchCreate,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    totals_by_size: Dict[int, Decimal] = {}
    for batch in payload.batches:
        batch_total = Decimal(batch.weight_per_sack) * Decimal(batch.total_sacks)
        totals_by_size[batch.blank_size_ml] = totals_by_size.get(batch.blank_size_ml, Decimal("0")) + batch_total

    saved = []
    for blank_size_ml, total_weight in totals_by_size.items():
        stock = (
            db.query(BlankStock)
            .filter(BlankStock.factory_id == current_user.factory_id)
            .filter(BlankStock.blank_size_ml == blank_size_ml)
            .with_for_update()
            .first()
        )
        if stock is None:
            stock = BlankStock(
                factory_id=current_user.factory_id,
                blank_size_ml=blank_size_ml,
                linked_bottom_size_mm=payload.linked_bottom_size_mm,
                total_qty_kg=Decimal("0.000"),
            )
            db.add(stock)
        stock.linked_bottom_size_mm = payload.linked_bottom_size_mm
        stock.total_qty_kg = Decimal(stock.total_qty_kg or 0) + total_weight
        saved.append(stock)

    db.commit()
    for stock in saved:
        db.refresh(stock)
    return saved


@router.post("/stock/bottoms", response_model=BottomStockResponse, status_code=status.HTTP_201_CREATED)
def upsert_bottom_stock(
    payload: BottomStockCreate,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    stock = (
        db.query(BottomStock)
        .filter(BottomStock.factory_id == current_user.factory_id)
        .filter(BottomStock.bottom_size_mm == payload.bottom_size_mm)
        .with_for_update()
        .first()
    )
    if stock is None:
        stock = BottomStock(factory_id=current_user.factory_id, bottom_size_mm=payload.bottom_size_mm)
        db.add(stock)
    stock.total_qty_kg = payload.total_qty_kg
    db.commit()
    db.refresh(stock)
    return stock


@router.post("/stock/boxes", response_model=BoxStockResponse, status_code=status.HTTP_201_CREATED)
def upsert_box_stock(
    payload: BoxStockCreate,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    packaging_size_name = normalize_name(payload.packaging_size_name)
    stock = (
        db.query(BoxStock)
        .filter(BoxStock.factory_id == current_user.factory_id)
        .filter(sql_func.lower(BoxStock.packaging_size_name) == packaging_size_name.lower())
        .with_for_update()
        .first()
    )
    if stock is None:
        stock = BoxStock(factory_id=current_user.factory_id, packaging_size_name=packaging_size_name)
        db.add(stock)
    stock.total_boxes = payload.total_boxes
    db.commit()
    db.refresh(stock)
    return stock


@router.post("/stock/polybags", response_model=PolybagStockResponse, status_code=status.HTTP_201_CREATED)
def upsert_polybag_stock(
    payload: PolybagStockCreate,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    packaging_size_name = normalize_name(payload.packaging_size_name)
    stock = (
        db.query(PolybagStock)
        .filter(PolybagStock.factory_id == current_user.factory_id)
        .filter(sql_func.lower(PolybagStock.packaging_size_name) == packaging_size_name.lower())
        .with_for_update()
        .first()
    )
    if stock is None:
        stock = PolybagStock(factory_id=current_user.factory_id, packaging_size_name=packaging_size_name)
        db.add(stock)
    stock.total_packets = payload.total_packets
    db.commit()
    db.refresh(stock)
    return stock


@router.post("/workers", response_model=WorkerResponse, status_code=status.HTTP_201_CREATED)
def create_worker(
    payload: WorkerCreate,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    worker = Worker(
        factory_id=current_user.factory_id,
        name=normalize_name(payload.name),
        daily_wages=payload.daily_wages,
        duty_hours=payload.duty_hours,
        daily_salary=payload.daily_wages,
        salary=payload.daily_wages,
        shift_hours=payload.duty_hours,
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return worker


@router.post("/stock/final-products", response_model=FinalProductStockResponse, status_code=status.HTTP_201_CREATED)
def upsert_final_product_stock(
    payload: FinalProductStockCreate,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    packaging_size_name = normalize_name(payload.packaging_size_name)
    stock = (
        db.query(FinalProductStock)
        .filter(FinalProductStock.factory_id == current_user.factory_id)
        .filter(FinalProductStock.product_size_ml == payload.product_size_ml)
        .filter(sql_func.lower(FinalProductStock.packaging_size_name) == packaging_size_name.lower())
        .with_for_update()
        .first()
    )
    if stock is None:
        stock = FinalProductStock(
            factory_id=current_user.factory_id,
            product_size_ml=payload.product_size_ml,
            packaging_size_name=packaging_size_name,
            current_quantity=payload.total_boxes,
            total_boxes=payload.total_boxes,
            loose_packets=payload.loose_packets,
            packets_per_box_limit=payload.packets_per_box_limit,
        )
        db.add(stock)
    stock.current_quantity = payload.total_boxes
    stock.total_boxes = payload.total_boxes
    stock.loose_packets = payload.loose_packets
    stock.packets_per_box_limit = payload.packets_per_box_limit
    db.commit()
    db.refresh(stock)
    return stock


@router.post("/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    customer = Customer(
        factory_id=current_user.factory_id,
        name=normalize_name(payload.name),
        address=payload.address,
        phone=payload.phone,
        contact_number=payload.phone,
        previous_due=payload.previous_due,
        total_due=payload.total_due,
        pending_balance=payload.total_due,
        balance_amount=payload.total_due,
        pending_dues=float(payload.total_due),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer

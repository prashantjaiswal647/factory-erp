import logging
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from auth import normalize_phone_number, require_owner
from dependencies import OWNER_ROLES, check_permissions
from db import get_db
from models import (
    BlankStock,
    BottomStock,
    BoxStock,
    CostingMaster,
    Customer,
    Employee,
    Factory,
    FinalProductStock,
    FinishedGoodsStock,
    Inventory,
    Machine,
    MaterialYield,
    PackagingProfile,
    RawMaterial,
    RawMaterialMetrics,
    PackagingMetrics,
    PlasticStock,
    User,
    Worker,
    WorkerOpeningAttendance,
)
from schemas import (
    CustomerPayload,
    MachinePayload,
    MaterialYieldPayload,
    OnboardingCompleteRequest,
    OnboardingCompleteResponse,
    PackagingProfilePayload,
    RawMaterialPayload,
    Step1Request,
    Step1Response,
    Step2MachineItem,
    Step2Request,
    Step2Response,
    Step3PackagingMetricItem,
    Step3RawMaterialMetricItem,
    Step3Request,
    Step3Response,
    BoxStockCreate,
    PlasticStockCreate,
    WorkerCreate,
    WorkerPayload,
    WorkerResponse,
)
from subscription_limits import check_machine_limit, get_machine_limit_usage


router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])
logger = logging.getLogger(__name__)


class OnboardingWorkerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    daily_wages: Decimal
    duty_hours: float


class OnboardingMachineSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    machine_type: str
    machine_number: Optional[str] = None
    mould_size_ml: Optional[int] = None
    bottom_size_mm: Optional[int] = None
    speed_per_minute: int


class OnboardingRawMetricSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_type: str
    size_ml_or_mm: int
    weight_per_sack_kg: Decimal
    pieces_per_sack: int


class OnboardingPackagingMetricSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cup_size_ml: int
    kg_per_box: Decimal
    cups_per_box: int


class OnboardingOverviewResponse(BaseModel):
    workers: List[OnboardingWorkerSummary]
    machines: List[OnboardingMachineSummary]
    raw_material_metrics: List[OnboardingRawMetricSummary]
    packaging_metrics: List[OnboardingPackagingMetricSummary]


class MachineLimitResponse(BaseModel):
    used: int
    limit: int
    plan: str
    nearing_limit: bool
    limit_reached: bool


class OnboardingCustomerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: Optional[str] = None
    total_due: Decimal


class FinalProductOpeningStockRequest(BaseModel):
    product_id: Optional[int] = Field(default=None, gt=0)
    product_size_ml: Optional[int] = Field(default=None, gt=0)
    variety: str = Field(default="Standard/White", max_length=100)
    packaging_size: Optional[str] = Field(default=None, max_length=100)
    packaging_size_name: Optional[str] = Field(default=None, max_length=100)
    initial_quantity: int = Field(default=0, ge=0)
    current_quantity: Optional[int] = Field(default=None, ge=0)
    total_boxes: Optional[int] = Field(default=None, ge=0)
    loose_packets: int = Field(default=0, ge=0)
    pieces_per_packet: int = Field(default=1, gt=0)
    packets_per_box: Optional[int] = Field(default=None, gt=0)
    packets_per_box_limit: Optional[int] = Field(default=None, gt=0)
    category: Optional[str] = None


class FinalProductOpeningStockResponse(BaseModel):
    id: int
    factory_id: str
    product_size_ml: Optional[int] = None
    variety: Optional[str] = None
    packaging_size: Optional[str] = None
    packaging_size_name: Optional[str] = None
    pieces_per_packet: Optional[int] = None
    packets_per_box: Optional[int] = None
    current_quantity: Optional[int] = None
    total_boxes: Optional[int] = None
    loose_packets: Optional[int] = None
    packets_per_box_limit: Optional[int] = None


class BottomStockCreate(BaseModel):
    bottom_size_mm: int = Field(..., gt=0)
    bag_weight_kg: Optional[Decimal] = Field(default=None, ge=0)
    rolls_per_bag: Optional[int] = Field(default=None, ge=0)
    total_bags: Optional[int] = Field(default=None, ge=0)
    total_rolls: Optional[int] = Field(default=None, ge=0)
    total_weight_kg: Optional[Decimal] = Field(default=None, ge=0)


class BlankStockCreate(BaseModel):
    material_name: str = Field(default="Blank", max_length=100)
    size_ml: int = Field(..., gt=0)
    kg_per_sack: Decimal = Field(..., gt=0)
    total_sacks: Decimal = Field(..., ge=0)


@router.get("/overview", response_model=OnboardingOverviewResponse)
def onboarding_overview(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    return OnboardingOverviewResponse(
        workers=(
            db.query(Worker)
            .filter(Worker.factory_id == factory_id)
            .filter(Worker.is_active.is_(True))
            .order_by(Worker.name.asc())
            .all()
        ),
        machines=(
            db.query(Machine)
            .filter(Machine.factory_id == factory_id)
            .order_by(Machine.machine_number.asc().nullslast(), Machine.name.asc())
            .all()
        ),
        raw_material_metrics=(
            db.query(RawMaterialMetrics)
            .filter(RawMaterialMetrics.factory_id == factory_id)
            .order_by(RawMaterialMetrics.material_type.asc(), RawMaterialMetrics.size_ml_or_mm.asc())
            .all()
        ),
        packaging_metrics=(
            db.query(PackagingMetrics)
            .filter(PackagingMetrics.factory_id == factory_id)
            .order_by(PackagingMetrics.cup_size_ml.asc())
            .all()
        ),
    )


@router.post("/final-stock", response_model=FinalProductOpeningStockResponse)
def save_final_product_opening_stock(
    payload: FinalProductOpeningStockRequest,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    try:
        # Dynamic fallback parameters injection
        product_size_ml = payload.product_size_ml if payload.product_size_ml is not None else 210
        packaging_size_name = (payload.packaging_size_name or payload.packaging_size or f"{product_size_ml}ml Standard Box").strip()
        packets_per_box_limit = payload.packets_per_box_limit or payload.packets_per_box or 1000
        
        quantity = payload.current_quantity
        if quantity is None:
            quantity = payload.total_boxes
        if quantity is None:
            quantity = payload.initial_quantity
        if quantity is None:
            quantity = 0

        # Database transactional safety: Ensure raw dependency records exist dynamically in background
        profile = db.query(PackagingProfile).filter(
            PackagingProfile.factory_id == str(current_user.factory_id),
            PackagingProfile.cup_size_ml == product_size_ml,
            sql_func.lower(PackagingProfile.profile_name) == packaging_size_name.lower(),
        ).first()

        if not profile:
            logger.info(f"Injecting dynamic default PackagingProfile '{packaging_size_name}' for size {product_size_ml}ml.")
            poly_inventory = get_or_create_inventory(db, str(current_user.factory_id), f"{product_size_ml}ml Polybag", "Packaging", "pieces")
            box_inventory = get_or_create_inventory(db, str(current_user.factory_id), packaging_size_name, "Packaging", "pieces")
            cups_per_poly = payload.pieces_per_packet if payload.pieces_per_packet and payload.pieces_per_packet > 0 else 1
            profile = PackagingProfile(
                factory_id=str(current_user.factory_id),
                profile_name=packaging_size_name,
                product_name=f"{product_size_ml}ml Paper Cup",
                product_name_ml=product_size_ml,
                cup_size_ml=product_size_ml,
                polybag_capacity=cups_per_poly,
                box_capacity=cups_per_poly * packets_per_box_limit,
                box_size_name=packaging_size_name,
                cups_per_poly=cups_per_poly,
                cups_per_polybag=cups_per_poly,
                polys_per_box=packets_per_box_limit,
                polybags_per_box=packets_per_box_limit,
                box_inventory_id=box_inventory.id,
                poly_inventory_id=poly_inventory.id
            )
            db.add(profile)
            db.flush()

        stock_fg = db.query(FinishedGoodsStock).filter(
            FinishedGoodsStock.factory_id == str(current_user.factory_id),
            FinishedGoodsStock.packaging_profile_id == profile.id
        ).first()

        if not stock_fg:
            logger.info(f"Injecting dynamic default FinishedGoodsStock for size {product_size_ml}ml.")
            stock_fg = FinishedGoodsStock(
                factory_id=str(current_user.factory_id),
                cup_size_ml=product_size_ml,
                packaging_profile_id=profile.id,
                boxes_available=0
            )
            db.add(stock_fg)
            db.flush()

        if payload.product_id:
            stock = (
                db.query(FinalProductStock)
                .filter(FinalProductStock.factory_id == str(current_user.factory_id))
                .filter(FinalProductStock.id == payload.product_id)
                .with_for_update()
                .first()
            )
            if stock is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Final product stock item not found")
        else:
            stock = (
                db.query(FinalProductStock)
                .filter(FinalProductStock.factory_id == str(current_user.factory_id))
                .filter(FinalProductStock.product_size_ml == product_size_ml)
                .filter(FinalProductStock.variety == payload.variety)
                .filter(FinalProductStock.packaging_size_name == packaging_size_name)
                .with_for_update()
                .first()
            )
            if stock is None:
                stock = FinalProductStock(
                    factory_id=str(current_user.factory_id),
                    product_size_ml=product_size_ml,
                    variety=payload.variety,
                    packaging_size_name=packaging_size_name,
                    pieces_per_packet=payload.pieces_per_packet if payload.pieces_per_packet else 1,
                    packets_per_box_limit=packets_per_box_limit,
                )
                db.add(stock)

        stock.packaging_size_name = packaging_size_name
        stock.packets_per_box_limit = packets_per_box_limit
        stock.variety = payload.variety
        stock.pieces_per_packet = payload.pieces_per_packet if payload.pieces_per_packet else 1
        stock.current_quantity = quantity
        stock.total_boxes = quantity
        stock.loose_packets = payload.loose_packets if payload.loose_packets is not None else 0
        
        db.commit()

        # Synchronize PackagingMetrics for Dashboard mapping
        metric = (
            db.query(PackagingMetrics)
            .filter(PackagingMetrics.factory_id == str(current_user.factory_id))
            .filter(PackagingMetrics.cup_size_ml == product_size_ml)
            .first()
        )
        if metric is None:
            metric = PackagingMetrics(
                factory_id=str(current_user.factory_id),
                cup_size_ml=product_size_ml,
                kg_per_box=Decimal("10.000"),
                cups_per_box=packets_per_box_limit,
            )
            db.add(metric)
        else:
            metric.cups_per_box = packets_per_box_limit
        db.commit()

        db.refresh(stock)
        
        # Synchronize caches to opening balance immediately
        from routers.inventory import recalculate_and_sync_sku_stock
        recalculate_and_sync_sku_stock(
            db=db,
            factory_id=str(current_user.factory_id),
            product_size_ml=product_size_ml,
            variety=payload.variety,
            packaging_size_name=packaging_size_name,
        )
        db.refresh(stock)
        
        # Enforce string representation for factory_id in return payload
        return FinalProductOpeningStockResponse(
            id=stock.id,
            factory_id=str(stock.factory_id),
            product_size_ml=stock.product_size_ml,
            variety=stock.variety or "Standard/White",
            packaging_size=stock.packaging_size_name,
            packaging_size_name=stock.packaging_size_name,
            pieces_per_packet=stock.pieces_per_packet,
            packets_per_box=stock.packets_per_box_limit,
            current_quantity=stock.current_quantity if stock.current_quantity is not None else 0,
            total_boxes=stock.total_boxes or 0,
            loose_packets=stock.loose_packets or 0,
            packets_per_box_limit=stock.packets_per_box_limit,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/workers", response_model=List[OnboardingWorkerSummary])
def list_onboarding_workers(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    return (
        db.query(Worker)
        .filter(Worker.factory_id == str(current_user.factory_id))
        .filter(Worker.is_active.is_(True))
        .order_by(Worker.name.asc())
        .all()
    )


@router.get("/machines", response_model=List[OnboardingMachineSummary])
def list_onboarding_machines(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    return (
        db.query(Machine)
        .filter(Machine.factory_id == str(current_user.factory_id))
        .order_by(Machine.machine_number.asc().nullslast(), Machine.name.asc())
        .all()
    )


@router.get("/machines/limits", response_model=MachineLimitResponse)
def get_machine_limits(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    usage = get_machine_limit_usage(db, str(current_user.factory_id))
    return MachineLimitResponse(
        used=usage.used,
        limit=usage.limit,
        plan=usage.plan,
        nearing_limit=usage.used >= max(usage.limit - 1, 0),
        limit_reached=usage.used >= usage.limit,
    )


@router.get("/materials")
def list_onboarding_materials(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    return {
        "raw_material_metrics": (
            db.query(RawMaterialMetrics)
            .filter(RawMaterialMetrics.factory_id == factory_id)
            .order_by(RawMaterialMetrics.material_type.asc(), RawMaterialMetrics.size_ml_or_mm.asc())
            .all()
        ),
        "packaging_metrics": (
            db.query(PackagingMetrics)
            .filter(PackagingMetrics.factory_id == factory_id)
            .order_by(PackagingMetrics.cup_size_ml.asc())
            .all()
        ),
    }


@router.get("/customers", response_model=List[OnboardingCustomerSummary])
def list_onboarding_customers(
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    return (
        db.query(Customer)
        .filter(Customer.factory_id == str(current_user.factory_id))
        .order_by(Customer.name.asc())
        .all()
    )


@router.post("/raw-material/blank", status_code=status.HTTP_201_CREATED)
def create_blank_stock(
    payload: BlankStockCreate,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    total_weight_kg = payload.kg_per_sack * payload.total_sacks
    stock = (
        db.query(BlankStock)
        .filter(BlankStock.factory_id == factory_id)
        .filter(BlankStock.blank_size_ml == payload.size_ml)
        .first()
    )
    if stock is None:
        stock = BlankStock(
            factory_id=factory_id,
            blank_size_ml=payload.size_ml,
            linked_bottom_size_mm=payload.size_ml,
        )
        db.add(stock)

    stock.weight_per_bora_kg = payload.kg_per_sack
    stock.total_boras = payload.total_sacks
    stock.total_qty_kg = total_weight_kg
    db.commit()

    # Synchronize RawMaterialMetrics for Dashboard mapping
    metric = (
        db.query(RawMaterialMetrics)
        .filter(RawMaterialMetrics.factory_id == factory_id)
        .filter(RawMaterialMetrics.material_type == "Blank")
        .filter(RawMaterialMetrics.size_ml_or_mm == payload.size_ml)
        .first()
    )
    if metric is None:
        metric = RawMaterialMetrics(
            factory_id=factory_id,
            material_type="Blank",
            size_ml_or_mm=payload.size_ml,
            weight_per_sack_kg=payload.kg_per_sack if payload.kg_per_sack > 0 else Decimal("20.000"),
            pieces_per_sack=1000,
        )
        db.add(metric)
    else:
        if payload.kg_per_sack > 0:
            metric.weight_per_sack_kg = payload.kg_per_sack
    db.commit()

    db.refresh(stock)
    return {
        "id": stock.id,
        "material_name": payload.material_name,
        "size_ml": stock.blank_size_ml,
        "kg_per_sack": payload.kg_per_sack,
        "total_sacks": payload.total_sacks,
        "total_weight_kg": stock.total_qty_kg,
    }


@router.post("/raw-material/bottom", status_code=status.HTTP_201_CREATED)
def create_bottom_stock(
    payload: BottomStockCreate,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    calculated_rolls = (payload.rolls_per_bag or 0) * (payload.total_bags or 0)
    calculated_weight_kg = (payload.bag_weight_kg or Decimal("0.000")) * Decimal(payload.total_bags or 0)
    total_rolls = payload.total_rolls if payload.total_rolls is not None else calculated_rolls
    total_weight_kg = payload.total_weight_kg if payload.total_weight_kg is not None else calculated_weight_kg
    stock = (
        db.query(BottomStock)
        .filter(BottomStock.factory_id == factory_id)
        .filter(BottomStock.bottom_size_mm == payload.bottom_size_mm)
        .first()
    )
    if stock is None:
        stock = BottomStock(factory_id=factory_id, bottom_size_mm=payload.bottom_size_mm)
        db.add(stock)

    stock.bag_weight_kg = payload.bag_weight_kg
    stock.rolls_per_bag = payload.rolls_per_bag
    stock.total_bags = payload.total_bags
    stock.total_rolls = total_rolls
    stock.total_weight_kg = total_weight_kg
    stock.total_qty_kg = total_weight_kg

    db.commit()

    # Synchronize RawMaterialMetrics for Dashboard mapping
    metric = (
        db.query(RawMaterialMetrics)
        .filter(RawMaterialMetrics.factory_id == factory_id)
        .filter(RawMaterialMetrics.material_type == "Bottom")
        .filter(RawMaterialMetrics.size_ml_or_mm == payload.bottom_size_mm)
        .first()
    )
    if metric is None:
        metric = RawMaterialMetrics(
            factory_id=factory_id,
            material_type="Bottom",
            size_ml_or_mm=payload.bottom_size_mm,
            weight_per_sack_kg=payload.bag_weight_kg if (payload.bag_weight_kg and payload.bag_weight_kg > 0) else Decimal("10.000"),
            pieces_per_sack=1,
        )
        db.add(metric)
    else:
        if payload.bag_weight_kg and payload.bag_weight_kg > 0:
            metric.weight_per_sack_kg = payload.bag_weight_kg
    db.commit()

    db.refresh(stock)
    return {
        "id": stock.id,
        "bottom_size_mm": stock.bottom_size_mm,
        "bag_weight_kg": stock.bag_weight_kg,
        "rolls_per_bag": stock.rolls_per_bag,
        "total_bags": stock.total_bags,
        "total_rolls": stock.total_rolls,
        "total_weight_kg": stock.total_weight_kg,
    }


@router.post("/raw-material/box", status_code=status.HTTP_201_CREATED)
def create_box_stock(
    payload: BoxStockCreate,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    stock = (
        db.query(BoxStock)
        .filter(BoxStock.factory_id == factory_id)
        .filter(sql_func.lower(BoxStock.packaging_size_name) == payload.box_type.lower())
        .first()
    )
    if stock is None:
        stock = BoxStock(factory_id=factory_id, packaging_size_name=payload.box_type)
        db.add(stock)

    stock.box_type = payload.box_type
    stock.quantity = payload.quantity
    stock.total_boxes = payload.quantity
    stock.price_per_box = payload.price_per_box
    db.commit()
    db.refresh(stock)
    return {
        "id": stock.id,
        "box_type": stock.box_type or stock.packaging_size_name,
        "quantity": stock.quantity,
        "price_per_box": stock.price_per_box,
    }


@router.post("/raw-material/plastic", status_code=status.HTTP_201_CREATED)
def create_plastic_stock(
    payload: PlasticStockCreate,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    stock = (
        db.query(PlasticStock)
        .filter(PlasticStock.factory_id == factory_id)
        .filter(sql_func.lower(PlasticStock.plastic_size_name) == payload.plastic_size_name.lower())
        .filter(PlasticStock.cup_size_ml == payload.cup_size_ml)
        .first()
    )
    if stock is None:
        stock = PlasticStock(
            factory_id=factory_id,
            plastic_size_name=payload.plastic_size_name.strip(),
            cup_size_ml=payload.cup_size_ml,
        )
        db.add(stock)

    stock.total_boras = payload.total_boras
    stock.weight_per_bora_kg = payload.weight_per_bora_kg
    stock.price_per_kg = payload.price_per_kg
    db.commit()

    # Synchronize PackagingMetrics for Dashboard mapping
    metric = (
        db.query(PackagingMetrics)
        .filter(PackagingMetrics.factory_id == factory_id)
        .filter(PackagingMetrics.cup_size_ml == payload.cup_size_ml)
        .first()
    )
    if metric is None:
        metric = PackagingMetrics(
            factory_id=factory_id,
            cup_size_ml=payload.cup_size_ml,
            kg_per_box=Decimal(str(payload.weight_per_bora_kg or 0)) if payload.weight_per_bora_kg > 0 else Decimal("10.000"),
            cups_per_box=1000,
        )
        db.add(metric)
    else:
        if payload.weight_per_bora_kg > 0:
            metric.kg_per_box = payload.weight_per_bora_kg
    db.commit()

    db.refresh(stock)
    return {
        "id": stock.id,
        "plastic_size_name": stock.plastic_size_name,
        "cup_size_ml": stock.cup_size_ml,
        "total_boras": stock.total_boras,
        "weight_per_bora_kg": stock.weight_per_bora_kg,
        "total_plastic_kg": stock.total_boras * stock.weight_per_bora_kg,
        "price_per_kg": stock.price_per_kg,
    }


@router.delete("/worker/{worker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_onboarding_worker(
    worker_id: int,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    can_cleanup_null_factory = (current_user.role or "").lower() in {"admin", "owner"}
    worker = (
        db.query(Worker)
        .filter(Worker.id == worker_id)
        .first()
    )
    if worker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

    if str(worker.factory_id) != str(current_user.factory_id):
        if not (worker.factory_id is None and can_cleanup_null_factory):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

    try:
        worker.is_active = False
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"DELETE ERROR: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Worker delete karte waqt error aaya.",
        ) from e
    return None


@router.delete("/machine/{machine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_onboarding_machine(
    machine_id: int,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    machine = (
        db.query(Machine)
        .filter(Machine.factory_id == str(current_user.factory_id))
        .filter(Machine.id == machine_id)
        .first()
    )
    if machine is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")
    db.delete(machine)
    db.commit()
    return None


@router.delete("/raw-material/{raw_material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_onboarding_raw_material(
    raw_material_id: int,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    metric = (
        db.query(RawMaterialMetrics)
        .filter(RawMaterialMetrics.factory_id == str(current_user.factory_id))
        .filter(RawMaterialMetrics.id == raw_material_id)
        .first()
    )
    if metric is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Raw material metric not found")
    db.delete(metric)
    db.commit()
    return None


@router.delete("/customer/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_onboarding_customer(
    customer_id: int,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    customer = (
        db.query(Customer)
        .filter(Customer.factory_id == str(current_user.factory_id))
        .filter(Customer.id == customer_id)
        .first()
    )
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    db.delete(customer)
    db.commit()
    return None


# =============================================================================
# LEVEL 1 ONBOARDING — Factory & Owner
# =============================================================================

@router.post("/step1", response_model=Step1Response)
def onboarding_step1(
    payload: Step1Request,
    current_user: User = Depends(check_permissions(OWNER_ROLES)),
    db: Session = Depends(get_db),
):
    if current_user.factory_id and current_user.factory_id > 0:
        existing = db.query(Factory).filter(Factory.id == current_user.factory_id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already linked to a factory",
            )

    factory = Factory(
        name=payload.factory_name.strip(),
        owner_phone_number=current_user.phone_number,
    )
    db.add(factory)
    db.commit()
    db.refresh(factory)

    current_user.factory_id = factory.id
    db.commit()

    return Step1Response(
        message="Factory created successfully",
        factory_id=factory.id,
        factory_name=factory.name,
    )


@router.post("/step1/workers", response_model=WorkerResponse, status_code=status.HTTP_201_CREATED)
def onboarding_step1_create_worker(
    payload: WorkerCreate,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    worker = (
        db.query(Worker)
        .filter(Worker.factory_id == str(current_user.factory_id))
        .filter(sql_func.lower(Worker.name) == payload.name.strip().lower())
        .first()
    )
    if worker is None:
        worker = Worker(factory_id=str(current_user.factory_id), name=payload.name.strip())
        db.add(worker)
        db.flush()

    if payload.phone:
        worker.phone, _ = normalize_phone_number(payload.phone, payload.country_code)
    worker.daily_wages = payload.daily_wages
    worker.duty_hours = payload.duty_hours
    worker.daily_salary = payload.daily_wages
    worker.salary = payload.daily_wages
    worker.shift_hours = payload.duty_hours
    worker.is_active = True
    db.flush()

    if payload.opening_attendance is not None:
        existing_oa = (
            db.query(WorkerOpeningAttendance)
            .filter(WorkerOpeningAttendance.factory_id == str(current_user.factory_id))
            .filter(WorkerOpeningAttendance.worker_id == worker.id)
            .first()
        )
        if existing_oa is not None:
            existing_oa.period_start = payload.opening_attendance.period_start
            existing_oa.period_end = payload.opening_attendance.period_end
            existing_oa.present_days = payload.opening_attendance.present_days
            existing_oa.half_days = payload.opening_attendance.half_days
            existing_oa.absent_days = payload.opening_attendance.absent_days
            existing_oa.paid_leave_days = payload.opening_attendance.paid_leave_days
            existing_oa.overtime_hours = payload.opening_attendance.overtime_hours
            existing_oa.advance_paid = payload.opening_attendance.advance_paid
            existing_oa.deductions = payload.opening_attendance.deductions
            existing_oa.notes = payload.opening_attendance.notes
        else:
            opening_att = WorkerOpeningAttendance(
                factory_id=str(current_user.factory_id),
                worker_id=worker.id,
                period_start=payload.opening_attendance.period_start,
                period_end=payload.opening_attendance.period_end,
                present_days=payload.opening_attendance.present_days,
                half_days=payload.opening_attendance.half_days,
                absent_days=payload.opening_attendance.absent_days,
                paid_leave_days=payload.opening_attendance.paid_leave_days,
                overtime_hours=payload.opening_attendance.overtime_hours,
                advance_paid=payload.opening_attendance.advance_paid,
                deductions=payload.opening_attendance.deductions,
                notes=payload.opening_attendance.notes,
                created_by_user_id=current_user.id,
            )
            db.add(opening_att)

    db.commit()
    db.refresh(worker)
    return worker


# =============================================================================
# LEVEL 2 ONBOARDING — Machine Configuration
# =============================================================================

@router.post("/step2/machines", response_model=Step2Response)
def onboarding_step2_machines(
    payload: Step2Request,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)
    check_machine_limit(factory_id, db, requested_count=len(payload.machines))

    for item in payload.machines:
        seq = item.machine_sequence_number.strip().upper()
        existing = (
            db.query(Machine)
            .filter(Machine.factory_id == factory_id)
            .filter(sql_func.lower(Machine.machine_sequence_number) == seq.lower())
            .first()
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Machine sequence {seq} already exists for this factory",
            )

        machine = Machine(
            factory_id=factory_id,
            name=item.name or seq,
            machine_sequence_number=seq,
            cup_size_ml=item.cup_size_ml,
            bottom_size_mm=item.bottom_size_mm,
            speed_cups_per_minute=item.speed_cups_per_minute,
            speed_per_minute=item.speed_cups_per_minute,
            speed_bpm=item.speed_cups_per_minute,
            can_swap_moulds=item.can_swap_moulds,
        )
        db.add(machine)

    db.commit()
    return Step2Response(
        message="Machines configured successfully",
        factory_id=factory_id,
        machines_saved=len(payload.machines),
    )


# =============================================================================
# LEVEL 3 ONBOARDING — Raw Material & Packaging Metrics
# =============================================================================

@router.post("/step3/materials", response_model=Step3Response)
def onboarding_step3_materials(
    payload: Step3Request,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)

    raw_saved = 0
    for item in payload.raw_material_metrics:
        metric = (
            db.query(RawMaterialMetrics)
            .filter(RawMaterialMetrics.factory_id == factory_id)
            .filter(RawMaterialMetrics.material_type == item.material_type)
            .filter(RawMaterialMetrics.size_ml_or_mm == item.size_ml_or_mm)
            .first()
        )
        if metric is None:
            metric = RawMaterialMetrics(
                factory_id=factory_id,
                material_type=item.material_type,
                size_ml_or_mm=item.size_ml_or_mm,
            )
            db.add(metric)

        metric.weight_per_sack_kg = item.weight_per_sack_kg
        metric.pieces_per_sack = item.pieces_per_sack
        total_weight_kg = item.total_weight_kg or (item.weight_per_sack_kg * item.total_sacks)
        if item.material_type == "Blank":
            stock = (
                db.query(BlankStock)
                .filter(BlankStock.factory_id == factory_id)
                .filter(BlankStock.blank_size_ml == item.size_ml_or_mm)
                .first()
            )
            if stock is None:
                stock = BlankStock(
                    factory_id=factory_id,
                    blank_size_ml=item.size_ml_or_mm,
                    linked_bottom_size_mm=item.size_ml_or_mm,
                    total_qty_kg=Decimal("0.000"),
                )
                db.add(stock)
            stock.total_qty_kg = total_weight_kg
        if item.material_type == "Bottom":
            stock = (
                db.query(BottomStock)
                .filter(BottomStock.factory_id == factory_id)
                .filter(BottomStock.bottom_size_mm == item.size_ml_or_mm)
                .first()
            )
            if stock is None:
                stock = BottomStock(
                    factory_id=factory_id,
                    bottom_size_mm=item.size_ml_or_mm,
                    total_qty_kg=Decimal("0.000"),
                    total_weight_kg=Decimal("0.000"),
                )
                db.add(stock)
            stock.total_qty_kg = total_weight_kg
            stock.total_weight_kg = total_weight_kg
        raw_saved += 1

    pack_saved = 0
    for item in payload.packaging_metrics:
        metric = (
            db.query(PackagingMetrics)
            .filter(PackagingMetrics.factory_id == factory_id)
            .filter(PackagingMetrics.cup_size_ml == item.cup_size_ml)
            .first()
        )
        if metric is None:
            metric = PackagingMetrics(
                factory_id=factory_id,
                cup_size_ml=item.cup_size_ml,
            )
            db.add(metric)

        metric.kg_per_box = item.kg_per_box
        metric.cups_per_box = item.cups_per_box
        packaging_size_name = f"{item.cup_size_ml}ml Standard Box"
        box_stock = (
            db.query(BoxStock)
            .filter(BoxStock.factory_id == factory_id)
            .filter(sql_func.lower(BoxStock.packaging_size_name) == packaging_size_name.lower())
            .first()
        )
        if box_stock is None:
            db.add(
                BoxStock(
                    factory_id=factory_id,
                    packaging_size_name=packaging_size_name,
                    total_boxes=0,
                )
            )

        final_stock = (
            db.query(FinalProductStock)
            .filter(FinalProductStock.factory_id == factory_id)
            .filter(FinalProductStock.product_size_ml == item.cup_size_ml)
            .filter(sql_func.lower(FinalProductStock.packaging_size_name) == packaging_size_name.lower())
            .first()
        )
        if final_stock is None:
            db.add(
                FinalProductStock(
                    factory_id=factory_id,
                    product_size_ml=item.cup_size_ml,
                    packaging_size_name=packaging_size_name,
                    current_quantity=0,
                    total_boxes=0,
                    loose_packets=0,
                    packets_per_box_limit=item.cups_per_box,
                )
            )
        pack_saved += 1

    db.commit()
    return Step3Response(
        message="Material and packaging metrics saved successfully",
        factory_id=factory_id,
        raw_material_metrics_saved=raw_saved,
        packaging_metrics_saved=pack_saved,
    )


# =============================================================================
# LEGACY BULK ONBOARDING (Backward Compatible)
# =============================================================================

@router.post("/complete", response_model=OnboardingCompleteResponse)
def complete_onboarding(
    payload: OnboardingCompleteRequest,
    current_user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    factory_id = str(current_user.factory_id)

    try:
        for machine_payload in payload.machines:
            upsert_machine(db, factory_id, machine_payload)

        for material_payload in payload.raw_materials:
            material = upsert_raw_material(db, factory_id, material_payload)
            upsert_inventory_from_raw_material(db, factory_id, material)

        for profile_payload in payload.packaging_profiles:
            upsert_packaging_profile(db, factory_id, profile_payload)

        for yield_payload in payload.material_yields:
            upsert_material_yield(db, factory_id, yield_payload)

        upsert_costing_master(db, factory_id, payload.costing_master)

        for worker_payload in payload.workers:
            upsert_worker(db, factory_id, worker_payload)
            upsert_employee_from_worker(db, factory_id, worker_payload)

        for customer_payload in payload.customers:
            upsert_customer(db, factory_id, customer_payload)

        db.commit()
        return OnboardingCompleteResponse(
            message="Factory onboarding completed successfully",
            factory_id=factory_id,
            machines_saved=len(payload.machines),
            raw_materials_saved=len(payload.raw_materials),
            packaging_profiles_saved=len(payload.packaging_profiles),
            material_yields_saved=len(payload.material_yields),
            workers_saved=len(payload.workers),
            customers_saved=len(payload.customers),
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Onboarding failed and was rolled back: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Legacy Upsert Helpers
# ---------------------------------------------------------------------------

def upsert_machine(db: Session, factory_id: int, payload: MachinePayload) -> Machine:
    name = payload.name.strip()
    machine = (
        db.query(Machine)
        .filter(Machine.factory_id == factory_id)
        .filter(sql_func.lower(Machine.name) == name.lower())
        .first()
    )
    if machine is None:
        machine = Machine(factory_id=factory_id, name=name)
        db.add(machine)

    machine.speed_bpm = payload.speed_bpm
    machine.speed_per_minute = payload.speed_bpm
    machine.current_mould_size = payload.current_mould_size
    machine.default_mould_size = payload.current_mould_size
    machine.current_bottom_size = payload.current_bottom_size
    machine.bottom_size = payload.current_bottom_size
    machine.can_swap_moulds = payload.can_swap_moulds
    return machine


def upsert_raw_material(db: Session, factory_id: int, payload: RawMaterialPayload) -> RawMaterial:
    material_name = payload.name or build_raw_material_name(payload)
    material_type = payload.type
    unit = payload.unit or ("pieces" if material_type in {"Polybag", "Carton Box"} else "kg")
    size_name = f"{payload.size_ml}ml" if payload.size_ml else None

    raw_material = (
        db.query(RawMaterial)
        .filter(RawMaterial.factory_id == factory_id)
        .filter(sql_func.lower(RawMaterial.name) == material_name.lower())
        .filter(RawMaterial.material_type == material_type)
        .filter(RawMaterial.size_name == size_name)
        .first()
    )
    if raw_material is None:
        raw_material = RawMaterial(
            factory_id=factory_id,
            name=material_name,
            material_type=material_type,
            size_name=size_name,
        )
        db.add(raw_material)

    raw_material.type = material_type
    raw_material.size_ml = payload.size_ml
    raw_material.gsm = payload.gsm
    raw_material.unit = unit
    raw_material.opening_stock = payload.stock_quantity
    raw_material.current_stock = payload.stock_quantity
    raw_material.stock_quantity = payload.stock_quantity
    raw_material.price_per_unit = payload.price_per_unit
    return raw_material


def build_raw_material_name(payload: RawMaterialPayload) -> str:
    parts = [payload.type]
    if payload.size_ml:
        parts.append(f"{payload.size_ml}ml")
    if payload.gsm:
        parts.append(f"{payload.gsm}gsm")
    return " ".join(parts)


def upsert_inventory_from_raw_material(db: Session, factory_id: int, raw_material: RawMaterial) -> Inventory:
    category = "Packaging" if raw_material.material_type in {"Polybag", "Carton Box"} else "Raw"
    item = get_or_create_inventory(db, factory_id, raw_material.name, category, raw_material.unit)
    item.quantity = raw_material.stock_quantity
    item.price_per_unit = raw_material.price_per_unit
    return item


def upsert_packaging_profile(
    db: Session,
    factory_id: int,
    payload: PackagingProfilePayload,
) -> PackagingProfile:
    product_name = f"{payload.product_name_ml}ml Paper Cup"
    profile_name = f"{payload.product_name_ml}ml Standard Box"
    poly_inventory = get_or_create_inventory(db, factory_id, f"{payload.product_name_ml}ml Polybag", "Packaging", "pieces")
    box_inventory = get_or_create_inventory(db, factory_id, payload.box_size_name or f"{payload.product_name_ml}ml Carton Box", "Packaging", "pieces")

    profile = (
        db.query(PackagingProfile)
        .filter(PackagingProfile.factory_id == factory_id)
        .filter(sql_func.lower(PackagingProfile.profile_name) == profile_name.lower())
        .first()
    )
    if profile is None:
        profile = PackagingProfile(factory_id=factory_id, profile_name=profile_name)
        db.add(profile)

    cups_per_box = payload.cups_per_polybag * payload.polybags_per_box
    profile.product_name = product_name
    profile.product_name_ml = payload.product_name_ml
    profile.cup_size_ml = payload.product_name_ml
    profile.polybag_capacity = payload.cups_per_polybag
    profile.box_capacity = cups_per_box
    profile.box_size_name = payload.box_size_name
    profile.cups_per_poly = payload.cups_per_polybag
    profile.cups_per_polybag = payload.cups_per_polybag
    profile.polys_per_box = payload.polybags_per_box
    profile.polybags_per_box = payload.polybags_per_box
    profile.box_inventory_id = box_inventory.id
    profile.poly_inventory_id = poly_inventory.id
    return profile


def upsert_material_yield(db: Session, factory_id: int, payload: MaterialYieldPayload) -> MaterialYield:
    material_yield = (
        db.query(MaterialYield)
        .filter(MaterialYield.factory_id == factory_id)
        .filter(MaterialYield.material_type == payload.material_type)
        .filter(MaterialYield.size_ml == payload.size_ml)
        .filter(MaterialYield.gsm == payload.gsm)
        .first()
    )
    if material_yield is None:
        material_yield = MaterialYield(
            factory_id=factory_id,
            material_type=payload.material_type,
            size_ml=payload.size_ml,
            gsm=payload.gsm,
        )
        db.add(material_yield)

    material_yield.pieces_per_kg = payload.pieces_per_kg
    return material_yield


def upsert_costing_master(db: Session, factory_id: int, payload) -> CostingMaster:
    costing = db.query(CostingMaster).filter(CostingMaster.factory_id == factory_id).first()
    if costing is None:
        costing = CostingMaster(factory_id=factory_id)
        db.add(costing)

    costing.paper_price_per_kg = payload.paper_price_per_kg
    costing.bottom_roll_price_per_kg = payload.bottom_roll_price_per_kg
    costing.polybag_price = payload.polybag_price
    costing.carton_price = payload.carton_price
    costing.labour_cost_per_box = payload.labour_cost_per_box
    costing.electricity_cost_per_box = payload.electricity_cost_per_box
    return costing


def upsert_worker(db: Session, factory_id: int, payload: WorkerPayload) -> Worker:
    worker = (
        db.query(Worker)
        .filter(Worker.factory_id == factory_id)
        .filter(sql_func.lower(Worker.name) == payload.name.lower())
        .first()
    )
    if worker is None:
        worker = Worker(factory_id=factory_id, name=payload.name.strip())
        db.add(worker)

    worker.is_active = True
    worker.daily_salary = payload.daily_salary
    worker.salary = payload.daily_salary
    worker.shift_type = payload.shift_type
    worker.shift_timing = payload.shift_type
    return worker


def upsert_employee_from_worker(db: Session, factory_id: int, payload: WorkerPayload) -> Employee:
    employee = (
        db.query(Employee)
        .filter(Employee.factory_id == factory_id)
        .filter(sql_func.lower(Employee.name) == payload.name.lower())
        .first()
    )
    if employee is None:
        employee = Employee(factory_id=factory_id, name=payload.name.strip())
        db.add(employee)

    employee.role = "Worker"
    employee.daily_wage = payload.daily_salary
    return employee


def upsert_customer(db: Session, factory_id: int, payload: CustomerPayload) -> Customer:
    customer_name = (payload.name or payload.firm_name).strip()
    customer = (
        db.query(Customer)
        .filter(Customer.factory_id == factory_id)
        .filter(sql_func.lower(Customer.name) == customer_name.lower())
        .first()
    )
    if customer is None:
        customer = Customer(factory_id=factory_id, name=customer_name)
        db.add(customer)

    customer.firm_name = payload.firm_name.strip()
    customer.contact_number = payload.contact_number
    customer.pending_balance = payload.pending_balance
    customer.pending_dues = float(payload.pending_balance)
    customer.balance_amount = payload.pending_balance
    return customer


def get_or_create_inventory(db: Session, factory_id: int, item_name: str, category: str, unit: str) -> Inventory:
    db.flush()
    item = (
        db.query(Inventory)
        .filter(Inventory.factory_id == factory_id)
        .filter(sql_func.lower(Inventory.item_name) == item_name.lower())
        .first()
    )
    if item is None:
        item = Inventory(
            factory_id=factory_id,
            item_name=item_name.strip(),
            category=category,
            unit=unit,
            quantity=Decimal("0.000"),
            price_per_unit=Decimal("0.00"),
        )
        db.add(item)
        db.flush()
    return item

from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from dependencies import INVENTORY_ROLES, check_permissions
from db import get_db
from models import BlankStock, BottomStock, BoxStock, FinalProductStock, Inventory, User


router = APIRouter()


def decimal_or_zero(value) -> Decimal:
    return Decimal(value or 0)


def int_or_zero(value) -> int:
    return int(value or 0)


class LiveStockRow(BaseModel):
    id: int
    stock_type: str
    item_name: str
    category: Optional[str] = None
    packaging_size: Optional[str] = None
    pieces_per_packet: Optional[int] = None
    packets_per_box: Optional[int] = None
    quantity: Decimal
    unit: str
    size_mm: Optional[int] = None
    total_weight_kg: Optional[Decimal] = None
    total_rolls: Optional[int] = None


class FinalStockRow(BaseModel):
    id: int
    product_size_ml: Optional[int] = None
    variety: Optional[str] = None
    packaging_size: Optional[str] = None
    packaging_size_name: Optional[str] = None
    pieces_per_packet: Optional[int] = None
    packets_per_box: Optional[int] = None
    packets_per_box_limit: Optional[int] = None
    current_quantity: Optional[int] = None
    total_boxes: Optional[int] = None
    loose_packets: Optional[int] = None


class FinalStockCreate(BaseModel):
    product_id: Optional[int] = Field(default=None, gt=0)
    product_size_ml: Optional[int] = Field(default=None, gt=0)
    variety: str = "Standard/White"
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


@router.get("/")
def list_live_stock(
    current_user: User = Depends(check_permissions(INVENTORY_ROLES)),
    db: Session = Depends(get_db),
):
    try:
        inventory_items = (
            db.query(Inventory)
            .filter(Inventory.factory_id == current_user.factory_id)
            .order_by(Inventory.item_name.asc().nullslast(), Inventory.id.asc())
            .all()
        )

        processed_inventory = []
        for item in inventory_items:
            quantity = item.quantity if item.quantity is not None else 0
            processed_inventory.append(
                {
                    "id": item.id,
                    "factory_id": item.factory_id,
                    "product_id": getattr(item, "product_id", None),
                    "item_name": item.item_name if item.item_name is not None else "Unknown Item",
                    "stock_type": item.category if item.category is not None else "Inventory",
                    "current_quantity": getattr(item, "current_quantity", None) if getattr(item, "current_quantity", None) is not None else float(quantity),
                    "quantity": float(quantity),
                    "unit": item.unit if item.unit is not None else "pieces",
                    "price_per_unit": float(item.price_per_unit if item.price_per_unit is not None else 0),
                    "packaging_size": item.packaging_size if item.packaging_size is not None else "Standard",
                    "pieces_per_packet": item.pieces_per_packet if item.pieces_per_packet is not None else 0,
                    "packets_per_box": item.packets_per_box if item.packets_per_box is not None else 0,
                    "category": item.category if item.category is not None else "Final Product",
                }
            )

        final_stock_items = (
            db.query(FinalProductStock)
            .filter(FinalProductStock.factory_id == current_user.factory_id)
            .order_by(FinalProductStock.product_size_ml.asc(), FinalProductStock.packaging_size_name.asc())
            .all()
        )
        for item in final_stock_items:
            current_quantity = item.current_quantity if item.current_quantity is not None else item.total_boxes
            packaging_size = item.packaging_size_name or "Standard"
            processed_inventory.append(
                {
                    "id": f"final-{item.id}",
                    "factory_id": item.factory_id,
                    "product_id": item.id,
                    "product_size_ml": item.product_size_ml or 0,
                    "variety": item.variety or "Standard/White",
                    "item_name": f"{item.product_size_ml or 0}ml {item.variety or 'Standard/White'} - {packaging_size}",
                    "stock_type": "Final Product",
                    "current_quantity": int(current_quantity or 0),
                    "quantity": int(current_quantity or 0),
                    "unit": "boxes",
                    "price_per_unit": 0,
                    "packaging_size": packaging_size,
                    "packaging_size_name": packaging_size,
                    "pieces_per_packet": item.pieces_per_packet if item.pieces_per_packet is not None else 0,
                    "packets_per_box": item.packets_per_box_limit if item.packets_per_box_limit is not None else 0,
                    "packets_per_box_limit": item.packets_per_box_limit if item.packets_per_box_limit is not None else 0,
                    "category": "Final Product",
                }
            )

        return processed_inventory
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Backend processing crashed: {str(e)}") from e


@router.post("/final-stock", response_model=FinalStockRow)
def save_final_stock(
    payload: FinalStockCreate,
    current_user: User = Depends(check_permissions(INVENTORY_ROLES)),
    db: Session = Depends(get_db),
):
    try:
        packaging_size_name = (payload.packaging_size_name or payload.packaging_size or "").strip()
        packets_per_box_limit = payload.packets_per_box_limit or payload.packets_per_box
        quantity = payload.current_quantity
        if quantity is None:
            quantity = payload.total_boxes
        if quantity is None:
            quantity = payload.initial_quantity

        if not packaging_size_name:
            raise HTTPException(status_code=422, detail="packaging_size or packaging_size_name is required")
        if packets_per_box_limit is None:
            raise HTTPException(status_code=422, detail="packets_per_box or packets_per_box_limit is required")

        if payload.product_id:
            stock = (
                db.query(FinalProductStock)
                .filter(FinalProductStock.factory_id == current_user.factory_id)
                .filter(FinalProductStock.id == payload.product_id)
                .with_for_update()
                .first()
            )
            if stock is None:
                raise HTTPException(status_code=404, detail="Final product stock item not found")
            if payload.product_size_ml is not None:
                stock.product_size_ml = payload.product_size_ml
        else:
            if payload.product_size_ml is None:
                raise HTTPException(status_code=422, detail="product_size_ml is required")
            stock = (
                db.query(FinalProductStock)
                .filter(FinalProductStock.factory_id == current_user.factory_id)
                .filter(FinalProductStock.product_size_ml == payload.product_size_ml)
                .filter(FinalProductStock.variety == payload.variety)
                .filter(FinalProductStock.packaging_size_name == packaging_size_name)
                .with_for_update()
                .first()
            )
            if stock is None:
                stock = FinalProductStock(
                    factory_id=current_user.factory_id,
                    product_size_ml=payload.product_size_ml,
                    variety=payload.variety,
                    packaging_size_name=packaging_size_name,
                    pieces_per_packet=payload.pieces_per_packet,
                    packets_per_box_limit=packets_per_box_limit,
                )
                db.add(stock)

        stock.variety = payload.variety
        stock.packaging_size_name = packaging_size_name
        stock.pieces_per_packet = payload.pieces_per_packet
        stock.packets_per_box_limit = packets_per_box_limit
        stock.current_quantity = quantity
        stock.total_boxes = quantity
        stock.loose_packets = payload.loose_packets
        db.commit()
        db.refresh(stock)
        return FinalStockRow(
            id=stock.id,
            product_size_ml=stock.product_size_ml,
            variety=stock.variety or "Standard/White",
            packaging_size=stock.packaging_size_name,
            packaging_size_name=stock.packaging_size_name,
            pieces_per_packet=stock.pieces_per_packet,
            packets_per_box=stock.packets_per_box_limit,
            current_quantity=stock.current_quantity if stock.current_quantity is not None else stock.total_boxes or 0,
            total_boxes=stock.total_boxes or 0,
            loose_packets=stock.loose_packets or 0,
            packets_per_box_limit=stock.packets_per_box_limit,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/final-stock", response_model=List[FinalStockRow])
def list_final_stock(
    current_user: User = Depends(check_permissions(INVENTORY_ROLES)),
    db: Session = Depends(get_db),
):
    try:
        rows = (
            db.query(FinalProductStock)
            .filter(FinalProductStock.factory_id == current_user.factory_id)
            .order_by(FinalProductStock.product_size_ml.asc(), FinalProductStock.variety.asc())
            .all()
        )
        return [
            FinalStockRow(
                id=row.id,
                product_size_ml=row.product_size_ml,
                variety=row.variety or "Standard/White",
                packaging_size=row.packaging_size_name,
                packaging_size_name=row.packaging_size_name,
                pieces_per_packet=row.pieces_per_packet,
                packets_per_box=row.packets_per_box_limit,
                current_quantity=row.current_quantity if row.current_quantity is not None else row.total_boxes or 0,
                total_boxes=row.total_boxes or 0,
                loose_packets=row.loose_packets or 0,
                packets_per_box_limit=row.packets_per_box_limit,
            )
            for row in rows
        ]
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e)) from e

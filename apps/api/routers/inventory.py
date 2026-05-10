from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from dependencies import INVENTORY_ROLES, check_permissions
from db import get_db
from models import BlankStock, BottomStock, BoxStock, FinalProductStock, User


router = APIRouter()


class LiveStockRow(BaseModel):
    id: int
    stock_type: str
    item_name: str
    quantity: Decimal
    unit: str
    size_mm: Optional[int] = None
    total_weight_kg: Optional[Decimal] = None
    total_rolls: Optional[int] = None


class FinalStockRow(BaseModel):
    id: int
    product_size_ml: int
    variety: str
    packaging_size_name: str
    total_boxes: int
    loose_packets: int
    packets_per_box_limit: int


@router.get("/", response_model=List[LiveStockRow])
def list_live_stock(
    current_user: User = Depends(check_permissions(INVENTORY_ROLES)),
    db: Session = Depends(get_db),
):
    try:
        factory_id = current_user.factory_id
        rows: List[LiveStockRow] = []

        for stock in db.query(BlankStock).filter(BlankStock.factory_id == factory_id).order_by(BlankStock.blank_size_ml.asc()).all():
            rows.append(LiveStockRow(id=stock.id, stock_type="Blank", item_name=f"{stock.blank_size_ml}ml Blank", quantity=stock.total_qty_kg, unit="kg"))

        for stock in db.query(BottomStock).filter(BottomStock.factory_id == factory_id).order_by(BottomStock.bottom_size_mm.asc()).all():
            rows.append(
                LiveStockRow(
                    id=stock.id,
                    stock_type="Bottom",
                    item_name=f"{stock.bottom_size_mm}mm Bottom",
                    quantity=stock.total_qty_kg,
                    unit="kg",
                    size_mm=stock.bottom_size_mm,
                    total_weight_kg=stock.total_weight_kg,
                    total_rolls=stock.total_rolls,
                )
            )

        for stock in db.query(BoxStock).filter(BoxStock.factory_id == factory_id).order_by(BoxStock.packaging_size_name.asc()).all():
            rows.append(LiveStockRow(id=stock.id, stock_type="Box", item_name=stock.packaging_size_name, quantity=Decimal(stock.total_boxes or 0), unit="boxes"))

        for stock in db.query(FinalProductStock).filter(FinalProductStock.factory_id == factory_id).order_by(FinalProductStock.product_size_ml.asc()).all():
            rows.append(LiveStockRow(id=stock.id, stock_type="Final Product", item_name=f"{stock.product_size_ml}ml {stock.packaging_size_name}", quantity=Decimal(stock.total_boxes or 0), unit="boxes"))

        return rows
    except Exception as e:
        print(f"INVENTORY ERROR: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Inventory load failed", "error": str(e)},
        )


@router.get("/final-stock", response_model=List[FinalStockRow])
def list_final_stock(
    current_user: User = Depends(check_permissions(INVENTORY_ROLES)),
    db: Session = Depends(get_db),
):
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
            packaging_size_name=row.packaging_size_name,
            total_boxes=row.total_boxes or 0,
            loose_packets=row.loose_packets or 0,
            packets_per_box_limit=row.packets_per_box_limit,
        )
        for row in rows
    ]

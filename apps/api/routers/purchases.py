from decimal import Decimal
from datetime import date as date_cls, datetime, timedelta
from typing import List, Optional
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from db import get_db
from dependencies import check_permissions, get_current_user
from models import (
    Supplier,
    PurchaseEntry,
    PurchaseRateHistory,
    BlankStock,
    BottomStock,
    BoxStock,
    PlasticStock,
    PolybagStock,
    DailyProduction,
    Factory,
)
from schemas import (
    SupplierCreate,
    SupplierResponse,
    PurchaseEntryCreate,
    PurchaseEntryResponse,
)
from services.telegram_delivery import send_role_briefing

router = APIRouter(prefix="/api/purchases", tags=["purchases"])
log = logging.getLogger(__name__)


def increase_inventory_stock(db: Session, factory_id: int, item_category: str, qty: Decimal,
                             product_size_ml: Optional[int] = None, variety_design: Optional[str] = None,
                             packaging_size_name: Optional[str] = None, bottom_size_mm: Optional[int] = None):
    variety = variety_design or "Plain White"
    if item_category == "Blank":
        size = product_size_ml or 250
        stock = db.query(BlankStock).filter(
            BlankStock.factory_id == factory_id,
            BlankStock.blank_size_ml == size,
            BlankStock.variety == variety
        ).first()
        if not stock:
            stock = BlankStock(
                factory_id=factory_id,
                blank_size_ml=size,
                variety=variety,
                linked_bottom_size_mm=bottom_size_mm or 52,
                total_qty_kg=qty
            )
            db.add(stock)
        else:
            stock.total_qty_kg += qty

    elif item_category == "Bottom":
        size = bottom_size_mm or 52
        stock = db.query(BottomStock).filter(
            BottomStock.factory_id == factory_id,
            BottomStock.bottom_size_mm == size,
            BottomStock.variety == variety
        ).first()
        if not stock:
            stock = BottomStock(
                factory_id=factory_id,
                bottom_size_mm=size,
                variety=variety,
                total_qty_kg=qty,
                total_weight_kg=qty,
                total_rolls=1
            )
            db.add(stock)
        else:
            stock.total_qty_kg += qty
            stock.total_weight_kg += qty

    elif item_category == "Box":
        pkg_name = packaging_size_name or f"{product_size_ml or 250}ML Standard"
        stock = db.query(BoxStock).filter(
            BoxStock.factory_id == factory_id,
            BoxStock.packaging_size_name == pkg_name
        ).first()
        if not stock:
            stock = BoxStock(
                factory_id=factory_id,
                packaging_size_name=pkg_name,
                quantity=int(qty),
                total_boxes=int(qty)
            )
            db.add(stock)
        else:
            stock.quantity += int(qty)
            stock.total_boxes += int(qty)

    elif item_category == "Plastic":
        pkg_name = packaging_size_name or variety
        size = product_size_ml or 250
        stock = db.query(PlasticStock).filter(
            PlasticStock.factory_id == factory_id,
            PlasticStock.plastic_size_name == pkg_name,
            PlasticStock.cup_size_ml == size
        ).first()
        if not stock:
            stock = PlasticStock(
                factory_id=factory_id,
                plastic_size_name=pkg_name,
                cup_size_ml=size,
                total_boras=int(qty)
            )
            db.add(stock)
        else:
            stock.total_boras += int(qty)

    elif item_category == "Polybag":
        pkg_name = packaging_size_name or f"{product_size_ml or 250}ML Polybag"
        stock = db.query(PolybagStock).filter(
            PolybagStock.factory_id == factory_id,
            PolybagStock.packaging_size_name == pkg_name
        ).first()
        if not stock:
            stock = PolybagStock(
                factory_id=factory_id,
                packaging_size_name=pkg_name,
                total_packets=int(qty)
            )
            db.add(stock)
        else:
            stock.total_packets += int(qty)


@router.post("/suppliers", response_model=SupplierResponse, status_code=201)
def create_supplier(payload: SupplierCreate, current_user=Depends(get_current_user), db: Session=Depends(get_db)):
    # Check if duplicate name in factory
    existing = db.query(Supplier).filter(
        Supplier.factory_id == current_user.factory_id,
        Supplier.name == payload.name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Supplier with this name already exists")
    
    supplier = Supplier(
        factory_id=current_user.factory_id,
        name=payload.name,
        phone=payload.phone,
        address=payload.address,
        gst_number=payload.gst_number,
        outstanding_amount=Decimal("0.00")
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.get("/suppliers", response_model=List[SupplierResponse])
def list_suppliers(current_user=Depends(get_current_user), db: Session=Depends(get_db)):
    return db.query(Supplier).filter(Supplier.factory_id == current_user.factory_id).all()


@router.post("/entries", response_model=PurchaseEntryResponse, status_code=201)
def create_purchase_entry(payload: PurchaseEntryCreate, current_user=Depends(get_current_user), db: Session=Depends(get_db)):
    supplier = db.query(Supplier).filter(
        Supplier.factory_id == current_user.factory_id,
        Supplier.id == payload.supplier_id
    ).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    total_amount = payload.quantity * payload.rate
    purchase = PurchaseEntry(
        factory_id=current_user.factory_id,
        supplier_id=payload.supplier_id,
        item_category=payload.item_category,
        product_size_ml=payload.product_size_ml,
        variety_design=payload.variety_design,
        packaging_size_name=payload.packaging_size_name,
        bottom_size_mm=payload.bottom_size_mm,
        quantity=payload.quantity,
        rate=payload.rate,
        total_amount=total_amount,
        bill_number=payload.bill_number,
        expected_delivery_date=payload.expected_delivery_date,
        received_status=payload.received_status,
        received_date=payload.received_date
    )
    db.add(purchase)

    # Increase outstanding amount for supplier
    supplier.outstanding_amount += total_amount

    # If already received, increase stock
    if payload.received_status == "Received":
        if not purchase.received_date:
            purchase.received_date = date_cls.today()
        increase_inventory_stock(
            db,
            factory_id=current_user.factory_id,
            item_category=payload.item_category,
            qty=payload.quantity,
            product_size_ml=payload.product_size_ml,
            variety_design=payload.variety_design,
            packaging_size_name=payload.packaging_size_name,
            bottom_size_mm=payload.bottom_size_mm
        )

    # Record rate history
    identifier = ""
    if payload.item_category == "Blank":
        identifier = f"{payload.product_size_ml or 250}ml_{payload.variety_design or 'Plain White'}"
    elif payload.item_category == "Bottom":
        identifier = f"{payload.bottom_size_mm or 52}mm_{payload.variety_design or 'Plain White'}"
    elif payload.item_category == "Box":
        identifier = payload.packaging_size_name or "Standard"
    elif payload.item_category == "Plastic":
        identifier = f"{payload.product_size_ml or 250}ml_{payload.variety_design or 'Standard'}"
    elif payload.item_category == "Polybag":
        identifier = payload.packaging_size_name or "Standard"

    history_entry = PurchaseRateHistory(
        factory_id=current_user.factory_id,
        item_category=payload.item_category,
        identifier=identifier,
        rate=payload.rate,
        purchase_date=date_cls.today()
    )
    db.add(history_entry)

    db.commit()
    db.refresh(purchase)
    return purchase


@router.get("/entries", response_model=List[PurchaseEntryResponse])
def list_purchase_entries(current_user=Depends(get_current_user), db: Session=Depends(get_db)):
    return db.query(PurchaseEntry).filter(PurchaseEntry.factory_id == current_user.factory_id).all()


@router.patch("/entries/{purchase_id}/receive", response_model=PurchaseEntryResponse)
def mark_purchase_received(purchase_id: int, current_user=Depends(get_current_user), db: Session=Depends(get_db)):
    purchase = db.query(PurchaseEntry).filter(
        PurchaseEntry.factory_id == current_user.factory_id,
        PurchaseEntry.id == purchase_id
    ).first()
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase entry not found")
    
    if purchase.received_status == "Received":
        raise HTTPException(status_code=400, detail="Purchase entry already marked as received")

    purchase.received_status = "Received"
    purchase.received_date = date_cls.today()

    increase_inventory_stock(
        db,
        factory_id=current_user.factory_id,
        item_category=purchase.item_category,
        qty=purchase.quantity,
        product_size_ml=purchase.product_size_ml,
        variety_design=purchase.variety_design,
        packaging_size_name=purchase.packaging_size_name,
        bottom_size_mm=purchase.bottom_size_mm
    )

    db.commit()
    db.refresh(purchase)
    return purchase


@router.post("/suppliers/{supplier_id}/pay")
def pay_supplier(supplier_id: int, amount: Decimal = Query(..., gt=0), current_user=Depends(get_current_user), db: Session=Depends(get_db)):
    supplier = db.query(Supplier).filter(
        Supplier.factory_id == current_user.factory_id,
        Supplier.id == supplier_id
    ).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    supplier.outstanding_amount = max(Decimal("0.00"), supplier.outstanding_amount - amount)
    db.commit()
    return {"message": "Payment recorded successfully", "outstanding_amount": supplier.outstanding_amount}


@router.get("/suppliers/{supplier_id}/ledger")
def get_supplier_ledger(supplier_id: int, current_user=Depends(get_current_user), db: Session=Depends(get_db)):
    supplier = db.query(Supplier).filter(
        Supplier.factory_id == current_user.factory_id,
        Supplier.id == supplier_id
    ).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    purchases = db.query(PurchaseEntry).filter(
        PurchaseEntry.factory_id == current_user.factory_id,
        PurchaseEntry.supplier_id == supplier_id
    ).order_by(PurchaseEntry.created_at.desc()).all()

    return {
        "supplier": {
            "id": supplier.id,
            "name": supplier.name,
            "phone": supplier.phone,
            "address": supplier.address,
            "gst_number": supplier.gst_number,
            "outstanding_amount": supplier.outstanding_amount,
        },
        "purchases": purchases
    }


@router.get("/alerts")
def get_purchase_alerts(current_user=Depends(get_current_user), db: Session=Depends(get_db)):
    factory_id = current_user.factory_id
    alerts = []

    # 1. Consumption calculations for Blank & Bottom (last 30 days)
    thirty_days_ago = date_cls.today() - timedelta(days=30)
    production_records = db.query(
        func.coalesce(func.sum(DailyProduction.blank_used_kg), 0),
        func.coalesce(func.sum(DailyProduction.bottom_used_kg), 0)
    ).filter(
        DailyProduction.factory_id == factory_id,
        DailyProduction.date >= thirty_days_ago
    ).first()

    total_blank_used = Decimal(production_records[0] or 0)
    total_bottom_used = Decimal(production_records[1] or 0)

    avg_blank_daily = total_blank_used / Decimal("30.0")
    avg_bottom_daily = total_bottom_used / Decimal("30.0")

    # Set fallbacks to avoid division by zero or handle no usage
    if avg_blank_daily == 0:
        avg_blank_daily = Decimal("10.0")  # Default daily consumption fallback
    if avg_bottom_daily == 0:
        avg_bottom_daily = Decimal("10.0")

    # Fetch total stock quantities
    total_blank_stock = db.query(func.coalesce(func.sum(BlankStock.total_qty_kg), 0)).filter(
        BlankStock.factory_id == factory_id
    ).scalar() or Decimal("0.0")

    total_bottom_stock = db.query(func.coalesce(func.sum(BottomStock.total_qty_kg), 0)).filter(
        BottomStock.factory_id == factory_id
    ).scalar() or Decimal("0.0")

    blank_days_left = float(total_blank_stock / avg_blank_daily)
    bottom_days_left = float(total_bottom_stock / avg_bottom_daily)

    if blank_days_left < 7:
        alerts.append({
            "type": "blank_low_stock",
            "message": f"Blank stock is low! Estimated days left: {blank_days_left:.1f} days.",
            "days_left": blank_days_left
        })

    if bottom_days_left < 7:
        alerts.append({
            "type": "bottom_low_stock",
            "message": f"Bottom stock is low! Estimated days left: {bottom_days_left:.1f} days.",
            "days_left": bottom_days_left
        })

    # 2. Supplier delivery delayed
    today = date_cls.today()
    delayed_purchases = db.query(PurchaseEntry).filter(
        PurchaseEntry.factory_id == factory_id,
        PurchaseEntry.received_status == "Pending",
        PurchaseEntry.expected_delivery_date < today
    ).all()

    for p in delayed_purchases:
        alerts.append({
            "type": "delivery_delayed",
            "message": f"Purchase ID {p.id} ({p.item_category}) from Supplier {p.supplier.name} is delayed. Expected on {p.expected_delivery_date}.",
            "purchase_id": p.id,
            "expected_date": p.expected_delivery_date
        })

    # 3. Supplier outstanding pending > 15 days
    fifteen_days_ago = today - timedelta(days=15)
    old_pending_purchases = db.query(PurchaseEntry).filter(
        PurchaseEntry.factory_id == factory_id,
        PurchaseEntry.received_status == "Received",
        PurchaseEntry.received_date < fifteen_days_ago
    ).all()

    # If supplier outstanding > 0 and has received bills > 15 days old
    supplier_ids_with_pending_outstanding = set()
    for p in old_pending_purchases:
        if p.supplier.outstanding_amount > 0:
            if p.supplier_id not in supplier_ids_with_pending_outstanding:
                supplier_ids_with_pending_outstanding.add(p.supplier_id)
                alerts.append({
                    "type": "outstanding_pending",
                    "message": f"Supplier {p.supplier.name} has outstanding balance pending for > 15 days (Bill: {p.bill_number or p.id}).",
                    "supplier_id": p.supplier_id,
                    "outstanding_amount": p.supplier.outstanding_amount
                })

    # 4. Purchase rate increased > 5%
    # We can check recent rate entries and compare them to the prior average rate
    recent_history = db.query(PurchaseRateHistory).filter(
        PurchaseRateHistory.factory_id == factory_id
    ).order_by(PurchaseRateHistory.purchase_date.desc()).all()

    checked_identifiers = set()
    for entry in recent_history:
        key = (entry.item_category, entry.identifier)
        if key not in checked_identifiers:
            checked_identifiers.add(key)
            # Find prior rate for comparison
            prior = db.query(PurchaseRateHistory).filter(
                PurchaseRateHistory.factory_id == factory_id,
                PurchaseRateHistory.item_category == entry.item_category,
                PurchaseRateHistory.identifier == entry.identifier,
                PurchaseRateHistory.id != entry.id,
                PurchaseRateHistory.purchase_date <= entry.purchase_date
            ).order_by(PurchaseRateHistory.purchase_date.desc()).first()

            if prior and entry.rate > prior.rate * Decimal("1.05"):
                increase_percent = float((entry.rate - prior.rate) / prior.rate * 100)
                alerts.append({
                    "type": "rate_increase",
                    "message": f"Purchase rate for {entry.item_category} ({entry.identifier}) increased by {increase_percent:.1f}% (Current: {entry.rate}, Prior: {prior.rate}).",
                    "item_category": entry.item_category,
                    "identifier": entry.identifier,
                    "increase_percent": increase_percent
                })

    # Telegram Send Integration
    if alerts:
        alert_text = "⚠️ *Munshi AI Reorder & Outstanding Alerts*\n\n"
        for alert in alerts[:5]:
            alert_text += f"• {alert['message']}\n"
        
        try:
            send_role_briefing(db, factory_id, "Owner", alert_text)
        except Exception as e:
            log.warning(f"Failed to send Telegram alert for factory_id={factory_id}: {e}")

    return {"alerts": alerts}

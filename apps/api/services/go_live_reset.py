from __future__ import annotations

from datetime import date
from decimal import Decimal
import logging

from sqlalchemy.orm import Session

from models import (
    ActivityLog,
    BillPayment,
    BlankStock,
    BottomStock,
    Customer,
    CustomerLedgerAdjustment,
    DailyProduction,
    DailySale,
    Factory,
    FactorySettings,
    FinalProductStock,
    InvoiceDeliveryLog,
    InvoiceDocument,
    Order,
    OrderItem,
    OutstandingBill,
    Payment,
    PaymentCollection,
    ProductionBatch,
    ProductionBatchWorkerLine,
    RecoveryFollowup,
    RecycledInvoice,
    SalesInvoice,
    ShiftWastage,
    WastageLog,
)
from services.master_backup import create_pre_restore_backup


logger = logging.getLogger(__name__)
SALES_SCOPES = {"sales", "all"}
PRODUCTION_SCOPES = {"production", "all"}


def preview_go_live_reset(db: Session, factory_id: int, scope: str) -> dict:
    include_sales = scope in SALES_SCOPES
    include_production = scope in PRODUCTION_SCOPES
    return {
        "invoices": (
            db.query(InvoiceDocument).filter(InvoiceDocument.factory_id == factory_id).count()
            + db.query(SalesInvoice).filter(SalesInvoice.factory_id == factory_id).count()
            if include_sales else 0
        ),
        "payments": (
            db.query(Payment).filter(Payment.factory_id == factory_id).count()
            + db.query(PaymentCollection).filter(PaymentCollection.factory_id == factory_id).count()
            if include_sales else 0
        ),
        "outstanding_bills": (
            db.query(OutstandingBill).filter(OutstandingBill.factory_id == factory_id).count()
            if include_sales else 0
        ),
        "payment_allocations": (
            db.query(BillPayment).filter(BillPayment.factory_id == factory_id).count()
            if include_sales else 0
        ),
        "production_entries": (
            db.query(DailyProduction).filter(DailyProduction.factory_id == factory_id).count()
            if include_production else 0
        ),
        "wastage_entries": (
            db.query(WastageLog).filter(WastageLog.factory_id == factory_id).count()
            + db.query(ShiftWastage).filter(ShiftWastage.factory_id == factory_id).count()
            if include_production else 0
        ),
        "affected_stock_records": _affected_stock_count(db, factory_id, include_sales, include_production),
        "customers_kept": db.query(Customer).filter(Customer.factory_id == factory_id).count(),
    }


def _affected_stock_count(db: Session, factory_id: int, include_sales: bool, include_production: bool) -> int:
    keys: set[tuple] = set()
    if include_sales:
        for row in db.query(DailySale).filter(DailySale.factory_id == factory_id):
            keys.add(("finished", row.product_size_ml, row.variety, row.packaging_size_name))
    if include_production:
        for row in db.query(DailyProduction).filter(DailyProduction.factory_id == factory_id):
            keys.add(("finished", row.product_size_ml, row.variety, row.packaging_size_name))
            if row.blank_used_kg or row.blank_used_bora:
                keys.add(("blank", row.product_size_ml, row.variety))
            if row.bottom_used_rolls or row.bottom_used_kg:
                keys.add(("bottom", row.product_size_ml, row.variety))
    return len(keys)


def _restore_sales_stock(db: Session, factory_id: int) -> None:
    for sale in db.query(DailySale).filter(DailySale.factory_id == factory_id).all():
        stock = (
            db.query(FinalProductStock)
            .filter(
                FinalProductStock.factory_id == factory_id,
                FinalProductStock.product_size_ml == sale.product_size_ml,
                FinalProductStock.variety == sale.variety,
                FinalProductStock.packaging_size_name == sale.packaging_size_name,
            )
            .first()
        )
        if stock is None:
            continue
        stock.total_boxes = int(stock.total_boxes or 0) + int(sale.boxes_sold or 0)
        stock.loose_packets = int(stock.loose_packets or 0) + int(sale.loose_packets_sold or 0)
        stock.current_quantity = int(stock.total_boxes or 0)


def _restore_production_stock(db: Session, factory_id: int) -> None:
    for row in db.query(DailyProduction).filter(DailyProduction.factory_id == factory_id).all():
        if row.status == "ACTIVE":
            stock = (
                db.query(FinalProductStock)
                .filter(
                    FinalProductStock.factory_id == factory_id,
                    FinalProductStock.product_size_ml == row.product_size_ml,
                    FinalProductStock.variety == row.variety,
                    FinalProductStock.packaging_size_name == row.packaging_size_name,
                )
                .first()
            )
            if stock is not None:
                stock.total_boxes = max(0, int(stock.total_boxes or 0) - int(row.total_boxes_made or 0))
                stock.loose_packets = max(0, int(stock.loose_packets or 0) - int(row.loose_packets_made or 0))
                stock.current_quantity = int(stock.total_boxes or 0)
        blank = (
            db.query(BlankStock)
            .filter(
                BlankStock.factory_id == factory_id,
                BlankStock.blank_size_ml == row.product_size_ml,
                BlankStock.variety == row.variety,
            )
            .first()
        )
        if blank is not None:
            blank.total_qty_kg = Decimal(blank.total_qty_kg or 0) + Decimal(row.blank_used_kg or 0)
            if blank.total_boras is not None:
                blank.total_boras = Decimal(blank.total_boras or 0) + Decimal(row.blank_used_bora or 0)


def _delete_sales_transactions(db: Session, factory_id: int) -> dict[str, int]:
    counts = {}
    counts[CustomerLedgerAdjustment.__tablename__] = (
        db.query(CustomerLedgerAdjustment)
        .filter(
            CustomerLedgerAdjustment.factory_id == factory_id,
            CustomerLedgerAdjustment.linked_bill_id.isnot(None),
        )
        .delete(synchronize_session="fetch")
    )
    models = [
        RecoveryFollowup,
        BillPayment,
        PaymentCollection,
        Payment,
        InvoiceDeliveryLog,
        OutstandingBill,
        InvoiceDocument,
        SalesInvoice,
        DailySale,
        RecycledInvoice,
        OrderItem,
        Order,
    ]
    for model in models:
        counts[model.__tablename__] = (
            db.query(model).filter(model.factory_id == factory_id).delete(synchronize_session="fetch")
        )
    return counts


def _delete_production_transactions(db: Session, factory_id: int) -> dict[str, int]:
    counts = {}
    for model in [
        ProductionBatchWorkerLine,
        ProductionBatch,
        DailyProduction,
        ShiftWastage,
        WastageLog,
    ]:
        counts[model.__tablename__] = (
            db.query(model).filter(model.factory_id == factory_id).delete(synchronize_session="fetch")
        )
    return counts


def _replace_opening_outstanding(
    db: Session,
    factory_id: int,
    opening_outstanding: list[dict],
    user_id: int,
) -> None:
    for customer in db.query(Customer).filter(Customer.factory_id == factory_id).all():
        customer.previous_due = Decimal("0")
        customer.total_due = Decimal("0")
    for item in opening_outstanding:
        amount = Decimal(str(item["amount"]))
        if amount <= 0:
            continue
        customer = (
            db.query(Customer)
            .filter(Customer.factory_id == factory_id, Customer.id == int(item["customer_id"]))
            .one()
        )
        customer.previous_due = amount
        customer.total_due = amount
        db.add(OutstandingBill(
            factory_id=factory_id,
            customer_id=customer.id,
            source_type="opening_outstanding",
            tracking_number=f"OPENING-{customer.id}",
            bill_date=date.today(),
            bill_amount=amount,
            amount_paid=0,
            balance_amount=amount,
            status="active",
            note="Go-live opening outstanding",
            created_by_user_id=user_id,
        ))


def confirm_go_live_reset(
    db: Session,
    factory_id: int,
    user_id: int,
    *,
    scope: str,
    inventory_mode: str,
    reason: str,
    invoice_starts: dict,
    opening_outstanding: list[dict],
) -> dict:
    backup_path = create_pre_restore_backup(db, factory_id)
    preview = preview_go_live_reset(db, factory_id, scope)
    deleted: dict[str, int] = {}
    try:
        if inventory_mode == "restore_baseline":
            if scope in SALES_SCOPES:
                _restore_sales_stock(db, factory_id)
            if scope in PRODUCTION_SCOPES:
                _restore_production_stock(db, factory_id)
        if scope in SALES_SCOPES:
            deleted.update(_delete_sales_transactions(db, factory_id))
            _replace_opening_outstanding(db, factory_id, opening_outstanding, user_id)
            factory = db.query(Factory).filter(Factory.id == factory_id).one()
            settings = db.query(FactorySettings).filter(FactorySettings.factory_id == factory_id).first()
            if settings is None:
                settings = FactorySettings(factory_id=factory_id)
                db.add(settings)
            factory.next_tax_invoice_number = int(invoice_starts["tax_invoice"])
            factory.next_bill_of_supply_number = int(invoice_starts["bill_of_supply"])
            factory.next_bill_of_supply_simple_number = int(invoice_starts["simple_bill"])
            settings.tax_invoice_start_seq = int(invoice_starts["tax_invoice"])
            settings.bill_of_supply_start_seq = int(invoice_starts["bill_of_supply"])
            settings.bill_of_supply_simple_start_seq = int(invoice_starts["simple_bill"])
        if scope in PRODUCTION_SCOPES:
            deleted.update(_delete_production_transactions(db, factory_id))
        db.add(ActivityLog(
            factory_id=factory_id,
            event_type="GO_LIVE_RESET",
            description=f"Owner reset test transaction data. Reason: {reason}",
            user_id=user_id,
            user_role="Owner",
            action_type="GO_LIVE_RESET",
            action_summary=f"scope={scope}; inventory_mode={inventory_mode}",
            metadata_json={
                "reason": reason,
                "scope": scope,
                "inventory_mode": inventory_mode,
                "preview": preview,
                "deleted": deleted,
                "invoice_starts": invoice_starts,
                "backup_path": str(backup_path),
            },
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Go-live reset failed factory_id=%s scope=%s", factory_id, scope)
        raise
    return {"status": "completed", "backup_path": str(backup_path), "deleted": deleted, "preview": preview}

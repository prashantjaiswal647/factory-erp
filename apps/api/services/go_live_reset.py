from __future__ import annotations

from datetime import date
from decimal import Decimal
import logging

from sqlalchemy import delete, inspect
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
    DailyFactoryHealthSnapshot,
    DailyProfitSnapshot,
    DailyWastageSnapshot,
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
    BriefingSnapshot,
    RecoveryFollowup,
    RecycledInvoice,
    SalesInvoice,
    ShiftWastage,
    WastageLog,
)
from services.master_backup import create_pre_restore_backup


logger = logging.getLogger(__name__)
SALES_SCOPES = {"sales", "sales_only", "all", "all_transaction_data"}
PRODUCTION_SCOPES = {"production", "production_only", "all", "all_transaction_data"}


def _table_exists(db: Session, model) -> bool:
    tables = db.info.get("go_live_reset_tables")
    if tables is None:
        tables = set(inspect(db.get_bind()).get_table_names())
        db.info["go_live_reset_tables"] = tables
    exists = model.__tablename__ in tables
    if not exists:
        logger.warning(
            "Go-live reset skipped missing optional table table=%s",
            model.__tablename__,
        )
    return exists


def _count(db: Session, model, factory_id: int, *filters) -> int:
    if not _table_exists(db, model):
        return 0
    return db.query(model).filter(model.factory_id == factory_id, *filters).count()


def _delete(db: Session, model, factory_id: int, *filters) -> int:
    if not _table_exists(db, model):
        return 0
    statement = delete(model).where(model.factory_id == factory_id, *filters)
    result = db.execute(statement)
    return int(result.rowcount or 0)


def preview_go_live_reset(db: Session, factory_id: int, scope: str) -> dict:
    include_sales = scope in SALES_SCOPES
    include_production = scope in PRODUCTION_SCOPES
    warnings = []
    if scope not in SALES_SCOPES | PRODUCTION_SCOPES:
        warnings.append(f"Unknown reset scope '{scope}'; no transaction data will be selected.")
    return {
        "invoices": (
            _count(db, InvoiceDocument, factory_id)
            + _count(db, SalesInvoice, factory_id)
            if include_sales else 0
        ),
        "invoice_items": _count(db, OrderItem, factory_id) if include_sales else 0,
        "payments": (
            _count(db, Payment, factory_id)
            + _count(db, PaymentCollection, factory_id)
            if include_sales else 0
        ),
        "outstanding_bills": (
            _count(db, OutstandingBill, factory_id)
            if include_sales else 0
        ),
        "payment_allocations": (
            _count(db, BillPayment, factory_id)
            if include_sales else 0
        ),
        "customer_ledger_entries": (
            _count(
                db,
                CustomerLedgerAdjustment,
                factory_id,
                CustomerLedgerAdjustment.linked_bill_id.isnot(None),
            )
            if include_sales else 0
        ),
        "production_entries": (
            _count(db, DailyProduction, factory_id)
            + _count(db, ProductionBatch, factory_id)
            + _count(db, ProductionBatchWorkerLine, factory_id)
            if include_production else 0
        ),
        "wastage_entries": (
            _count(db, WastageLog, factory_id)
            + _count(db, ShiftWastage, factory_id)
            if include_production else 0
        ),
        "affected_stock_records": _affected_stock_count(db, factory_id, include_sales, include_production),
        "customers_kept": _count(db, Customer, factory_id),
        "warnings": warnings,
    }


def _affected_stock_count(db: Session, factory_id: int, include_sales: bool, include_production: bool) -> int:
    keys: set[tuple] = set()
    if include_sales and _table_exists(db, DailySale):
        for row in db.query(DailySale).filter(DailySale.factory_id == factory_id):
            keys.add(("finished", row.product_size_ml, row.variety, row.packaging_size_name))
    if include_production and _table_exists(db, DailyProduction):
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
    counts[CustomerLedgerAdjustment.__tablename__] = _delete(
        db,
        CustomerLedgerAdjustment,
        factory_id,
        CustomerLedgerAdjustment.linked_bill_id.isnot(None),
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
        counts[model.__tablename__] = _delete(db, model, factory_id)
    db.expunge_all()
    return counts


def _delete_production_transactions(db: Session, factory_id: int) -> dict[str, int]:
    counts = {}
    for model in [
        ProductionBatchWorkerLine,
        ProductionBatch,
        DailyProduction,
        ShiftWastage,
        WastageLog,
        DailyWastageSnapshot,
        DailyFactoryHealthSnapshot,
        DailyProfitSnapshot,
        BriefingSnapshot,
    ]:
        counts[model.__tablename__] = _delete(db, model, factory_id)
    return counts


def _replace_opening_outstanding(
    db: Session,
    factory_id: int,
    opening_outstanding: list[dict],
    user_id: int,
) -> None:
    db.query(Customer).filter(Customer.factory_id == factory_id).update(
        {Customer.previous_due: Decimal("0"), Customer.total_due: Decimal("0")},
        synchronize_session=False,
    )
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
        if inventory_mode in {"restore_baseline", "reset_transaction_impacts"}:
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

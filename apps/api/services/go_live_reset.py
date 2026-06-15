from __future__ import annotations

from datetime import date
from decimal import Decimal
import logging

from sqlalchemy import Integer, String, delete, inspect
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


def _load_schema_snapshot(db: Session) -> None:
    if "go_live_reset_tables" in db.info and "go_live_reset_factory_id_types" in db.info:
        return
    inspector = inspect(db.get_bind())
    tables = set(inspector.get_table_names())
    factory_id_types = {}
    for table in tables:
        for column in inspector.get_columns(table):
            if column["name"] == "factory_id":
                factory_id_types[table] = column["type"]
                break
    db.info["go_live_reset_tables"] = tables
    db.info["go_live_reset_factory_id_types"] = factory_id_types


def _table_exists(db: Session, model) -> bool:
    _load_schema_snapshot(db)
    tables = db.info.get("go_live_reset_tables")
    exists = model.__tablename__ in tables
    if not exists:
        logger.warning(
            "Go-live reset skipped missing optional table table=%s",
            model.__tablename__,
        )
    return exists


def normalize_factory_filter(db: Session, model, factory_id):
    _load_schema_snapshot(db)
    column = model.__table__.c.get("factory_id")
    if column is None:
        raise ValueError(f"{model.__tablename__} has no factory_id column")
    type_cache = db.info["go_live_reset_factory_id_types"]
    column_type = type_cache.get(model.__tablename__, column.type)
    if isinstance(column_type, String):
        value = str(factory_id)
    elif isinstance(column_type, Integer):
        value = int(factory_id)
    else:
        value = factory_id
    return column == value


def _add_warning(warnings: list[str] | None, message: str) -> None:
    logger.warning(message)
    if warnings is not None and message not in warnings:
        warnings.append(message)


def _count(db: Session, model, factory_id, *filters, warnings: list[str] | None = None) -> int:
    if not _table_exists(db, model):
        _add_warning(warnings, f"Skipped missing table {model.__tablename__}.")
        return 0
    try:
        with db.begin_nested():
            return db.query(model).filter(normalize_factory_filter(db, model, factory_id), *filters).count()
    except Exception as exc:
        _add_warning(
            warnings,
            f"Could not count {model.__tablename__}; using 0 ({exc.__class__.__name__}).",
        )
        return 0


def _delete(db: Session, model, factory_id: int, *filters) -> int:
    if not _table_exists(db, model):
        return 0
    statement = delete(model).where(normalize_factory_filter(db, model, factory_id), *filters)
    result = db.execute(statement)
    return int(result.rowcount or 0)


def preview_go_live_reset(db: Session, factory_id: int, scope: str) -> dict:
    include_sales = scope in SALES_SCOPES
    include_production = scope in PRODUCTION_SCOPES
    warnings = []
    if scope not in SALES_SCOPES | PRODUCTION_SCOPES:
        warnings.append(f"Unknown reset scope '{scope}'; no transaction data will be selected.")
    result = {
        "invoices": (
            _count(db, InvoiceDocument, factory_id, warnings=warnings)
            + _count(db, SalesInvoice, factory_id, warnings=warnings)
            if include_sales else 0
        ),
        "invoice_items": _count(db, OrderItem, factory_id, warnings=warnings) if include_sales else 0,
        "payments": (
            _count(db, Payment, factory_id, warnings=warnings)
            + _count(db, PaymentCollection, factory_id, warnings=warnings)
            if include_sales else 0
        ),
        "outstanding_bills": (
            _count(db, OutstandingBill, factory_id, warnings=warnings)
            if include_sales else 0
        ),
        "payment_allocations": (
            _count(db, BillPayment, factory_id, warnings=warnings)
            if include_sales else 0
        ),
        "customer_ledger_entries": (
            _count(
                db,
                CustomerLedgerAdjustment,
                factory_id,
                CustomerLedgerAdjustment.linked_bill_id.isnot(None),
                warnings=warnings,
            )
            if include_sales else 0
        ),
        "production_entries": (
            _count(db, DailyProduction, factory_id, warnings=warnings)
            + _count(db, ProductionBatch, factory_id, warnings=warnings)
            + _count(db, ProductionBatchWorkerLine, factory_id, warnings=warnings)
            if include_production else 0
        ),
        "wastage_entries": (
            _count(db, WastageLog, factory_id, warnings=warnings)
            + _count(db, ShiftWastage, factory_id, warnings=warnings)
            if include_production else 0
        ),
        "affected_stock_records": _affected_stock_count(
            db, factory_id, include_sales, include_production, warnings
        ),
        "customers_kept": _count(db, Customer, factory_id, warnings=warnings),
    }
    result["warnings"] = warnings
    result["counts"] = {key: value for key, value in result.items() if isinstance(value, int)}
    return result


def _affected_stock_count(
    db: Session,
    factory_id: int,
    include_sales: bool,
    include_production: bool,
    warnings: list[str] | None = None,
) -> int:
    keys: set[tuple] = set()
    try:
        with db.begin_nested():
            if include_sales and _table_exists(db, DailySale):
                for row in db.query(DailySale).filter(normalize_factory_filter(db, DailySale, factory_id)):
                    keys.add(("finished", row.product_size_ml, row.variety, row.packaging_size_name))
            if include_production and _table_exists(db, DailyProduction):
                for row in db.query(DailyProduction).filter(
                    normalize_factory_filter(db, DailyProduction, factory_id)
                ):
                    keys.add(("finished", row.product_size_ml, row.variety, row.packaging_size_name))
                    if row.blank_used_kg or row.blank_used_bora:
                        keys.add(("blank", row.product_size_ml, row.variety))
                    if row.bottom_used_rolls or row.bottom_used_kg:
                        keys.add(("bottom", row.product_size_ml, row.variety))
    except Exception as exc:
        _add_warning(
            warnings,
            f"Could not inspect affected stock records; using 0 ({exc.__class__.__name__}).",
        )
        return 0
    return len(keys)


def _restore_sales_stock(db: Session, factory_id: int) -> None:
    for sale in db.query(DailySale).filter(normalize_factory_filter(db, DailySale, factory_id)).all():
        stock = (
            db.query(FinalProductStock)
            .filter(
                normalize_factory_filter(db, FinalProductStock, factory_id),
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
    for row in db.query(DailyProduction).filter(
        normalize_factory_filter(db, DailyProduction, factory_id)
    ).all():
        if row.status == "ACTIVE":
            stock = (
                db.query(FinalProductStock)
                .filter(
                    normalize_factory_filter(db, FinalProductStock, factory_id),
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
                normalize_factory_filter(db, BlankStock, factory_id),
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
    db.query(Customer).filter(normalize_factory_filter(db, Customer, factory_id)).update(
        {Customer.previous_due: Decimal("0"), Customer.total_due: Decimal("0")},
        synchronize_session=False,
    )
    for item in opening_outstanding:
        amount = Decimal(str(item["amount"]))
        if amount <= 0:
            continue
        customer = (
            db.query(Customer)
            .filter(
                normalize_factory_filter(db, Customer, factory_id),
                Customer.id == int(item["customer_id"]),
            )
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
            settings = db.query(FactorySettings).filter(
                normalize_factory_filter(db, FactorySettings, factory_id)
            ).first()
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

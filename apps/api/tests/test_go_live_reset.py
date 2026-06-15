from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import (
    ActivityLog,
    BillPayment,
    Customer,
    DailyProduction,
    Factory,
    FactorySettings,
    FinalProductStock,
    InvoiceDocument,
    Machine,
    OutstandingBill,
    PaymentCollection,
    Worker,
)
from services.go_live_reset import confirm_go_live_reset, preview_go_live_reset
from routers.go_live_reset import ConfirmRequest, confirm_reset


@pytest.fixture()
def reset_db(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    factory = Factory(
        id=1,
        name="Go Live Factory",
        factory_name="Go Live Factory",
        subscription_status="active",
        next_tax_invoice_number=8,
        next_bill_of_supply_number=9,
        next_bill_of_supply_simple_number=10,
    )
    customer = Customer(id=1, factory_id=1, name="Customer", phone_number="9999999999", total_due=100)
    worker = Worker(id=1, factory_id=1, name="Worker", is_active=True)
    machine = Machine(id=1, factory_id=1, name="M1", machine_number="M1")
    stock = FinalProductStock(
        id=1,
        factory_id=1,
        product_size_ml=210,
        variety="Plain",
        packaging_size_name="210 Plain",
        current_quantity=10,
        total_boxes=10,
        loose_packets=0,
        packets_per_box_limit=50,
    )
    settings = FactorySettings(
        factory_id=1,
        tax_invoice_start_seq=8,
        bill_of_supply_start_seq=9,
        bill_of_supply_simple_start_seq=10,
    )
    invoice = InvoiceDocument(
        id=1,
        factory_id=1,
        customer_id=1,
        invoice_number="INV-7",
        invoice_date=date(2026, 6, 1),
        customer_name="Customer",
        payment_method="Cash",
        bill_total=100,
        amount_paid=20,
        customer_total_due=80,
        payload_json={},
    )
    outstanding = OutstandingBill(
        id=1,
        factory_id=1,
        customer_id=1,
        invoice_document_id=1,
        source_type="invoice",
        tracking_number="INV-7",
        bill_date=date(2026, 6, 1),
        bill_amount=100,
        amount_paid=20,
        balance_amount=80,
        status="active",
    )
    collection = PaymentCollection(
        id=1,
        factory_id=1,
        customer_id=1,
        outstanding_bill_id=1,
        amount_collected=20,
        payment_mode="Cash",
        collection_date=date(2026, 6, 2),
    )
    allocation = BillPayment(
        id=1,
        factory_id=1,
        bill_id=1,
        amount_allocated=20,
        payment_date=date(2026, 6, 2),
    )
    production = DailyProduction(
        id=1,
        factory_id=1,
        date=date(2026, 6, 1),
        worker_id=1,
        machine_id=1,
        product_size_ml=210,
        variety="Plain",
        packaging_size_name="210 Plain",
        packets_per_box_limit=50,
        total_boxes_made=2,
        loose_packets_made=0,
        status="ACTIVE",
    )
    db.add_all([
        factory, customer, worker, machine, stock, settings, invoice,
        outstanding, collection, allocation, production,
    ])
    db.commit()
    backup_path = tmp_path / "pre-reset.dump"
    monkeypatch.setattr("services.go_live_reset.create_pre_restore_backup", lambda *_: backup_path)
    try:
        yield db, backup_path
    finally:
        db.close()
        engine.dispose()


def _confirm(db, scope="sales", inventory_mode="keep_current"):
    return confirm_go_live_reset(
        db,
        1,
        99,
        scope=scope,
        inventory_mode=inventory_mode,
        reason="Remove verified test data before launch",
        invoice_starts={"tax_invoice": 1, "bill_of_supply": 2, "simple_bill": 3},
        opening_outstanding=[],
    )


def test_sales_reset_removes_transactions_keeps_masters_and_resets_sequences(reset_db):
    db, backup_path = reset_db
    preview = preview_go_live_reset(db, 1, "sales")
    assert preview["invoices"] == 1
    assert preview["payments"] == 1
    assert preview["outstanding_bills"] == 1

    result = _confirm(db)

    assert result["backup_path"] == str(backup_path)
    assert db.query(InvoiceDocument).count() == 0
    assert db.query(PaymentCollection).count() == 0
    assert db.query(BillPayment).count() == 0
    assert db.query(OutstandingBill).count() == 0
    assert db.query(Customer).count() == 1
    assert db.query(Worker).count() == 1
    assert db.query(Machine).count() == 1
    assert db.query(FinalProductStock).count() == 1
    factory = db.query(Factory).one()
    settings = db.query(FactorySettings).one()
    assert (factory.next_tax_invoice_number, factory.next_bill_of_supply_number, factory.next_bill_of_supply_simple_number) == (1, 2, 3)
    assert (settings.tax_invoice_start_seq, settings.bill_of_supply_start_seq, settings.bill_of_supply_simple_start_seq) == (1, 2, 3)
    assert db.query(ActivityLog).filter(ActivityLog.event_type == "GO_LIVE_RESET").count() == 1


def test_production_reset_is_optional(reset_db):
    db, _ = reset_db
    _confirm(db, scope="sales")
    assert db.query(DailyProduction).count() == 1

    _confirm(db, scope="production")
    assert db.query(DailyProduction).count() == 0


def test_reset_can_recreate_actual_opening_outstanding(reset_db):
    db, _ = reset_db
    confirm_go_live_reset(
        db,
        1,
        99,
        scope="sales",
        inventory_mode="keep_current",
        reason="Set real opening customer balance",
        invoice_starts={"tax_invoice": 1, "bill_of_supply": 1, "simple_bill": 1},
        opening_outstanding=[{"customer_id": 1, "amount": Decimal("450.50")}],
    )
    bill = db.query(OutstandingBill).one()
    customer = db.query(Customer).one()
    assert bill.source_type == "opening_outstanding"
    assert bill.balance_amount == Decimal("450.50")
    assert customer.total_due == Decimal("450.50")


def test_backup_failure_prevents_any_reset(reset_db, monkeypatch):
    db, _ = reset_db

    def fail_backup(*_):
        raise RuntimeError("backup failed")

    monkeypatch.setattr("services.go_live_reset.create_pre_restore_backup", fail_backup)
    with pytest.raises(RuntimeError, match="backup failed"):
        _confirm(db)

    assert db.query(InvoiceDocument).count() == 1
    assert db.query(Customer).count() == 1
    assert db.query(DailyProduction).count() == 1


def test_preview_works_with_empty_db(reset_db):
    db, _ = reset_db
    _confirm(db, scope="all_transaction_data")

    preview = preview_go_live_reset(db, 1, "all_transaction_data")

    assert preview["invoices"] == 0
    assert preview["invoice_items"] == 0
    assert preview["payments"] == 0
    assert preview["payment_allocations"] == 0
    assert preview["outstanding_bills"] == 0
    assert preview["customer_ledger_entries"] == 0
    assert preview["production_entries"] == 0
    assert preview["wastage_entries"] == 0
    assert preview["affected_stock_records"] == 0


def test_preview_works_when_optional_tables_are_missing(reset_db, caplog):
    db, _ = reset_db
    db.info["go_live_reset_tables"] = {"customers"}

    preview = preview_go_live_reset(db, 1, "all_transaction_data")

    assert preview["invoices"] == 0
    assert preview["production_entries"] == 0
    assert preview["customers_kept"] == 1
    assert "missing optional table" in caplog.text


def test_production_only_keeps_sales_and_master_data(reset_db):
    db, _ = reset_db

    _confirm(db, scope="production_only")

    assert db.query(DailyProduction).count() == 0
    assert db.query(InvoiceDocument).count() == 1
    assert db.query(Customer).count() == 1
    assert db.query(Worker).count() == 1
    assert db.query(Machine).count() == 1
    assert db.query(FinalProductStock).count() == 1


def test_all_transaction_data_removes_sales_and_production(reset_db):
    db, _ = reset_db

    _confirm(db, scope="all_transaction_data")

    assert db.query(InvoiceDocument).count() == 0
    assert db.query(OutstandingBill).count() == 0
    assert db.query(PaymentCollection).count() == 0
    assert db.query(DailyProduction).count() == 0
    assert db.query(Customer).count() == 1
    assert db.query(Worker).count() == 1
    assert db.query(Machine).count() == 1
    assert db.query(FinalProductStock).count() == 1


def test_transaction_rolls_back_when_production_delete_fails(reset_db, monkeypatch):
    db, _ = reset_db

    def fail_production(*_):
        raise RuntimeError("production delete failed")

    monkeypatch.setattr("services.go_live_reset._delete_production_transactions", fail_production)
    with pytest.raises(RuntimeError, match="production delete failed"):
        _confirm(db, scope="all_transaction_data")

    assert db.query(InvoiceDocument).count() == 1
    assert db.query(OutstandingBill).count() == 1
    assert db.query(PaymentCollection).count() == 1
    assert db.query(DailyProduction).count() == 1
    assert db.query(Customer).count() == 1


def test_confirm_requires_exact_confirmation_text(reset_db):
    db, _ = reset_db
    payload = ConfirmRequest(
        scope="sales_only",
        confirmation="RESET LIVE",
        reason="Remove test transactions",
        inventory_mode="keep_current_inventory_as_is",
    )
    owner = type("Owner", (), {"factory_id": 1, "id": 99})()

    with pytest.raises(HTTPException) as caught:
        confirm_reset(payload, owner, db)

    assert caught.value.status_code == 422
    assert db.query(InvoiceDocument).count() == 1

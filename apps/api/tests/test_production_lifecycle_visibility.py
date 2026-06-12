from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import ActivityLog, DailyProduction, Factory, FinalProductStock, Machine, User, Worker
from routers.inventory import recalculate_and_sync_sku_stock
from routers.operations import (
    ProductionRejectRequest,
    ProductionUpdateRequest,
    list_daily_production,
    production_worker_summary,
    reject_daily_production,
    update_daily_production,
)


@pytest.fixture()
def production_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    factory = Factory(id=1, name="Lifecycle Factory", subscription_status="active")
    user = User(id=1, factory_id=1, username="owner@test.com", full_name="Factory Owner", role="Owner", password_hash="x")
    worker = Worker(id=1, factory_id=1, name="Raju", daily_wages=500, duty_hours=8)
    machine = Machine(id=1, factory_id=1, name="Machine-2", machine_type="Cup", machine_number="M-2", speed_per_minute=100)
    stock = FinalProductStock(
        id=1,
        factory_id=1,
        product_size_ml=210,
        variety="Cup",
        packaging_size_name="210ml Box",
        pieces_per_packet=100,
        packets_per_box_limit=10,
        total_boxes=5,
        loose_packets=0,
        current_quantity=5,
    )
    production = DailyProduction(
        id=1,
        factory_id=1,
        date=date(2026, 6, 12),
        worker_id=1,
        machine_id=1,
        product_size_ml=210,
        variety="Cup",
        packaging_size_name="210ml Box",
        packets_per_box_limit=10,
        total_boxes_made=12,
        loose_packets_made=0,
        boxes_from_loose=0,
        shift="Day",
        status="ACTIVE",
        created_by_user_id=1,
    )
    session.add_all([factory, user, worker, machine, stock, production])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_production_history_summary_and_reject_inventory(production_db):
    db = production_db
    user = SimpleNamespace(id=1, factory_id=1, role="Owner", username="owner@test.com", full_name="Factory Owner")
    production = db.query(DailyProduction).one()

    history = list_daily_production(
        production_date=production.date,
        include_rejected=True,
        current_user=user,
        db=db,
    )
    assert history[0]["worker_name"] == "Raju"
    assert history[0]["machine_name"] == "Machine-2"
    assert history[0]["status"] == "ACTIVE"

    summary = production_worker_summary(production_date=production.date, current_user=user, db=db)
    assert summary["total_quantity"] == 12
    assert summary["workers"][0]["products"][0]["product_size_ml"] == 210

    updated = update_daily_production(
        production.id,
        ProductionUpdateRequest(total_boxes_made=15),
        current_user=user,
        db=db,
    )
    assert updated["quantity_boxes"] == 15

    before_boxes, _ = recalculate_and_sync_sku_stock(db, "1", 210, "Cup", "210ml Box")
    rejected = reject_daily_production(
        production.id,
        ProductionRejectRequest(reason="Incorrect worker production entry"),
        current_user=user,
        db=db,
    )
    after_boxes, _ = recalculate_and_sync_sku_stock(db, "1", 210, "Cup", "210ml Box")

    assert before_boxes == 20
    assert after_boxes == 5
    assert rejected["status"] == "REJECTED"
    assert production_worker_summary(production_date=production.date, current_user=user, db=db)["total_quantity"] == 0
    assert db.query(ActivityLog).filter(ActivityLog.action_type == "REJECT").count() == 1


def test_reject_reason_is_required():
    with pytest.raises(ValidationError):
        ProductionRejectRequest(reason="")

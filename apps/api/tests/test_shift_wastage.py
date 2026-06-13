from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import (
    Factory, User, Worker, Machine, BlankStock, BottomStock, BoxStock,
    FinalProductStock, DailyProduction, AttendanceLog, ShiftWastage
)
from routers.operations import (
    create_daily_production, save_shift_wastage, get_shift_wastage, ShiftWastageCreate
)
from schemas import DailyProductionCreate

@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    
    # Factory 1
    f1 = Factory(id=1, name="Factory 1", subscription_status="active")
    u1 = User(id=1, factory_id=1, username="owner1", role="Owner", password_hash="x")
    w1 = Worker(id=1, factory_id=1, name="Worker 1", daily_wages=500, duty_hours=8)
    m1 = Machine(id=1, factory_id=1, name="Machine 1", machine_type="Cup", machine_number="M-1", mould_size_ml=210, bottom_size_mm=57)
    
    # Stock setup for Factory 1
    blank1 = BlankStock(id=1, factory_id=1, blank_size_ml=210, variety="Plain White", weight_per_bora_kg=Decimal("40"), total_boras=Decimal("10"), total_qty_kg=Decimal("400"), linked_bottom_size_mm=57)
    bottom1 = BottomStock(id=1, factory_id=1, bottom_size_mm=57, variety="Plain White", bag_weight_kg=Decimal("30"), rolls_per_bag=3, total_rolls=10, total_qty_kg=Decimal("100"), total_weight_kg=Decimal("100"))
    box1 = BoxStock(id=1, factory_id=1, box_type="Carton A", total_boxes=100, quantity=100, size_for_finished_product="210", packaging_size_name="210ml-Standard")
    fps1 = FinalProductStock(
        id=1,
        factory_id=1,
        product_size_ml=210,
        variety="Plain White",
        packaging_size_name="210ml-Standard",
        pieces_per_packet=100,
        packets_per_box_limit=10,
        carton_type="Carton A",
        total_boxes=0,
        loose_packets=0,
        current_quantity=0,
    )
    
    # Factory 2 (for isolation testing)
    f2 = Factory(id=2, name="Factory 2", subscription_status="active")
    u2 = User(id=2, factory_id=2, username="owner2", role="Owner", password_hash="x")
    w2 = Worker(id=2, factory_id=2, name="Worker 2", daily_wages=500, duty_hours=8)
    m2 = Machine(id=2, factory_id=2, name="Machine 2", machine_type="Cup", machine_number="M-2", mould_size_ml=210, bottom_size_mm=57)
    blank2 = BlankStock(id=2, factory_id=2, blank_size_ml=210, variety="Plain White", weight_per_bora_kg=Decimal("40"), total_boras=Decimal("10"), total_qty_kg=Decimal("400"), linked_bottom_size_mm=57)
    bottom2 = BottomStock(id=2, factory_id=2, bottom_size_mm=57, variety="Plain White", bag_weight_kg=Decimal("30"), rolls_per_bag=3, total_rolls=10, total_qty_kg=Decimal("100"), total_weight_kg=Decimal("100"))
    box2 = BoxStock(id=2, factory_id=2, box_type="Carton A", total_boxes=100, quantity=100, size_for_finished_product="210", packaging_size_name="210ml-Standard")
    fps2 = FinalProductStock(
        id=2,
        factory_id=2,
        product_size_ml=210,
        variety="Plain White",
        packaging_size_name="210ml-Standard",
        pieces_per_packet=100,
        packets_per_box_limit=10,
        carton_type="Carton A",
        total_boxes=0,
        loose_packets=0,
        current_quantity=0,
    )

    session.add_all([f1, u1, w1, m1, blank1, bottom1, box1, fps1, f2, u2, w2, m2, blank2, bottom2, box2, fps2])
    session.commit()
    
    try:
        yield session
    finally:
        session.close()
        engine.dispose()

def test_production_save_and_wastage_behavior(db_session):
    db = db_session
    u1 = db.query(User).filter_by(id=1).one()
    
    # Save production without wastage
    payload = DailyProductionCreate(
        date=date(2026, 6, 13),
        worker_id=1,
        machine_id=1,
        product_id=1,
        product_size_ml=210,
        variety="Plain White",
        packaging_size_name="210ml-Standard",
        pieces_per_packet=100,
        packets_per_box_limit=10,
        shift="Day",
        total_boxes_made=2,
        loose_packets_made=0,
        blank_used_bori=Decimal("1"),  # should deduct 1 bori = 40 kg
        bottom_used_rolls=1,           # should deduct 1 roll = 10 kg
        wastage_kg=Decimal("0"),
    )
    
    class FakeBackgroundTasks:
        def add_task(self, func, *args, **kwargs):
            pass
            
    create_daily_production(
        payload=payload,
        background_tasks=FakeBackgroundTasks(),
        current_user=u1,
        db=db
    )
    
    # 1. Finished goods stock increases
    fg = db.query(FinalProductStock).filter_by(factory_id=1, product_size_ml=210).first()
    assert fg is not None
    assert fg.current_quantity == 2
    
    # 2. Worker attendance becomes present
    att = db.query(AttendanceLog).filter_by(factory_id=1, worker_id=1, date=date(2026, 6, 13)).first()
    assert att is not None
    assert att.status == "Present"
    
    # 3. Blank and bottom stock decrease
    blank = db.query(BlankStock).filter_by(id=1).one()
    assert blank.total_boras == Decimal("9")
    assert blank.total_qty_kg == Decimal("360")
    
    bottom = db.query(BottomStock).filter_by(id=1).one()
    assert bottom.total_rolls == 9
    assert bottom.total_qty_kg == Decimal("90")

    # 4. Saving wastage separately works
    wastage_payload = ShiftWastageCreate(
        date=date(2026, 6, 13),
        shift="Day",
        wastage_kg=Decimal("12.500"),
        note="Setup waste"
    )
    
    saved_w = save_shift_wastage(payload=wastage_payload, current_user=u1, db=db)
    assert saved_w.wastage_kg == Decimal("12.500")
    assert saved_w.note == "Setup waste"
    
    # Check GET
    retrieved_w = get_shift_wastage(date=date(2026, 6, 13), shift="Day", current_user=u1, db=db)
    assert retrieved_w is not None
    assert retrieved_w.wastage_kg == 12.5
    
    # 5. Re-saving wastage same date + shift updates old record
    update_payload = ShiftWastageCreate(
        date=date(2026, 6, 13),
        shift="Day",
        wastage_kg=Decimal("15.000"),
        note="Updated setup waste"
    )
    saved_w_updated = save_shift_wastage(payload=update_payload, current_user=u1, db=db)
    assert saved_w_updated.id == saved_w.id
    assert saved_w_updated.wastage_kg == Decimal("15.000")
    assert saved_w_updated.note == "Updated setup waste"
    
    # 6. Factory isolation for production and wastage
    u2 = db.query(User).filter_by(id=2).one()
    
    # Factory 2 should not see Factory 1's wastage
    w_f2 = get_shift_wastage(date=date(2026, 6, 13), shift="Day", current_user=u2, db=db)
    assert w_f2 is None
    
    # Saving wastage in Factory 2
    save_shift_wastage(
        payload=ShiftWastageCreate(
            date=date(2026, 6, 13),
            shift="Day",
            wastage_kg=Decimal("5.0"),
            note="F2 waste"
        ),
        current_user=u2,
        db=db
    )
    
    # Assert Factory 1 still has its original wastage
    w_f1_check = get_shift_wastage(date=date(2026, 6, 13), shift="Day", current_user=u1, db=db)
    assert w_f1_check.wastage_kg == 15.0

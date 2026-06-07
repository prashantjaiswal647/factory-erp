from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import (
    AttendanceLog,
    BlankStock,
    BottomStock,
    Customer,
    DailyProduction,
    Factory,
    Machine,
    OutstandingBill,
    Payment,
    SalesInvoice,
    User,
)


BRIEFING_DATE = date(2026, 6, 5)


def make_briefing_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    return engine, SessionLocal()


def seed_two_factories(db):
    factory_a = Factory(id=1, name="Briefing Factory A", subscription_status="active")
    factory_b = Factory(id=2, name="Briefing Factory B", subscription_status="active")
    db.add_all([factory_a, factory_b])
    db.flush()

    owner_a = User(
        id=11,
        factory_id=1,
        username="briefing-owner-a",
        full_name="Owner A",
        password_hash="unused",
        role="Owner",
        is_active=True,
    )
    owner_b = User(
        id=22,
        factory_id=2,
        username="briefing-owner-b",
        full_name="Owner B",
        password_hash="unused",
        role="Owner",
        is_active=True,
    )
    machine_a = Machine(id=101, factory_id=1, name="Machine A", target_output_per_shift=100)
    machine_b = Machine(id=202, factory_id=2, name="Machine B", target_output_per_shift=900)
    customer_a = Customer(id=301, factory_id=1, name="Alpha Buyer")
    customer_b = Customer(id=302, factory_id=2, name="Secret Beta Buyer")
    db.add_all([owner_a, owner_b, machine_a, machine_b, customer_a, customer_b])
    db.flush()
    db.add_all(
        [
            DailyProduction(
                factory_id=1,
                date=BRIEFING_DATE,
                machine_id=machine_a.id,
                product_size_ml=100,
                variety="White",
                packaging_size_name="A Box",
                packets_per_box_limit=10,
                total_boxes_made=70,
            ),
            DailyProduction(
                factory_id=2,
                date=BRIEFING_DATE,
                machine_id=machine_b.id,
                product_size_ml=200,
                variety="Secret",
                packaging_size_name="B Box",
                packets_per_box_limit=10,
                total_boxes_made=800,
            ),
            AttendanceLog(factory_id=1, date=BRIEFING_DATE, status="Present", is_present=True),
            AttendanceLog(factory_id=1, date=BRIEFING_DATE, status="Absent", is_present=False),
            AttendanceLog(factory_id=2, date=BRIEFING_DATE, status="Present", is_present=True),
            AttendanceLog(factory_id=2, date=BRIEFING_DATE, status="Present", is_present=True),
            Payment(factory_id=1, customer_phone="111", amount_paid=Decimal("2500"), date=BRIEFING_DATE),
            Payment(factory_id=2, customer_phone="222", amount_paid=Decimal("99999"), date=BRIEFING_DATE),
            SalesInvoice(
                factory_id=1,
                customer_id=customer_a.id,
                date=BRIEFING_DATE,
                cup_size_ml=100,
                packaging_profile_id=401,
                boxes_sold=10,
                total_amount=Decimal("12000"),
                amount_paid=Decimal("2500"),
            ),
            SalesInvoice(
                factory_id=2,
                customer_id=customer_b.id,
                date=BRIEFING_DATE,
                cup_size_ml=200,
                packaging_profile_id=402,
                boxes_sold=80,
                total_amount=Decimal("654321"),
                amount_paid=Decimal("99999"),
            ),
            OutstandingBill(
                factory_id=1,
                customer_id=customer_a.id,
                tracking_number="A-1",
                bill_date=BRIEFING_DATE,
                bill_amount=Decimal("130000"),
                balance_amount=Decimal("125000"),
                status="active",
            ),
            OutstandingBill(
                factory_id=2,
                customer_id=customer_b.id,
                tracking_number="B-1",
                bill_date=BRIEFING_DATE,
                bill_amount=Decimal("88888"),
                balance_amount=Decimal("77777"),
                status="active",
            ),
            BottomStock(
                factory_id=1,
                bottom_size_mm=45,
                variety="White",
                total_qty_kg=Decimal("150"),
            ),
            BlankStock(
                factory_id=1,
                blank_size_ml=100,
                variety="White",
                linked_bottom_size_mm=45,
                total_qty_kg=Decimal("700"),
            ),
            BottomStock(
                factory_id=2,
                bottom_size_mm=55,
                variety="Secret",
                total_qty_kg=Decimal("9000"),
            ),
            BlankStock(
                factory_id=2,
                blank_size_ml=200,
                variety="Secret",
                linked_bottom_size_mm=55,
                total_qty_kg=Decimal("100"),
            ),
        ]
    )
    db.commit()
    return owner_a, owner_b

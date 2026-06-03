import pytest
from datetime import datetime
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import (
    Factory,
    Worker,
    Employee,
    FactoryExpense,
    ExpenseLog,
    PackagingProfile,
    FinishedGoodsStock,
    FinalProductStock,
    Machine,
    Inventory
)

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    # Seed factory
    factory = Factory(id=1, name="Test Factory")
    db.add(factory)
    db.commit()
    return db

def test_worker_employee_synchronization():
    db = init_db()
    try:
        # 1. Insert Worker
        worker = Worker(
            factory_id=1,
            name="John Doe",
            daily_wages=Decimal("500.00"),
            shift_type="Supervisor"
        )
        db.add(worker)
        db.commit()

        # Verify Employee auto-created
        employee = db.query(Employee).filter(Employee.factory_id == 1, Employee.name == "John Doe").first()
        assert employee is not None
        assert employee.role == "Supervisor"
        assert float(employee.daily_wage) == 500.00

        # 2. Update Worker
        worker.name = "John Smith"
        worker.daily_wages = Decimal("600.00")
        db.commit()

        print("WORKERS IN DB:", [w.name for w in db.query(Worker).all()])
        print("EMPLOYEES IN DB:", [(e.name, float(e.daily_wage)) for e in db.query(Employee).all()])

        # Verify Employee updated
        employee = db.query(Employee).filter(Employee.factory_id == 1, Employee.name == "John Smith").first()
        assert employee is not None
        assert float(employee.daily_wage) == 600.00

        # 3. Delete Worker
        db.delete(worker)
        db.commit()

        # Verify Employee deleted
        employee = db.query(Employee).filter(Employee.factory_id == 1, Employee.name == "John Smith").first()
        assert employee is None
    finally:
        db.close()

def test_expense_synchronization():
    db = init_db()
    try:
        # 1. Insert FactoryExpense
        expense = FactoryExpense(
            factory_id=1,
            expense_name="Office Supplies",
            amount=Decimal("150.50"),
            category="Office"
        )
        db.add(expense)
        db.commit()

        # Verify ExpenseLog created
        log = db.query(ExpenseLog).filter(ExpenseLog.factory_id == 1, ExpenseLog.description == "Office Supplies").first()
        assert log is not None
        assert log.category == "Office"
        assert float(log.amount) == 150.50

        # 2. Update FactoryExpense
        expense.expense_name = "Office Supplies Upgraded"
        expense.amount = Decimal("200.00")
        db.commit()

        print("EXPENSES IN DB:", [ex.expense_name for ex in db.query(FactoryExpense).all()])
        print("EXPENSE_LOGS IN DB:", [(el.description, float(el.amount)) for el in db.query(ExpenseLog).all()])

        log = db.query(ExpenseLog).filter(ExpenseLog.factory_id == 1, ExpenseLog.description == "Office Supplies Upgraded").first()
        assert log is not None
        assert float(log.amount) == 200.00

        # 3. Delete FactoryExpense
        db.delete(expense)
        db.commit()

        log = db.query(ExpenseLog).filter(ExpenseLog.factory_id == 1, ExpenseLog.description == "Office Supplies Upgraded").first()
        assert log is None
    finally:
        db.close()

def test_finished_goods_final_product_synchronization():
    db = init_db()
    try:
        # Seed dependencies for FinishedGoodsStock
        box_inv = Inventory(factory_id=1, item_name="Box Material", category="Packaging", unit="pieces", quantity=Decimal("100"), price_per_unit=Decimal("10"))
        poly_inv = Inventory(factory_id=1, item_name="Poly Material", category="Packaging", unit="pieces", quantity=Decimal("200"), price_per_unit=Decimal("2"))
        db.add_all([box_inv, poly_inv])
        db.flush()

        profile = PackagingProfile(
            id=10,
            factory_id=1,
            profile_name="250ML Special Packing",
            cup_size_ml=250,
            cups_per_poly=50,
            polys_per_box=10,
            box_capacity=500,
            box_inventory_id=box_inv.id,
            poly_inventory_id=poly_inv.id
        )
        db.add(profile)
        db.commit()

        # 1. Insert FinishedGoodsStock
        fg = FinishedGoodsStock(
            factory_id=1,
            cup_size_ml=250,
            packaging_profile_id=10,
            boxes_available=15,
            variant_name="Special Design"
        )
        db.add(fg)
        db.commit()

        # Verify FinalProductStock created
        fp = db.query(FinalProductStock).filter(
            FinalProductStock.factory_id == 1,
            FinalProductStock.product_size_ml == 250,
            FinalProductStock.variety == "Special Design"
        ).first()
        assert fp is not None
        assert fp.packaging_size_name == "250ML Special Packing"
        assert fp.total_boxes == 15
        assert fp.current_quantity == 15 * 500

        # 2. Update FinishedGoodsStock
        fg.boxes_available = 25
        db.commit()

        fp = db.query(FinalProductStock).filter(
            FinalProductStock.factory_id == 1,
            FinalProductStock.product_size_ml == 250,
            FinalProductStock.variety == "Special Design"
        ).first()
        assert fp.total_boxes == 25
        assert fp.current_quantity == 25 * 500
    finally:
        db.close()

def test_machine_columns_synchronization():
    db = init_db()
    try:
        # Insert Machine with speed_per_minute and mould_size_ml
        machine = Machine(
            factory_id=1,
            name="Machine Alpha",
            speed_per_minute=80,
            mould_size_ml=210
        )
        db.add(machine)
        db.commit()

        # Verify other speed/size columns aligned before write
        assert machine.speed_bpm == 80
        assert machine.speed_cups_per_minute == 80
        assert machine.default_speed == 80.0
        assert machine.cup_size_ml == 210
        assert machine.current_mould_size == "210"
        assert machine.default_mould_size == "210"
    finally:
        db.close()

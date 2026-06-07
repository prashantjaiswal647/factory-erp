from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import BottomStock, Customer, Factory, Machine, Worker, WorkerOpeningAttendance
from routers.onboarding import apply_bulk_rows, build_master_onboarding_workbook, dedupe_valid_bulk_rows, validate_bulk_frame


def customer_row(**overrides):
    row = {
        "row_type": "ACTUAL",
        "name": "Rajesh Kumar",
        "firm_name": "Rajesh Traders",
        "contact_number": "9876543210",
        "phone_number": "9876543210",
        "place": "Delhi",
        "address": "Wazirpur Industrial Area",
        "gst_number": "07ABCDE1234F1Z5",
        "previous_due": Decimal("1500"),
    }
    row.update(overrides)
    return row


def test_master_template_contains_customers_sheet_with_valid_sample():
    workbook = pd.read_excel(BytesIO(build_master_onboarding_workbook().getvalue()), sheet_name=None, header=None)

    assert "Customers" in workbook
    headers = workbook["Customers"].iloc[1].tolist()
    assert headers == [
        "row_type",
        "name",
        "firm_name",
        "contact_number",
        "phone_number",
        "place",
        "address",
        "gst_number",
        "previous_due",
    ]


def test_customer_bulk_row_validation_rejects_blank_name():
    frame = pd.DataFrame([customer_row(name="")])

    rows, errors = validate_bulk_frame(frame, "customer", "Customers")

    assert rows == []
    assert len(errors) == 1
    assert "name" in errors[0]["error"]


def test_customer_sheet_without_previous_due_imports_with_zero_balance():
    frame = pd.DataFrame(
        [
            {
                "row_type": "ACTUAL",
                "customer_name": "Minimal Customer",
                "phone": "9876500000",
                "address": "Delhi",
            }
        ]
    )

    rows, errors = validate_bulk_frame(frame, "customer", "Customers")

    assert errors == []
    assert len(rows) == 1
    assert rows[0]["name"] == "Minimal Customer"
    assert rows[0]["phone_number"] == "9876500000"
    assert rows[0]["previous_due"] == Decimal("0")

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        factory = Factory(name="Minimal Customer Factory")
        db.add(factory)
        db.flush()

        assert apply_bulk_rows(
            db,
            SimpleNamespace(id=1, factory_id=factory.id),
            "customer",
            rows,
            {},
        ) == 1
        db.commit()

        customer = db.query(Customer).filter(Customer.factory_id == factory.id).one()
        assert customer.name == "Minimal Customer"
        assert customer.phone_number == "9876500000"
        assert customer.address == "Delhi"
        assert customer.previous_due == Decimal("0")
        assert customer.total_due == Decimal("0")
        assert customer.pending_balance == Decimal("0")
        assert customer.balance_amount == Decimal("0")
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_customer_bulk_upload_happy_path_and_idempotent_reupload():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        current_user = SimpleNamespace(id=1, factory_id=2)
        first_stats = {"inserted": 0, "updated": 0, "skipped": 0}
        assert apply_bulk_rows(db, current_user, "customer", [customer_row()], first_stats) == 1
        db.commit()

        second_stats = {"inserted": 0, "updated": 0, "skipped": 0}
        assert apply_bulk_rows(
            db,
            current_user,
            "customer",
            [customer_row(firm_name="Rajesh Enterprises", previous_due=Decimal("1750"))],
            second_stats,
        ) == 1
        db.commit()

        customers = db.query(Customer).filter(Customer.factory_id == 2).all()
        assert len(customers) == 1
        assert customers[0].firm_name == "Rajesh Enterprises"
        assert customers[0].phone == "9876543210"
        assert customers[0].previous_due == Decimal("1750")
        assert customers[0].total_due == Decimal("1750")
        assert customers[0].pending_dues == 1750.0
        assert customers[0].pending_balance == Decimal("1750")
        assert customers[0].balance_amount == Decimal("1750")
        assert first_stats["inserted"] == 1
        assert second_stats["updated"] == 1
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_customer_bulk_upload_is_isolated_by_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        factory_a = Factory(name="Factory A")
        factory_b = Factory(name="Factory B")
        db.add_all([factory_a, factory_b])
        db.flush()

        shared_customer = customer_row(
            name="Shree Traders",
            firm_name="Shree Traders",
            contact_number="9876543210",
            phone_number="9876543210",
            gst_number="07ABCDE1234F1Z5",
        )
        assert apply_bulk_rows(
            db,
            SimpleNamespace(id=1, factory_id=factory_a.id),
            "customer",
            [shared_customer],
            {},
        ) == 1
        assert apply_bulk_rows(
            db,
            SimpleNamespace(id=2, factory_id=factory_b.id),
            "customer",
            [shared_customer],
            {},
        ) == 1
        db.commit()

        assert apply_bulk_rows(
            db,
            SimpleNamespace(id=1, factory_id=factory_a.id),
            "customer",
            [customer_row(
                name="Shree Traders",
                firm_name="Factory A Updated Customer",
                contact_number="9876543210",
                phone_number="9876543210",
                gst_number="07ABCDE1234F1Z5",
            )],
            {},
        ) == 1
        db.commit()

        customers = db.query(Customer).filter(Customer.name == "Shree Traders").order_by(Customer.factory_id).all()
        assert len(customers) == 2
        assert {customer.factory_id for customer in customers} == {factory_a.id, factory_b.id}

        factory_a_customer = next(customer for customer in customers if customer.factory_id == factory_a.id)
        factory_b_customer = next(customer for customer in customers if customer.factory_id == factory_b.id)
        assert factory_a_customer.firm_name == "Factory A Updated Customer"
        assert factory_b_customer.firm_name == "Shree Traders"
        assert factory_a_customer.phone_number == factory_b_customer.phone_number == "9876543210"
        assert factory_a_customer.gst_number == factory_b_customer.gst_number == "07ABCDE1234F1Z5"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_bottom_reel_bulk_rows_default_blank_weight_to_zero():
    frame = pd.DataFrame(
        [
            {
                "row_type": "ACTUAL",
                "bottom_size_mm": 65,
                "total_individual_rolls": 49,
                "total_weight_kg": None,
            }
        ]
    )

    rows, errors = validate_bulk_frame(frame, "bottom_reel", "Raw Materials", row_offset=20)

    assert errors == []
    assert rows == [
        {
            "row_type": "ACTUAL",
            "bottom_size_mm": 65,
            "total_individual_rolls": 49,
            "total_weight_kg": Decimal("0"),
            "_row_number": 1,
        }
    ]


def test_plastic_stock_bulk_rows_expand_comma_separated_cup_sizes():
    frame = pd.DataFrame(
        [
            {
                "row_type": "ACTUAL",
                "plastic_size_type": "3.5*18",
                "used_for_cup_size_ml": "55,65",
                "total_boras_sacks": 4,
                "weight_per_bora_kg": 30,
                "price_per_kg_rs": 180,
            }
        ]
    )

    rows, errors = validate_bulk_frame(frame, "plastic_stock", "Raw Materials", row_offset=64)

    assert errors == []
    assert [row["used_for_cup_size_ml"] for row in rows] == [55, 65]
    assert {row["plastic_size_type"] for row in rows} == {"3.5*18"}


def test_worker_bulk_upload_updates_existing_worker_in_same_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        db.add(Worker(factory_id=2, name="Anjal Kumar", phone="9000000000", daily_wages=300, daily_wage_rate=300))
        db.commit()

        current_user = SimpleNamespace(id=1, factory_id=2)
        row_count = apply_bulk_rows(
            db,
            current_user,
            "worker",
            [
                {
                    "row_type": "ACTUAL",
                    "name": "Anjal Kumar",
                    "mobile_number": "8285817277",
                    "daily_wages": Decimal("400"),
                    "duty_hours": Decimal("8"),
                    "previous_attendance_details": Decimal("0"),
                }
            ],
        )
        db.commit()

        workers = db.query(Worker).filter(Worker.factory_id == 2, Worker.name == "Anjal Kumar").all()
        assert row_count == 1
        assert len(workers) == 1
        assert workers[0].phone == "+918285817277"
        assert workers[0].daily_wages == Decimal("400")
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_worker_bulk_upload_same_file_reupload_updates_without_duplicates():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        current_user = SimpleNamespace(id=1, factory_id=2)
        rows = [
            {
                "row_type": "ACTUAL",
                "name": "Anjal Kumar",
                "mobile_number": "8285817277",
                "daily_wages": Decimal("400"),
                "duty_hours": Decimal("8"),
                "previous_attendance_details": Decimal("0"),
            }
        ]

        first_stats = {"inserted": 0, "updated": 0, "skipped": 0}
        first_count = apply_bulk_rows(db, current_user, "worker", rows, first_stats)
        db.commit()

        second_rows = [{**rows[0], "daily_wages": Decimal("450")}]
        second_stats = {"inserted": 0, "updated": 0, "skipped": 0}
        second_count = apply_bulk_rows(db, current_user, "worker", second_rows, second_stats)
        db.commit()

        workers = db.query(Worker).filter(Worker.factory_id == 2, Worker.name == "Anjal Kumar").all()
        assert first_count == 1
        assert second_count == 1
        assert first_stats["inserted"] == 1
        assert second_stats["updated"] == 1
        assert len(workers) == 1
        assert workers[0].daily_wages == Decimal("450")
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_duplicate_rows_in_same_workbook_are_deduped_with_warning():
    valid_by_type = {
        "worker": [
            {
                "row_type": "ACTUAL",
                "name": "Anjal Kumar",
                "mobile_number": "8285817277",
                "daily_wages": Decimal("400"),
                "duty_hours": Decimal("8"),
                "previous_attendance_details": Decimal("0"),
                "_row_number": 3,
            },
            {
                "row_type": "ACTUAL",
                "name": "Anjal Kumar",
                "mobile_number": "8285817277",
                "daily_wages": Decimal("450"),
                "duty_hours": Decimal("8"),
                "previous_attendance_details": Decimal("0"),
                "_row_number": 4,
            },
        ]
    }

    deduped, warnings = dedupe_valid_bulk_rows(valid_by_type)

    assert len(deduped["worker"]) == 1
    assert deduped["worker"][0]["daily_wages"] == Decimal("450")
    assert len(warnings) == 1
    assert warnings[0].row == 4
    assert warnings[0].severity == "warning"


def test_bottom_reel_bulk_upload_updates_existing_stock_in_same_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        db.add(
            BottomStock(
                factory_id=2,
                bottom_size_mm=65,
                variety="Plain White",
                total_rolls=10,
                total_weight_kg=Decimal("25"),
                total_qty_kg=Decimal("25"),
            )
        )
        db.commit()

        current_user = SimpleNamespace(id=1, factory_id=2)
        row_count = apply_bulk_rows(
            db,
            current_user,
            "bottom_reel",
            [
                {
                    "row_type": "ACTUAL",
                    "bottom_size_mm": 65,
                    "total_individual_rolls": 49,
                    "total_weight_kg": Decimal("0"),
                }
            ],
        )
        db.commit()

        stocks = (
            db.query(BottomStock)
            .filter(BottomStock.factory_id == 2, BottomStock.bottom_size_mm == 65, BottomStock.variety == "Plain White")
            .all()
        )
        assert row_count == 1
        assert len(stocks) == 1
        assert stocks[0].total_rolls == 49
        assert stocks[0].total_weight_kg == Decimal("0")
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_machine_bulk_upload_updates_existing_machine_in_same_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        db.add(
            Machine(
                factory_id=2,
                name="Hi-Speed Cup Machine X",
                machine_name="Hi-Speed Cup Machine X",
                machine_type="Hi-Speed Cup Machine X",
                speed_per_minute=60,
                speed_bpm=60,
                speed_cups_per_minute=60,
                default_speed=60,
                target_output_per_shift=20000,
                raw_materials_mapped=[],
                is_active=True,
            )
        )
        db.commit()

        current_user = SimpleNamespace(id=1, factory_id=2)
        row_count = apply_bulk_rows(
            db,
            current_user,
            "machine",
            [
                {
                    "row_type": "ACTUAL",
                    "machine_name": "Hi-Speed Cup Machine X",
                    "default_operating_speed": 120,
                    "target_output_per_shift": 55000,
                    "mould_size_ml": 210,
                    "bottom_size_mm": 68,
                }
            ],
        )
        db.commit()

        machines = db.query(Machine).filter(Machine.factory_id == 2, Machine.name == "Hi-Speed Cup Machine X").all()
        assert row_count == 1
        assert len(machines) == 1
        assert machines[0].default_speed == 120
        assert machines[0].target_output_per_shift == 55000
        assert machines[0].mould_size_ml == 210
        assert machines[0].bottom_size_mm == 68
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_worker_bulk_upload_updates_existing_opening_attendance():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        worker = Worker(factory_id=2, name="Anjal Kumar", phone="9000000000", daily_wages=300, daily_wage_rate=300)
        db.add(worker)
        db.flush()
        db.add(
            WorkerOpeningAttendance(
                factory_id=2,
                worker_id=worker.id,
                period_start=date.today(),
                period_end=date.today(),
                present_days=Decimal("3"),
                created_by_user_id=1,
            )
        )
        db.commit()

        current_user = SimpleNamespace(id=1, factory_id=2)
        row_count = apply_bulk_rows(
            db,
            current_user,
            "worker",
            [
                {
                    "row_type": "ACTUAL",
                    "name": "Anjal Kumar",
                    "mobile_number": "8285817277",
                    "daily_wages": Decimal("400"),
                    "duty_hours": Decimal("8"),
                    "previous_attendance_details": Decimal("7"),
                }
            ],
        )
        db.commit()

        attendance_rows = db.query(WorkerOpeningAttendance).filter(WorkerOpeningAttendance.factory_id == 2).all()
        assert row_count == 1
        assert len(attendance_rows) == 1
        assert attendance_rows[0].present_days == Decimal("7")
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_finished_goods_bulk_upload_creates_final_product_stock():
    from models import FinishedGoodsStock, FinalProductStock, PackagingProfile
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        current_user = SimpleNamespace(id=1, factory_id=2)
        row_count = apply_bulk_rows(
            db,
            current_user,
            "finished_goods",
            [
                {
                    "row_type": "ACTUAL",
                    "product_size_ml": 250,
                    "variety_design": "Spiderman Design",
                    "packaging_size_name": "250ML Spiderman Carton",
                    "pcs_per_packet": 100,
                    "packets_per_box": 10,
                    "initial_stock_boxes": 5,
                }
            ],
        )
        db.commit()

        # Check FinishedGoodsStock
        fg_stocks = db.query(FinishedGoodsStock).filter(FinishedGoodsStock.factory_id == 2).all()
        assert len(fg_stocks) == 1
        assert fg_stocks[0].boxes_available == 5
        assert fg_stocks[0].cup_size_ml == 250

        # Check FinalProductStock
        final_stocks = db.query(FinalProductStock).filter(FinalProductStock.factory_id == 2).all()
        assert len(final_stocks) == 1
        assert final_stocks[0].total_boxes == 5
        assert final_stocks[0].product_size_ml == 250
        assert final_stocks[0].variety == "Spiderman Design"
        assert final_stocks[0].packaging_size_name == "250ML Spiderman Carton"
        assert final_stocks[0].pieces_per_packet == 100
        assert final_stocks[0].packets_per_box_limit == 10
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


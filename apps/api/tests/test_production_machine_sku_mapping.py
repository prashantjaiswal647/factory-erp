from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import get_current_user
from db import Base, get_db
from main import app
from models import (
    BlankStock,
    BottomStock,
    BoxStock,
    Factory,
    FinalProductStock,
    Machine,
    ProductionBatch,
    ProductionBatchOutputLine,
    ProductionBatchWorkerLine,
    ShiftWastage,
    User,
    Worker,
)
from tests.test_e2e_erp_flow import ensure_testclient_compatibility


@pytest.fixture()
def mapped_production_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    user = SimpleNamespace(id=1, factory_id=1, role="Owner", username="owner@test", full_name="Owner")

    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    db = session_factory()
    db.add_all([
        Factory(id=1, name="Mapping Factory", subscription_status="active", active_plan="growth"),
        User(id=1, factory_id=1, username="owner@test", email="owner@test", role="Owner", password_hash="x", is_verified=True),
        Worker(id=1, factory_id=1, name="Raju", is_active=True),
        Worker(id=2, factory_id=1, name="Mohan", is_active=True),
        Worker(id=3, factory_id=1, name="Sohan", is_active=True),
        Machine(id=1, factory_id=1, name="Machine 210", machine_number="1", mould_size_ml=210, cup_size_ml=210, bottom_size_mm=47, is_active=True),
        Machine(id=2, factory_id=1, name="Machine 55", machine_number="2", mould_size_ml=55, cup_size_ml=55, bottom_size_mm=35, is_active=True),
        BlankStock(factory_id=1, blank_size_ml=210, variety="White", linked_bottom_size_mm=47, weight_per_bora_kg=Decimal("40"), total_boras=Decimal("10"), total_qty_kg=Decimal("400")),
        BottomStock(factory_id=1, bottom_size_mm=47, variety="White", total_rolls=10, total_weight_kg=Decimal("100"), total_qty_kg=Decimal("100")),
        BoxStock(factory_id=1, packaging_size_name="Big Box", box_type="Big Box", size_for_finished_product="210,250,300", total_boxes=20, quantity=20),
        BoxStock(factory_id=1, packaging_size_name="Premium Box", box_type="Premium Box", size_for_finished_product="210", total_boxes=20, quantity=20),
        FinalProductStock(id=2101, factory_id=1, product_size_ml=210, variety="White", packaging_size_name="210-48", carton_type="Big Box", pieces_per_packet=48, packets_per_box_limit=10, current_quantity=2, total_boxes=2, loose_packets=0),
        FinalProductStock(id=2102, factory_id=1, product_size_ml=210, variety="Lovely Day", packaging_size_name="210-45", carton_type="Big Box", pieces_per_packet=45, packets_per_box_limit=10, current_quantity=0, total_boxes=0, loose_packets=0),
        FinalProductStock(id=2103, factory_id=1, product_size_ml=210, variety="Premium", packaging_size_name="210-62", carton_type="Premium Box", pieces_per_packet=62, packets_per_box_limit=10, current_quantity=0, total_boxes=0, loose_packets=8),
        FinalProductStock(id=5501, factory_id=1, product_size_ml=55, variety="Plain White", packaging_size_name="55-40", carton_type="Small Box", pieces_per_packet=40, packets_per_box_limit=10, current_quantity=0, total_boxes=0, loose_packets=0),
    ])
    db.commit()
    db.close()
    ensure_testclient_compatibility()
    yield TestClient(app), session_factory
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_machine_scoped_options_and_exact_inventory_impact(mapped_production_client):
    client, session_factory = mapped_production_client
    options = client.get("/api/inventory/final-stock", params={"machine_id": 1})
    assert options.status_code == 200
    assert {row["product_size_ml"] for row in options.json()} == {210}
    assert all(row["id"] != 5501 for row in options.json())

    wrong = client.post("/api/production/daily", json={
        "date": "2026-06-03", "worker_id": 1, "machine_id": 1, "product_id": 5501,
        "product_size_ml": 55, "variety": "Plain White", "packaging_size_name": "55-40",
        "pieces_per_packet": 40, "packets_per_box_limit": 10, "total_boxes_made": 1,
        "loose_packets_made": 0, "blank_used_bori": 0, "bottom_used_rolls": 0,
    })
    assert wrong.status_code == 400
    assert "Machine size: 210ml, Product size: 55ml" in wrong.json()["detail"]

    valid = client.post("/api/production/daily", json={
        "date": "2026-06-03", "worker_id": 1, "machine_id": 1, "product_id": 2101,
        "product_size_ml": 210, "variety": "White", "packaging_size_name": "210-48",
        "pieces_per_packet": 48, "packets_per_box_limit": 10, "total_boxes_made": 1,
        "loose_packets_made": 0, "blank_used_bori": 1, "bottom_used_rolls": 1,
    })
    assert valid.status_code == 201, valid.text

    db = session_factory()
    assert db.get(FinalProductStock, 2101).current_quantity == 3
    assert db.query(BlankStock).filter_by(blank_size_ml=210, variety="White").one().total_boras == Decimal("9")
    assert db.query(BottomStock).filter_by(bottom_size_mm=47, variety="White").one().total_rolls == 9
    db.close()


def test_one_worker_two_outputs_deducts_shared_raw_material_once(mapped_production_client):
    client, session_factory = mapped_production_client
    db = session_factory()
    sku = db.get(FinalProductStock, 2101)
    sku.loose_packets = 5
    db.commit()
    db.close()

    payload = {
        "date": "2026-06-04",
        "shift": "Night",
        "machine_id": 1,
        "worker_cards": [
            {
                "worker_id": 1,
                "blank_used_bora": 2,
                "bottom_used_roll": 1,
                "outputs": [
                    {"finished_good_id": 2101, "boxes_made": 5, "loose_packets_made": 0},
                    {"finished_good_id": 2102, "boxes_made": 5, "loose_packets_made": 0},
                ],
            },
        ],
        "shift_wastage_kg": 1.25,
        "wastage_note": "Shift setup loss",
    }
    response = client.post("/api/production/daily-batch", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["worker_line_count"] == 1
    assert body["output_line_count"] == 2
    assert body["finished_boxes_added"] == 10
    assert body["blank_bora_deducted"] == 2
    assert body["bottom_rolls_deducted"] == 1

    db = session_factory()
    batch = db.query(ProductionBatch).one()
    assert batch.shift_wastage_kg == Decimal("1.250")
    assert db.query(ProductionBatchWorkerLine).count() == 1
    assert db.query(ProductionBatchOutputLine).count() == 2
    assert db.get(FinalProductStock, 2101).current_quantity == 7
    assert db.get(FinalProductStock, 2102).current_quantity == 5
    assert db.query(BoxStock).filter_by(box_type="Big Box").one().total_boxes == 10
    assert db.query(BlankStock).filter_by(blank_size_ml=210).one().total_boras == Decimal("8")
    assert db.query(BottomStock).filter_by(bottom_size_mm=47).one().total_rolls == 9
    assert db.query(ShiftWastage).count() == 1
    db.close()


def test_two_workers_multiple_outputs_sum_raw_and_cartons_by_type(mapped_production_client):
    client, session_factory = mapped_production_client
    response = client.post("/api/production/daily-batch", json={
        "date": "2026-06-05",
        "shift": "Day",
        "machine_id": 1,
        "worker_cards": [
            {
                "worker_id": 1, "blank_used_bora": 1, "bottom_used_roll": 1,
                "outputs": [
                    {"finished_good_id": 2101, "boxes_made": 2, "loose_packets_made": 0},
                    {"finished_good_id": 2103, "boxes_made": 1, "loose_packets_made": 4},
                ],
            },
            {
                "worker_id": 2, "blank_used_bora": 2, "bottom_used_roll": 1,
                "outputs": [
                    {"finished_good_id": 2102, "boxes_made": 3, "loose_packets_made": 0},
                ],
            },
        ],
        "shift_wastage_kg": 0.5,
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["blank_bora_deducted"] == 3
    assert body["bottom_rolls_deducted"] == 2
    assert body["cartons_deducted_by_type"] == {"big box": 5, "premium box": 2}

    db = session_factory()
    assert db.query(BlankStock).one().total_boras == Decimal("7")
    assert db.query(BottomStock).one().total_rolls == 8
    assert db.query(BoxStock).filter_by(box_type="Big Box").one().total_boxes == 15
    assert db.query(BoxStock).filter_by(box_type="Premium Box").one().total_boxes == 18
    assert db.get(FinalProductStock, 2103).current_quantity == 2
    premium_output = db.query(ProductionBatchOutputLine).filter_by(finished_good_id=2103).one()
    assert premium_output.boxes_from_loose == 1
    assert db.query(ProductionBatch).one().remaining_loose_packets == 2
    db.close()

    second = client.post("/api/production/daily-batch", json={
        "date": "2026-06-05",
        "shift": "Night",
        "machine_id": 1,
        "worker_cards": [{
            "worker_id": 3, "blank_used_bora": 0, "bottom_used_roll": 0,
            "outputs": [{"finished_good_id": 2103, "boxes_made": 0, "loose_packets_made": 8}],
        }],
        "shift_wastage_kg": 0,
    })
    assert second.status_code == 201, second.text
    assert second.json()["converted_boxes_from_loose"] == 1
    assert second.json()["remaining_loose_packets"] == 0


def test_product_size_mismatch_returns_400(mapped_production_client):
    client, _ = mapped_production_client
    response = client.post("/api/production/daily-batch", json={
        "date": "2026-06-05", "shift": "Day", "machine_id": 1,
        "worker_cards": [{
            "worker_id": 1, "blank_used_bora": 0, "bottom_used_roll": 0,
            "outputs": [{"finished_good_id": 5501, "boxes_made": 1, "loose_packets_made": 0}],
        }],
        "shift_wastage_kg": 0,
    })
    assert response.status_code == 400
    assert "mould size" in response.json()["detail"]


def test_shift_batch_inventory_failure_rolls_back_everything(mapped_production_client):
    client, session_factory = mapped_production_client
    db = session_factory()
    db.query(BoxStock).filter_by(box_type="Big Box").one().total_boxes = 1
    db.commit()
    db.close()

    response = client.post("/api/production/daily-batch", json={
        "date": "2026-06-04",
        "shift": "Day",
        "machine_id": 1,
        "worker_cards": [
            {
                "worker_id": 1, "blank_used_bora": 11, "bottom_used_roll": 1,
                "outputs": [{"finished_good_id": 2101, "boxes_made": 2, "loose_packets_made": 0}],
            },
            {
                "worker_id": 2, "blank_used_bora": 1, "bottom_used_roll": 1,
                "outputs": [{"finished_good_id": 2102, "boxes_made": 2, "loose_packets_made": 0}],
            },
        ],
        "shift_wastage_kg": 0,
    })
    assert response.status_code == 400
    db = session_factory()
    assert db.query(ProductionBatch).count() == 0
    assert db.query(ProductionBatchWorkerLine).count() == 0
    assert db.query(ProductionBatchOutputLine).count() == 0
    assert db.query(BoxStock).filter_by(box_type="Big Box").one().total_boxes == 1
    assert db.query(BlankStock).filter_by(blank_size_ml=210).one().total_boras == Decimal("10")
    assert db.query(ShiftWastage).count() == 0
    db.close()


@pytest.mark.parametrize(
    ("stock_kind", "expected_detail"),
    [
        ("blank", "Insufficient blank stock"),
        ("bottom", "Insufficient bottom stock"),
        ("box", "Insufficient Box Stock"),
    ],
)
def test_each_insufficient_inventory_type_rolls_back(mapped_production_client, stock_kind, expected_detail):
    client, session_factory = mapped_production_client
    db = session_factory()
    if stock_kind == "blank":
        db.query(BlankStock).one().total_boras = Decimal("0")
        db.query(BlankStock).one().total_qty_kg = Decimal("0")
    elif stock_kind == "bottom":
        db.query(BottomStock).one().total_rolls = 0
        db.query(BottomStock).one().total_qty_kg = Decimal("0")
    else:
        db.query(BoxStock).filter_by(box_type="Big Box").one().total_boxes = 0
    db.commit()
    db.close()

    response = client.post("/api/production/daily-batch", json={
        "date": "2026-06-06",
        "shift": "Day",
        "machine_id": 1,
        "worker_cards": [{
            "worker_id": 1,
            "blank_used_bora": 1,
            "bottom_used_roll": 1,
            "outputs": [{"finished_good_id": 2101, "boxes_made": 1, "loose_packets_made": 0}],
        }],
        "shift_wastage_kg": 0.25,
    })

    assert response.status_code == 400
    assert expected_detail.casefold() in response.json()["detail"].casefold()
    db = session_factory()
    assert db.query(ProductionBatch).count() == 0
    assert db.query(ProductionBatchWorkerLine).count() == 0
    assert db.query(ProductionBatchOutputLine).count() == 0
    assert db.query(ShiftWastage).count() == 0
    assert db.get(FinalProductStock, 2101).current_quantity == 2
    db.close()

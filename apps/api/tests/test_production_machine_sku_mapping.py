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
        Machine(id=1, factory_id=1, name="Machine 210", machine_number="1", mould_size_ml=210, cup_size_ml=210, bottom_size_mm=47, is_active=True),
        Machine(id=2, factory_id=1, name="Machine 55", machine_number="2", mould_size_ml=55, cup_size_ml=55, bottom_size_mm=35, is_active=True),
        BlankStock(factory_id=1, blank_size_ml=210, variety="White", linked_bottom_size_mm=47, weight_per_bora_kg=Decimal("40"), total_boras=Decimal("10"), total_qty_kg=Decimal("400")),
        BottomStock(factory_id=1, bottom_size_mm=47, variety="White", total_rolls=10, total_weight_kg=Decimal("100"), total_qty_kg=Decimal("100")),
        BoxStock(factory_id=1, packaging_size_name="210-48", total_boxes=20, quantity=20),
        FinalProductStock(id=2101, factory_id=1, product_size_ml=210, variety="White", packaging_size_name="210-48", pieces_per_packet=48, packets_per_box_limit=10, current_quantity=2, total_boxes=2, loose_packets=0),
        FinalProductStock(id=2102, factory_id=1, product_size_ml=210, variety="Lovely Day", packaging_size_name="210-45", pieces_per_packet=45, packets_per_box_limit=10, current_quantity=0, total_boxes=0, loose_packets=0),
        FinalProductStock(id=5501, factory_id=1, product_size_ml=55, variety="Plain White", packaging_size_name="55-40", pieces_per_packet=40, packets_per_box_limit=10, current_quantity=0, total_boxes=0, loose_packets=0),
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

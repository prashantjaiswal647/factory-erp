from datetime import datetime, timedelta, timezone
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
    ActionEvent,
    BlankStock,
    BottomStock,
    BoxStock,
    DailyProduction,
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
        User(id=1, factory_id=1, username="owner@test", email="owner@test", full_name="Owner", role="Owner", password_hash="x", is_verified=True),
        User(id=2, factory_id=1, username="supervisor@test", email="supervisor@test", full_name="Supervisor", role="Supervisor", password_hash="x", is_verified=True),
        User(id=3, factory_id=1, username="subowner@test", email="subowner@test", full_name="Sub Owner", role="Sub-Owner", password_hash="x", is_verified=True),
        User(id=4, factory_id=1, username="supervisor2@test", email="supervisor2@test", full_name="Supervisor Two", role="Supervisor", password_hash="x", is_verified=True),
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


def _production_payload(**overrides):
    payload = {
        "date": "2026-06-03",
        "worker_id": 1,
        "machine_id": 1,
        "product_id": 2101,
        "product_size_ml": 210,
        "variety": "White",
        "packaging_size_name": "210-48",
        "pieces_per_packet": 48,
        "packets_per_box_limit": 10,
        "total_boxes_made": 1,
        "loose_packets_made": 0,
        "blank_used_bori": 1,
        "bottom_used_rolls": 1,
    }
    payload.update(overrides)
    return payload


def _as_user(user_id: int, role: str, username: str):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=user_id,
        factory_id=1,
        role=role,
        username=username,
        full_name=username,
    )


def _set_action_event_created_date(session_factory, date_text: str) -> int:
    db = session_factory()
    event = db.query(ActionEvent).order_by(ActionEvent.id.desc()).first()
    assert event is not None
    event.created_at = datetime.fromisoformat(f"{date_text}T10:00:00+00:00")
    event_id = event.id
    db.commit()
    db.close()
    return event_id


def test_supervisor_reverses_own_latest_production_without_hard_delete(mapped_production_client):
    client, session_factory = mapped_production_client
    _as_user(2, "Supervisor", "Supervisor")

    created = client.post("/api/production/daily", json=_production_payload())
    assert created.status_code == 201, created.text
    production_id = created.json()["production_id"]

    db = session_factory()
    assert db.get(FinalProductStock, 2101).current_quantity == 3
    assert db.query(BlankStock).filter_by(blank_size_ml=210, variety="White").one().total_boras == Decimal("9")
    assert db.query(BottomStock).filter_by(bottom_size_mm=47, variety="White").one().total_rolls == 9
    db.close()

    reversed_response = client.post(
        f"/api/production/daily/{production_id}/reverse",
        json={"reason": "Duplicate entry"},
    )
    assert reversed_response.status_code == 200, reversed_response.text
    assert reversed_response.json()["status"] == "reversed"

    db = session_factory()
    row = db.query(DailyProduction).filter_by(id=production_id).one()
    assert row.status == "reversed"
    assert row.reversal_reason == "Duplicate entry"
    assert db.query(DailyProduction).count() == 1
    assert db.get(FinalProductStock, 2101).current_quantity == 2
    assert db.query(BlankStock).filter_by(blank_size_ml=210, variety="White").one().total_boras == Decimal("10.000")
    assert db.query(BottomStock).filter_by(bottom_size_mm=47, variety="White").one().total_rolls == 10
    db.close()


def test_production_save_creates_daily_sequence_action_event(mapped_production_client):
    client, session_factory = mapped_production_client
    _as_user(2, "Supervisor", "Supervisor")

    created = client.post("/api/production/daily", json=_production_payload(date="2026-06-15"))
    assert created.status_code == 201, created.text
    production_id = created.json()["production_id"]

    db = session_factory()
    event = db.query(ActionEvent).one()
    assert event.action_type == "PRODUCTION_ADDED"
    assert event.module == "production"
    assert event.entity_type == "daily_production"
    assert event.entity_id == production_id
    assert event.created_by_user_id == 2
    assert event.created_by_role == "Supervisor"
    assert event.status == "pending"
    assert event.before_payload_json["finished_goods"]["boxes"] == 2
    assert event.after_payload_json["finished_goods"]["boxes"] == 3
    assert event.impact_summary_json["worker_name"] == "Raju"
    db.close()


def test_daily_sequence_action_rollback_restores_stock_and_hides_from_active(mapped_production_client):
    client, session_factory = mapped_production_client
    _as_user(2, "Supervisor", "Supervisor")

    created = client.post("/api/production/daily", json=_production_payload(date="2026-06-16"))
    assert created.status_code == 201, created.text
    production_id = created.json()["production_id"]
    _set_action_event_created_date(session_factory, "2026-06-16")

    active = client.get("/api/daily-sequence/actions", params={"date": "2026-06-16"})
    assert active.status_code == 200, active.text
    event = active.json()["events"][0]
    assert event["entity_id"] == production_id
    assert event["created_by_name"] == "Supervisor"
    assert event["created_by_role"] == "Supervisor"
    assert event["allowed_actions"]["can_rollback"] is True
    assert event["allowed_actions"]["can_verify"] is True

    rollback = client.post(
        f"/api/daily-sequence/actions/{event['id']}/rollback",
        json={"reason": "Duplicate production entry"},
    )
    assert rollback.status_code == 200, rollback.text
    assert rollback.json()["status"] == "rolled_back"
    assert rollback.json()["rollback_reason"] == "Duplicate production entry"

    db = session_factory()
    row = db.query(DailyProduction).filter_by(id=production_id).one()
    assert row.status == "reversed"
    assert db.get(FinalProductStock, 2101).current_quantity == 2
    assert db.query(BlankStock).filter_by(blank_size_ml=210, variety="White").one().total_boras == Decimal("10.000")
    db.close()

    active_after = client.get("/api/daily-sequence/actions", params={"date": "2026-06-16"})
    assert active_after.status_code == 200
    assert active_after.json()["events"] == []

    rolled_back = client.get("/api/daily-sequence/actions", params={"date": "2026-06-16", "status": "rolled_back"})
    assert rolled_back.status_code == 200
    assert rolled_back.json()["events"][0]["rolled_back_by_name"] == "Supervisor"


def test_daily_sequence_action_permissions_block_hidden_rollback(mapped_production_client):
    client, session_factory = mapped_production_client
    _as_user(4, "Supervisor", "Supervisor Two")
    created = client.post("/api/production/daily", json=_production_payload(date="2026-06-17"))
    assert created.status_code == 201, created.text
    _set_action_event_created_date(session_factory, "2026-06-17")

    _as_user(2, "Supervisor", "Supervisor")
    hidden = client.get("/api/daily-sequence/actions", params={"date": "2026-06-17"})
    assert hidden.status_code == 200
    assert hidden.json()["events"] == []

    _as_user(1, "Owner", "Owner")
    owner_view = client.get("/api/daily-sequence/actions", params={"date": "2026-06-17"})
    assert owner_view.status_code == 200
    event = owner_view.json()["events"][0]
    assert event["allowed_actions"]["can_rollback"] is True

    _as_user(2, "Supervisor", "Supervisor")
    blocked = client.post(
        f"/api/daily-sequence/actions/{event['id']}/rollback",
        json={"reason": "Trying hidden action"},
    )
    assert blocked.status_code == 403


def test_daily_sequence_action_verify_marks_event_and_production_verified(mapped_production_client):
    client, session_factory = mapped_production_client
    _as_user(2, "Supervisor", "Supervisor")
    created = client.post("/api/production/daily", json=_production_payload(date="2026-06-18"))
    assert created.status_code == 201, created.text
    _set_action_event_created_date(session_factory, "2026-06-18")

    _as_user(1, "Owner", "Owner")
    action_list = client.get("/api/daily-sequence/actions", params={"date": "2026-06-18"})
    assert action_list.status_code == 200
    event_id = action_list.json()["events"][0]["id"]
    verified = client.post(f"/api/daily-sequence/actions/{event_id}/verify")
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "verified"
    assert verified.json()["verified_by_name"] == "Owner"

    db = session_factory()
    assert db.query(ActionEvent).filter_by(id=event_id).one().status == "verified"
    assert db.query(DailyProduction).filter_by(id=created.json()["production_id"]).one().status == "verified"
    db.close()


def test_supervisor_cannot_reverse_another_users_or_verified_or_old_entry(mapped_production_client):
    client, session_factory = mapped_production_client
    _as_user(1, "Owner", "Owner")
    owner_created = client.post("/api/production/daily", json=_production_payload(date="2026-06-07"))
    assert owner_created.status_code == 201, owner_created.text

    _as_user(2, "Supervisor", "Supervisor")
    forbidden = client.post(
        f"/api/production/daily/{owner_created.json()['production_id']}/reverse",
        json={"reason": "Not mine"},
    )
    assert forbidden.status_code == 403

    supervisor_created = client.post("/api/production/daily", json=_production_payload(date="2026-06-08"))
    assert supervisor_created.status_code == 201, supervisor_created.text
    supervisor_id = supervisor_created.json()["production_id"]

    _as_user(1, "Owner", "Owner")
    verify = client.post(f"/api/production/daily/{supervisor_id}/verify")
    assert verify.status_code == 200, verify.text

    _as_user(2, "Supervisor", "Supervisor")
    verified_reverse = client.post(
        f"/api/production/daily/{supervisor_id}/reverse",
        json={"reason": "Verified"},
    )
    assert verified_reverse.status_code == 403

    old_created = client.post("/api/production/daily", json=_production_payload(date="2026-06-09"))
    assert old_created.status_code == 201, old_created.text
    old_id = old_created.json()["production_id"]
    db = session_factory()
    row = db.query(DailyProduction).filter_by(id=old_id).one()
    row.created_at = datetime.now(timezone.utc) - timedelta(minutes=31)
    db.commit()
    db.close()

    old_reverse = client.post(
        f"/api/production/daily/{old_id}/reverse",
        json={"reason": "Too late"},
    )
    assert old_reverse.status_code == 403


def test_supervisor_cannot_reverse_another_supervisor_entry_and_api_hides_action(mapped_production_client):
    client, _ = mapped_production_client
    _as_user(4, "Supervisor", "Supervisor Two")
    created = client.post("/api/production/daily", json=_production_payload(date="2026-06-11"))
    assert created.status_code == 201, created.text
    production_id = created.json()["production_id"]

    _as_user(2, "Supervisor", "Supervisor")
    review = client.get("/api/production/review", params={"date": "2026-06-11"})
    assert review.status_code == 200
    entry = review.json()["entries"][0]
    assert entry["created_by"] == "Supervisor Two"
    assert entry["created_by_role"] == "Supervisor"
    assert entry["allowed_actions"]["can_reverse"] is False

    reverse = client.post(
        f"/api/production/daily/{production_id}/reverse",
        json={"reason": "Trying hidden action"},
    )
    assert reverse.status_code == 403


def test_owner_can_reverse_unverified_production_with_reason_and_review_lists_stock_impact(mapped_production_client):
    client, session_factory = mapped_production_client
    _as_user(2, "Supervisor", "Supervisor")
    created = client.post("/api/production/daily", json=_production_payload(date="2026-06-10"))
    assert created.status_code == 201, created.text
    production_id = created.json()["production_id"]
    assert created.json()["status"] == "pending_review"
    assert created.json()["stock_before_json"]["finished_goods"]["boxes"] == 2
    assert created.json()["stock_after_json"]["finished_goods"]["boxes"] == 3

    _as_user(1, "Owner", "Owner")
    review = client.get("/api/production/review", params={"date": "2026-06-10"})
    assert review.status_code == 200
    entry = review.json()["entries"][0]
    assert entry["worker_name"] == "Raju"
    assert entry["created_by"] == "Supervisor"
    assert entry["created_by_role"] == "Supervisor"
    assert entry["stock_before_json"]["finished_goods"]["boxes"] == 2
    assert entry["allowed_actions"] == {"can_reverse": True, "can_verify": True, "reason_required": True}

    missing_reason = client.post(f"/api/production/daily/{production_id}/reverse", json={"reason": ""})
    assert missing_reason.status_code == 422
    reversed_response = client.post(
        f"/api/production/daily/{production_id}/reverse",
        json={"reason": "Supervisor entered duplicate production"},
    )
    assert reversed_response.status_code == 200, reversed_response.text
    assert reversed_response.json()["status"] == "reversed"
    assert reversed_response.json()["reversed_by"] == "Owner"
    assert reversed_response.json()["reversal_reason"] == "Supervisor entered duplicate production"

    db = session_factory()
    assert db.query(DailyProduction).filter_by(id=production_id).one().reversed_by_user_id == 1
    db.close()


def test_owner_can_reverse_own_entry(mapped_production_client):
    client, _ = mapped_production_client
    _as_user(1, "Owner", "Owner")
    created = client.post("/api/production/daily", json=_production_payload(date="2026-06-12"))
    assert created.status_code == 201, created.text
    reverse = client.post(
        f"/api/production/daily/{created.json()['production_id']}/reverse",
        json={"reason": "Owner correcting own mistake"},
    )
    assert reverse.status_code == 200, reverse.text
    assert reverse.json()["status"] == "reversed"


def test_sub_owner_can_reverse_supervisor_but_not_owner_entry(mapped_production_client):
    client, _ = mapped_production_client
    _as_user(1, "Owner", "Owner")
    owner_created = client.post("/api/production/daily", json=_production_payload(date="2026-06-13"))
    assert owner_created.status_code == 201, owner_created.text

    _as_user(3, "Sub-Owner", "Sub Owner")
    blocked = client.post(
        f"/api/production/daily/{owner_created.json()['production_id']}/reverse",
        json={"reason": "Sub-owner should not reverse owner"},
    )
    assert blocked.status_code == 403

    _as_user(2, "Supervisor", "Supervisor")
    supervisor_created = client.post("/api/production/daily", json=_production_payload(date="2026-06-14"))
    assert supervisor_created.status_code == 201, supervisor_created.text

    _as_user(3, "Sub-Owner", "Sub Owner")
    review = client.get("/api/production/review", params={"date": "2026-06-14"})
    assert review.status_code == 200
    assert review.json()["entries"][0]["allowed_actions"]["can_reverse"] is True
    reversed_response = client.post(
        f"/api/production/daily/{supervisor_created.json()['production_id']}/reverse",
        json={"reason": "Sub-owner correcting supervisor duplicate"},
    )
    assert reversed_response.status_code == 200, reversed_response.text
    assert reversed_response.json()["reversed_by"] == "Sub Owner"


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

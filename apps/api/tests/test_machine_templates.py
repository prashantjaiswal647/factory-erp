from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import get_current_active_user, get_current_user
from db import Base, get_db
from machine_template_verifier import TemplateVerificationResult
from routers import machine_templates
from routers.machine_templates import get_template_verification_runner, router


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def build_client(user, verification_runner=None):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_active_user] = lambda: user
    if verification_runner is not None:
        app.dependency_overrides[get_template_verification_runner] = lambda: verification_runner
    return TestClient(app)


def test_template_requires_approval_before_general_visibility():
    owner = SimpleNamespace(id=1, factory_id=101, role="Owner")
    supervisor = SimpleNamespace(id=2, factory_id=101, role="Supervisor")
    owner_client = build_client(owner, verification_runner=lambda template_id: None)

    payload = {
        "machine_type": "Paper Bag",
        "base_config": {"bag_width_mm": 180, "speed_bags_per_minute": 60},
        "custom_fields": {"Voltage": "220v"},
    }

    submitted_response = owner_client.post("/templates/submit", json=payload)

    assert submitted_response.status_code == 201
    submitted = submitted_response.json()
    assert submitted["status"] == "processing"
    assert submitted["creator_id"] == owner.id

    app = owner_client.app
    app.dependency_overrides[get_current_user] = lambda: supervisor
    app.dependency_overrides[get_current_active_user] = lambda: supervisor
    supervisor_client = TestClient(app)

    general_list_response = supervisor_client.get("/templates")

    assert general_list_response.status_code == 200
    assert general_list_response.json() == []

    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_current_active_user] = lambda: owner
    approve_response = owner_client.patch(f"/admin/templates/{submitted['id']}/approve")

    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    app.dependency_overrides[get_current_user] = lambda: supervisor
    app.dependency_overrides[get_current_active_user] = lambda: supervisor
    approved_list_response = supervisor_client.get("/templates")

    assert approved_list_response.status_code == 200
    visible_templates = approved_list_response.json()
    assert len(visible_templates) == 1
    assert visible_templates[0]["status"] == "approved"
    assert visible_templates[0]["custom_fields"] == {"Voltage": "220v"}


def test_good_template_submission_is_ai_approved(monkeypatch):
    owner = SimpleNamespace(id=1, factory_id=101, role="Owner")

    def approve_verifier(db, template):
        return TemplateVerificationResult(
            confidence_score=0.97,
            decision="approved",
            reasons=["Template is complete, unique, and logically consistent."],
        )

    monkeypatch.setattr(machine_templates, "verify_machine_template_submission", approve_verifier)

    client = build_client(
        owner,
        verification_runner=lambda template_id: machine_templates.run_ai_template_verification(
            template_id,
            session_factory=TestingSessionLocal,
        ),
    )

    response = client.post(
        "/templates/submit",
        json={
            "machine_type": "Paper Cup",
            "base_config": {"cup_size_ml": 250, "speed_cups_per_minute": 45},
            "custom_fields": {"Voltage": "220v"},
        },
    )

    assert response.status_code == 201
    template_id = response.json()["id"]

    status_response = client.get(f"/templates/{template_id}")

    assert status_response.status_code == 200
    template = status_response.json()
    assert template["status"] == "approved"
    assert template["ai_confidence"] == 0.97


def test_bad_template_submission_goes_to_pending_review(monkeypatch):
    owner = SimpleNamespace(id=1, factory_id=101, role="Owner")

    def reject_verifier(db, template):
        return TemplateVerificationResult(
            confidence_score=0.42,
            decision="pending",
            reasons=["Template has empty fields and questionable machine logic."],
        )

    monkeypatch.setattr(machine_templates, "verify_machine_template_submission", reject_verifier)

    client = build_client(
        owner,
        verification_runner=lambda template_id: machine_templates.run_ai_template_verification(
            template_id,
            session_factory=TestingSessionLocal,
        ),
    )

    response = client.post(
        "/templates/submit",
        json={
            "machine_type": "X",
            "base_config": {},
            "custom_fields": {"Voltage": ""},
        },
    )

    assert response.status_code == 201
    template_id = response.json()["id"]

    status_response = client.get(f"/templates/{template_id}")

    assert status_response.status_code == 200
    template = status_response.json()
    assert template["status"] == "pending"
    assert template["ai_confidence"] == 0.42
    assert "questionable machine logic" in template["ai_review"]["reasons"][0]

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from routers.machine_onboarding import get_current_user, get_db, router


def ensure_testclient_compatibility():
    import inspect
    import httpx

    if "app" in inspect.signature(httpx.Client.__init__).parameters:
        return

    original_init = httpx.Client.__init__
    if getattr(original_init, "_munshi_accepts_app_kwarg", False):
        return

    def patched_init(self, *args, app=None, **kwargs):
        return original_init(self, *args, **kwargs)

    patched_init._munshi_accepts_app_kwarg = True
    httpx.Client.__init__ = patched_init


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


def override_get_current_user():
    return SimpleNamespace(id=1, factory_id=101, role="Owner")


def build_client():
    ensure_testclient_compatibility()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    return TestClient(app)


def test_machine_onboarding_saves_and_filters_dynamic_json_fields():
    client = build_client()
    payload = {
        "machine_type": "Paper Cup",
        "base_config": {
            "cup_size_ml": 250,
            "bottom_size_mm": 52,
            "speed_cups_per_minute": 45,
        },
        "custom_fields": {
            "Voltage": "220v",
            "PLC Model": "Delta DVP",
        },
    }

    create_response = client.post("/api/machine-onboardings", json=payload)

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["machine_type"] == "Paper Cup"
    assert created["base_config"] == payload["base_config"]
    assert created["custom_fields"] == payload["custom_fields"]

    list_response = client.get(
        "/api/machine-onboardings",
        params={"custom_field_key": "Voltage", "custom_field_value": "220v"},
    )

    assert list_response.status_code == 200
    records = list_response.json()
    assert len(records) == 1
    assert records[0]["custom_fields"]["PLC Model"] == "Delta DVP"

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest
from datetime import datetime, timezone, timedelta

from db import Base, get_db
from models import User, Factory, ActivityLog
from auth import get_current_user
from main import app as main_app


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

mock_user = None

def override_get_current_user():
    global mock_user
    return mock_user

@pytest.fixture(autouse=True)
def setup_db_and_overrides():
    main_app.dependency_overrides[get_db] = override_get_db
    main_app.dependency_overrides[get_current_user] = override_get_current_user
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    for dep in [get_db, get_current_user]:
        main_app.dependency_overrides.pop(dep, None)

def test_operations_telemetry_pipeline():
    global mock_user
    db = TestingSessionLocal()

    # Create mock Factory and Users
    factory = Factory(id=1, name="Cosmic Yog Factory")
    db.add(factory)
    db.flush()

    owner_user = User(id=1, factory_id=1, username="owner@cosmicyog.com", role="Owner", full_name="Owner Admin", password_hash="mock_secure_hash")
    supervisor_user = User(id=2, factory_id=1, username="supervisor@cosmicyog.com", role="Supervisor", full_name="Supervisor Node", password_hash="mock_secure_hash")
    db.add(owner_user)
    db.add(supervisor_user)
    db.commit()

    ensure_testclient_compatibility()
    client = TestClient(main_app)

    # 1. Test Mock Action 2: Authenticate a Supervisor and call v1 daily-sequence (Assert HTTP 403 Forbidden)
    mock_user = supervisor_user
    response = client.get("/api/v1/operations/daily-sequence")
    assert response.status_code == 403
    assert "restricted" in response.json()["detail"].lower()

    # 2. Test Mock Action 1: Authenticate an Owner credentials token session, add mock ActivityLog telemetry, assert
    mock_user = owner_user
    
    activity = ActivityLog(
        factory_id=1,
        event_type="production",
        description="Owner configured machine setup parameters.",
        short_statement="👤 Owner added/modified details for Worker profile.",
        user_role="owner",
        user_id=1
    )
    db.add(activity)
    db.commit()

    # Hit daily-sequence as Owner
    response = client.get("/api/v1/operations/daily-sequence")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["user_role"] == "owner"
    assert "Worker profile" in data[0]["short_statement"]
    assert data[0]["relative_day"] in ["Today", "Yesterday"]



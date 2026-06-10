import time
import pytest
from types import SimpleNamespace
from fastapi import FastAPI, Depends, Request, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from pathlib import Path
import json

from db import Base, get_db
from models import SuperAdminAuditLog
from main import app as main_app, _rate_limit_store
from routers.super_admin import (
    load_mfa_settings,
    save_mfa_settings,
    verify_totp,
    generate_base32_secret,
    _super_admin_failed_attempts,
    _super_admin_lockouts,
    MFA_FILE
)
from auth import pwd_context

# Test DB configuration
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

@pytest.fixture(autouse=True)
def setup_super_admin_env_and_db(monkeypatch):
    ensure_testclient_compatibility()
    monkeypatch.setenv("SUPER_ADMIN_EMAIL", "admin@munshiai.com")
    monkeypatch.setenv("SUPER_ADMIN_PASSWORD_HASH", pwd_context.hash("super_secure_pass_123"))
    monkeypatch.setenv("SUPER_ADMIN_JWT_SECRET", "super_admin_secret_key_987654321")
    
    # Force SQLite test db
    main_app.dependency_overrides[get_db] = override_get_db
    
    # Initialize DB
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # Reset lockouts, rate limits, and MFA file
    _super_admin_failed_attempts.clear()
    _super_admin_lockouts.clear()
    _rate_limit_store.clear()
    if MFA_FILE.exists():
        MFA_FILE.unlink()
        
    yield
    
    # Cleanup after test
    if MFA_FILE.exists():
        MFA_FILE.unlink()
    _super_admin_failed_attempts.clear()
    _super_admin_lockouts.clear()
    _rate_limit_store.clear()

def test_super_admin_login_rate_limiting():
    """Verify that the sixth request in a minute triggers 429 rate limiting."""
    client = TestClient(main_app)
    payload = {"email": "admin@munshiai.com", "password": "wrong_password"}
    
    for _ in range(5):
        response = client.post("/api/super-admin/login", json=payload)
        assert response.status_code in (401, 429)
    
    response = client.post("/api/super-admin/login", json=payload)
    assert response.status_code == 429
    assert "too many login attempts" in response.json()["detail"].lower()

def test_super_admin_lockout_after_failures(monkeypatch):
    """Verify that 5 failed attempts from an IP locks it out for 15 minutes."""
    client = TestClient(main_app)
    payload = {"email": "admin@munshiai.com", "password": "wrong_password"}
    
    # Send 5 failed attempts
    for _ in range(5):
        response = client.post("/api/super-admin/login", json=payload)
        assert response.status_code in (401, 429)

    _rate_limit_store.clear()

    # 6th attempt must trigger 429 lockout
    response = client.post("/api/super-admin/login", json=payload)
    assert response.status_code == 429
    assert "locked out" in response.json()["detail"].lower()

def test_super_admin_login_success_and_audit_logging():
    """Verify successful login generates token and creates audit logs."""
    client = TestClient(main_app)
    db = TestingSessionLocal()
    
    payload = {"email": "admin@munshiai.com", "password": "super_secure_pass_123"}
    response = client.post("/api/super-admin/login", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["access_token"] != ""
    assert res_data["email"] == "admin@munshiai.com"
    assert res_data["mfa_required"] is False
    
    # Verify audit logs in database
    audit_logs = db.query(SuperAdminAuditLog).filter(SuperAdminAuditLog.action_type == "login_success").all()
    assert len(audit_logs) == 1
    assert audit_logs[0].admin_email == "admin@munshiai.com"
    db.close()

def test_optional_mfa_setup_enable_and_verify_flow():
    """Verify setup generates secret, enable validates TOTP, and login enforces it."""
    client = TestClient(main_app)
    
    # 1. Login first to get Super Admin JWT
    login_res = client.post("/api/super-admin/login", json={"email": "admin@munshiai.com", "password": "super_secure_pass_123"})
    jwt_token = login_res.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {jwt_token}"}
    
    # 2. Initiate MFA setup
    setup_res = client.post("/api/super-admin/mfa/setup", headers=auth_headers)
    assert setup_res.status_code == 200
    setup_data = setup_res.json()
    secret = setup_data["secret"]
    uri = setup_data["provisioning_uri"]
    assert len(secret) == 32
    assert "otpauth://totp/" in uri
    
    # Verify settings has pending secret
    settings = load_mfa_settings()
    assert settings["pending_secret"] == secret
    assert settings["mfa_enabled"] is False
    
    # 3. Enable MFA with incorrect code -> 400
    enable_res = client.post("/api/super-admin/mfa/enable", json={"code": "000000"}, headers=auth_headers)
    assert enable_res.status_code == 400
    
    # Generate valid code using the pure Python TOTP generator
    from routers.super_admin import verify_totp
    import hmac, hashlib, struct
    # We can calculate intervals directly to fetch a valid code
    intervals = int(time.time() / 30)
    msg = struct.pack(">Q", intervals)
    import base64
    key = base64.b32decode(secret, casefold=True)
    hs = hmac.new(key, msg, hashlib.sha1).digest()
    offset = hs[-1] & 0x0f
    binary = struct.unpack(">I", hs[offset:offset+4])[0] & 0x7fffffff
    valid_code = str(binary % 1000000).zfill(6)
    
    # 4. Enable with correct code -> 200
    enable_res = client.post("/api/super-admin/mfa/enable", json={"code": valid_code}, headers=auth_headers)
    assert enable_res.status_code == 200
    
    # Verify settings says MFA is enabled
    settings = load_mfa_settings()
    assert settings["mfa_enabled"] is True
    assert settings["mfa_secret"] == secret
    
    # 5. Subsequent login with email/password only -> Returns mfa_required=True and no token
    login_res = client.post("/api/super-admin/login", json={"email": "admin@munshiai.com", "password": "super_secure_pass_123"})
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert login_data["mfa_required"] is True
    assert login_data["access_token"] == ""
    
    # 6. Login with correct password and correct totp_code -> Returns token
    intervals = int(time.time() / 30)
    msg = struct.pack(">Q", intervals)
    hs = hmac.new(key, msg, hashlib.sha1).digest()
    offset = hs[-1] & 0x0f
    binary = struct.unpack(">I", hs[offset:offset+4])[0] & 0x7fffffff
    current_code = str(binary % 1000000).zfill(6)
    
    login_res = client.post(
        "/api/super-admin/login",
        json={"email": "admin@munshiai.com", "password": "super_secure_pass_123", "totp_code": current_code}
    )
    assert login_res.status_code == 200
    assert login_res.json()["access_token"] != ""
    
    # 7. Disable MFA with correct TOTP code -> 200
    intervals = int(time.time() / 30)
    msg = struct.pack(">Q", intervals)
    hs = hmac.new(key, msg, hashlib.sha1).digest()
    offset = hs[-1] & 0x0f
    binary = struct.unpack(">I", hs[offset:offset+4])[0] & 0x7fffffff
    current_code = str(binary % 1000000).zfill(6)
    
    disable_res = client.post("/api/super-admin/mfa/disable", json={"code": current_code}, headers=auth_headers)
    assert disable_res.status_code == 200
    
    # Verify settings has MFA disabled
    settings = load_mfa_settings()
    assert settings["mfa_enabled"] is False
    assert settings["mfa_secret"] is None

def test_super_admin_change_password_flow():
    """Verify changing password updates settings hash and is verified upon subsequent logins."""
    client = TestClient(main_app)
    
    # Login first
    login_res = client.post("/api/super-admin/login", json={"email": "admin@munshiai.com", "password": "super_secure_pass_123"})
    jwt_token = login_res.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {jwt_token}"}
    
    # 1. Change password with incorrect old password -> 400
    change_res = client.post(
        "/api/super-admin/change-password",
        json={"old_password": "wrong_old_password", "new_password": "new_awesome_password_123"},
        headers=auth_headers
    )
    assert change_res.status_code == 400
    
    # 2. Change password with correct old password -> 200
    change_res = client.post(
        "/api/super-admin/change-password",
        json={"old_password": "super_secure_pass_123", "new_password": "new_awesome_password_123"},
        headers=auth_headers
    )
    assert change_res.status_code == 200
    
    # 3. Try to login with old password -> 401
    login_res = client.post("/api/super-admin/login", json={"email": "admin@munshiai.com", "password": "super_secure_pass_123"})
    assert login_res.status_code == 401
    
    # 4. Try to login with new password -> 200
    login_res = client.post("/api/super-admin/login", json={"email": "admin@munshiai.com", "password": "new_awesome_password_123"})
    assert login_res.status_code == 200
    assert login_res.json()["access_token"] != ""

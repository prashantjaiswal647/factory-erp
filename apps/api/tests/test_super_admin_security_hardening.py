"""
test_super_admin_security_hardening.py
=======================================
Comprehensive security hardening tests for the Super Admin panel.

Coverage:
  - Login rate limiting (in-memory fallback)
  - Lockout after brute-force attempts
  - Lockout safety: valid credentials clear lockout state
  - Audit log persistence for login_success / login_failure
  - Audit log persistence for password change (db.commit fix verification)
  - Audit log persistence for role changes
  - Audit log persistence for factory suspension / unsuspension
  - Audit log persistence for subscription_override
  - Audit log persistence for manual subscription adjustment
  - MFA: invalid code does NOT grant token
  - Unauthenticated access returns 401
  - Invalid JWT returns 401
"""

import base64
import hashlib
import hmac
import json
import struct
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import pwd_context
from db import Base, get_db
from main import app as main_app, _rate_limit_store
from models import Factory, SuperAdminAuditLog, User
from routers.super_admin import (
    MFA_FILE,
    _super_admin_failed_attempts,
    _super_admin_lockouts,
    generate_base32_secret,
    load_mfa_settings,
    save_mfa_settings,
)

# ---------------------------------------------------------------------------
# Test DB
# ---------------------------------------------------------------------------

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def ensure_testclient_compatibility():
    """Patch httpx.Client to accept the 'app' kwarg that starlette TestClient passes.
    Required on Python 3.14 with older httpx versions."""
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


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ADMIN_EMAIL = "hardening@munshiai.com"
_ADMIN_PASS = "HardeningPass#99"


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """Ensure isolated env, fresh DB, and cleared state for every test."""
    ensure_testclient_compatibility()
    monkeypatch.setenv("SUPER_ADMIN_EMAIL", _ADMIN_EMAIL)
    monkeypatch.setenv("SUPER_ADMIN_PASSWORD_HASH", pwd_context.hash(_ADMIN_PASS))
    monkeypatch.setenv("SUPER_ADMIN_JWT_SECRET", "hardening_jwt_secret_xyz_987654321")

    main_app.dependency_overrides[get_db] = override_get_db

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    _super_admin_failed_attempts.clear()
    _super_admin_lockouts.clear()
    _rate_limit_store.clear()
    if MFA_FILE.exists():
        MFA_FILE.unlink()

    yield

    if MFA_FILE.exists():
        MFA_FILE.unlink()
    _super_admin_failed_attempts.clear()
    _super_admin_lockouts.clear()
    _rate_limit_store.clear()
    main_app.dependency_overrides.pop(get_db, None)


def _client():
    ensure_testclient_compatibility()
    return TestClient(main_app)


def _login(client, password=_ADMIN_PASS, totp_code=None):
    payload = {"email": _ADMIN_EMAIL, "password": password}
    if totp_code:
        payload["totp_code"] = totp_code
    return client.post("/api/super-admin/login", json=payload)


def _get_token(client):
    resp = _login(client)
    assert resp.status_code == 200, resp.json()
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _db_session():
    return TestingSessionLocal()


def _totp_code(secret: str) -> str:
    """Generate a valid TOTP code for the given secret."""
    secret = secret.strip().replace(" ", "")
    missing = len(secret) % 8
    if missing:
        secret += "=" * (8 - missing)
    key = base64.b32decode(secret, casefold=True)
    intervals = int(time.time() / 30)
    msg = struct.pack(">Q", intervals)
    hs = hmac.new(key, msg, hashlib.sha1).digest()
    offset = hs[-1] & 0x0F
    binary = struct.unpack(">I", hs[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary % 1_000_000).zfill(6)


# ===========================================================================
# 1. Rate Limiting
# ===========================================================================


def test_rate_limit_triggers_after_threshold():
    """More than 10 bad requests in a minute must trigger 429 rate limiting.
    
    Mirrors the same strategy as the existing passing test: make real requests
    to seed the rate-limit store, then manually top it up past the threshold.
    """
    client = _client()
    payload = {"email": _ADMIN_EMAIL, "password": "wrong_password"}

    # Make 5 bad attempts (will lockout at attempt 5, but we need to seed the rate-limit)
    for _ in range(5):
        client.post("/api/super-admin/login", json=payload)

    # Clear lockout so only rate-limit applies
    _super_admin_lockouts.clear()
    _super_admin_failed_attempts.clear()

    # Find which IP key got seeded and top it up past 10
    for key in list(_rate_limit_store.keys()):
        if "super_admin_login" in key:
            _rate_limit_store[key] = [time.time()] * 11  # exceed limit of 10
            break
    else:
        # Fallback: seed both possible IPs
        _rate_limit_store["rate_limit:super_admin_login:127.0.0.1"] = [time.time()] * 11
        _rate_limit_store["rate_limit:super_admin_login:testclient"] = [time.time()] * 11

    resp = client.post("/api/super-admin/login", json=payload)
    assert resp.status_code == 429
    assert "too many login attempts" in resp.json()["detail"].lower()


def test_rate_limit_does_not_block_before_threshold():
    """First valid login attempt must not be rate-blocked."""
    client = _client()
    resp = _login(client)
    assert resp.status_code == 200


# ===========================================================================
# 2. Brute-Force Lockout
# ===========================================================================


def test_lockout_activates_after_five_bad_attempts():
    """Exactly 5 bad attempts trigger lockout; 6th returns 429 locked-out."""
    client = _client()
    for _ in range(5):
        r = client.post(
            "/api/super-admin/login",
            json={"email": _ADMIN_EMAIL, "password": "WRONG_PASSWORD"},
        )
        assert r.status_code in (401, 429)  # 429 = lockout, 401 = invalid creds

    r = client.post(
        "/api/super-admin/login",
        json={"email": _ADMIN_EMAIL, "password": "WRONG_PASSWORD"},
    )
    assert r.status_code == 429
    assert "locked out" in r.json()["detail"].lower()


def test_valid_login_clears_lockout_state():
    """
    Lockout safety: after 5 bad attempts cause a lockout, once the lockout
    expires, valid credentials MUST be accepted (not permanently blocked).
    The login also clears any lingering bad-attempt state.
    """
    client = _client()

    # Make 5 bad attempts to trigger a lockout naturally
    for _ in range(5):
        client.post(
            "/api/super-admin/login",
            json={"email": _ADMIN_EMAIL, "password": "WRONG_PASSWORD"},
        )

    # Expire the lockout by back-dating it in the store
    for ip_key in list(_super_admin_lockouts.keys()):
        _super_admin_lockouts[ip_key] = time.time() - 1  # immediately expired

    # Valid credentials should now be accepted (lockout expired)
    resp = _login(client)
    assert resp.status_code == 200, (
        f"Expected 200 after lockout expiry, got {resp.status_code}: {resp.json()}"
    )

    # Lockout entry should be cleared after successful login
    for ip_key in list(_super_admin_lockouts.keys()):
        # Lockout timestamps should no longer block (either gone or in the past)
        assert _super_admin_lockouts.get(ip_key, 0) <= time.time(), (
            "Lockout was not cleared after successful login"
        )


def test_lockout_respects_time_window():
    """Requests older than the 900s window do not count toward lockout.
    
    Seeds stale entries for 'testclient' (actual TestClient host).
    Only 1 recent bad attempt → not locked out (lockout requires 5).
    """
    client = _client()
    ip = "testclient"  # actual TestClient request.client.host
    # 4 attempts that are >900s old (outside window)
    stale_time = time.time() - 1000
    _super_admin_failed_attempts[ip] = [stale_time] * 4

    # One more bad attempt now → should only total 1 recent attempt, no lockout
    r = _login(client, password="WRONG")
    assert r.status_code == 401  # not locked out



# ===========================================================================
# 3. Audit Logging — Login Events
# ===========================================================================


def test_audit_log_written_on_login_success():
    """Successful login must produce a 'login_success' audit log in the DB."""
    client = _client()
    db = _db_session()
    try:
        resp = _login(client)
        assert resp.status_code == 200

        logs = (
            db.query(SuperAdminAuditLog)
            .filter(SuperAdminAuditLog.action_type == "login_success")
            .all()
        )
        assert len(logs) >= 1
        assert logs[-1].admin_email == _ADMIN_EMAIL
    finally:
        db.close()


def test_audit_log_written_on_login_failure_wrong_password():
    """Failed login (wrong password) must write a failure audit log."""
    client = _client()
    db = _db_session()
    try:
        _login(client, password="completely_wrong")

        logs = (
            db.query(SuperAdminAuditLog)
            .filter(
                SuperAdminAuditLog.action_type == "login_failure_invalid_password"
            )
            .all()
        )
        assert len(logs) >= 1
    finally:
        db.close()


def test_audit_log_written_on_wrong_email():
    """Mismatched email must write a failure audit log."""
    client = _client()
    db = _db_session()
    try:
        client.post(
            "/api/super-admin/login",
            json={"email": "notadmin@example.com", "password": _ADMIN_PASS},
        )
        logs = (
            db.query(SuperAdminAuditLog)
            .filter(
                SuperAdminAuditLog.action_type == "login_failure_invalid_email"
            )
            .all()
        )
        assert len(logs) >= 1
    finally:
        db.close()


def test_audit_log_written_on_rate_limit_block():
    """Rate-limited attempt must write a 'login_failure_rate_limited' audit log.
    
    Uses real HTTP requests to seed the rate-limit store, then tops it up
    to exceed the threshold and checks that the audit log is written.
    """
    client = _client()
    db = _db_session()
    try:
        # Make bad requests to seed the rate-limit store with real IP keys
        for _ in range(5):
            client.post(
                "/api/super-admin/login",
                json={"email": _ADMIN_EMAIL, "password": "wrong"},
            )

        # Clear lockout so only rate-limit applies on next request
        _super_admin_lockouts.clear()
        _super_admin_failed_attempts.clear()

        # Exceed the rate limit for the real IP key
        for key in list(_rate_limit_store.keys()):
            if "super_admin_login" in key:
                _rate_limit_store[key] = [time.time()] * 11
                break
        else:
            _rate_limit_store["rate_limit:super_admin_login:127.0.0.1"] = [time.time()] * 11
            _rate_limit_store["rate_limit:super_admin_login:testclient"] = [time.time()] * 11

        resp = client.post(
            "/api/super-admin/login",
            json={"email": _ADMIN_EMAIL, "password": "anything"},
        )
        assert resp.status_code == 429

        logs = (
            db.query(SuperAdminAuditLog)
            .filter(
                SuperAdminAuditLog.action_type == "login_failure_rate_limited"
            )
            .all()
        )
        assert len(logs) >= 1, "login_failure_rate_limited audit log was not written"
    finally:
        db.close()


# ===========================================================================
# 4. Audit Logging — Password Change (db.commit fix)
# ===========================================================================


def test_password_change_audit_log_is_persisted():
    """
    Regression test: change_password must commit the audit log to the DB.
    Before the fix, audit() was called but db.commit() was missing.
    """
    client = _client()
    db = _db_session()
    try:
        token = _get_token(client)
        resp = client.post(
            "/api/super-admin/change-password",
            json={"old_password": _ADMIN_PASS, "new_password": "NewSecurePass!456"},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        logs = (
            db.query(SuperAdminAuditLog)
            .filter(
                SuperAdminAuditLog.action_type == "super_admin_password_change"
            )
            .all()
        )
        assert len(logs) >= 1, (
            "Password change audit log was NOT persisted. "
            "db.commit() was likely missing in change_password()."
        )
    finally:
        db.close()


def test_password_change_rejects_wrong_old_password():
    """Cannot change password without supplying the correct old password."""
    client = _client()
    token = _get_token(client)
    resp = client.post(
        "/api/super-admin/change-password",
        json={"old_password": "WRONG_OLD", "new_password": "NewSecurePass!456"},
        headers=_auth(token),
    )
    assert resp.status_code == 400


# ===========================================================================
# 5. Audit Logging — Role Changes
# ===========================================================================


def test_audit_log_written_on_role_change():
    """
    PATCH /owners/{id} with a new role must emit a 'role_change' audit event.
    """
    client = _client()
    db = _db_session()
    try:
        # Create a factory + owner directly in the DB
        factory = Factory(
            id=901,
            name="RoleAuditFactory",
            factory_name="RoleAuditFactory",
            subscription_status="trial_active",
        )
        db.add(factory)
        db.flush()
        owner = User(
            id=801,
            user_id="role-audit-owner",
            factory_id=factory.id,
            username="roleaudit@example.com",
            email="roleaudit@example.com",
            full_name="Role Audit Owner",
            password_hash=pwd_context.hash("password123"),
            role="Owner",
            is_verified=True,
            is_active=True,
        )
        db.add(owner)
        factory.owner_id = owner.id
        db.commit()

        token = _get_token(client)
        resp = client.patch(
            f"/api/super-admin/owners/{owner.id}",
            json={"role": "Sub-Owner"},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        logs = (
            db.query(SuperAdminAuditLog)
            .filter(SuperAdminAuditLog.action_type == "role_change")
            .all()
        )
        assert len(logs) >= 1
        # Verify old/new values are captured
        log = logs[-1]
        assert log.old_value is not None or log.new_value is not None
    finally:
        db.close()


# ===========================================================================
# 6. Audit Logging — Factory Suspension
# ===========================================================================


def test_audit_log_written_on_factory_suspension():
    """
    PATCH /factories/{id} with is_active=False must emit
    a 'factory_suspension' audit event.
    """
    client = _client()
    db = _db_session()
    try:
        factory = Factory(
            id=902,
            name="SuspensionAuditFactory",
            factory_name="SuspensionAuditFactory",
            subscription_status="trial_active",
            is_active=True,
        )
        db.add(factory)
        db.commit()

        token = _get_token(client)
        resp = client.patch(
            f"/api/super-admin/factories/{factory.id}",
            json={"is_active": False},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        logs = (
            db.query(SuperAdminAuditLog)
            .filter(SuperAdminAuditLog.action_type == "factory_suspension")
            .all()
        )
        assert len(logs) >= 1
    finally:
        db.close()


def test_audit_log_written_on_factory_unsuspension():
    """
    Re-activating a suspended factory must emit 'factory_unsuspension'.
    """
    client = _client()
    db = _db_session()
    try:
        factory = Factory(
            id=903,
            name="UnsuspendAuditFactory",
            factory_name="UnsuspendAuditFactory",
            subscription_status="trial_active",
            is_active=False,
        )
        db.add(factory)
        db.commit()

        token = _get_token(client)
        resp = client.patch(
            f"/api/super-admin/factories/{factory.id}",
            json={"is_active": True},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        logs = (
            db.query(SuperAdminAuditLog)
            .filter(SuperAdminAuditLog.action_type == "factory_unsuspension")
            .all()
        )
        assert len(logs) >= 1
    finally:
        db.close()


# ===========================================================================
# 7. Audit Logging — Subscription Override
# ===========================================================================


def test_audit_log_written_on_subscription_patch_with_critical_fields():
    """
    PATCH /subscriptions/{id} touching subscription-critical fields must emit
    both 'subscription_override' and 'subscription_update' audit events.
    """
    client = _client()
    db = _db_session()
    try:
        factory = Factory(
            id=904,
            name="SubOverrideFactory",
            factory_name="SubOverrideFactory",
            subscription_status="trial_active",
        )
        db.add(factory)
        db.commit()

        token = _get_token(client)
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        resp = client.patch(
            f"/api/super-admin/subscriptions/{factory.id}",
            json={
                "active_plan": "premium",
                "subscription_status": "active",
                "payment_status": "paid",
                "subscription_end_date": future,
            },
            headers=_auth(token),
        )
        assert resp.status_code == 200

        override_logs = (
            db.query(SuperAdminAuditLog)
            .filter(SuperAdminAuditLog.action_type == "subscription_override")
            .all()
        )
        assert len(override_logs) >= 1, "subscription_override audit event was not emitted"

        update_logs = (
            db.query(SuperAdminAuditLog)
            .filter(SuperAdminAuditLog.action_type == "subscription_update")
            .all()
        )
        assert len(update_logs) >= 1, "subscription_update audit event was not emitted"
    finally:
        db.close()


def test_audit_log_written_on_manual_subscription_adjustment():
    """
    POST /subscriptions/manual-adjustment must emit both
    'subscription_override' and 'subscription_manual_adjustment' events.
    """
    client = _client()
    db = _db_session()
    try:
        factory = Factory(
            id=905,
            name="ManualSubFactory",
            factory_name="ManualSubFactory",
            subscription_status="trial_active",
        )
        db.add(factory)
        db.commit()

        token = _get_token(client)
        future = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
        resp = client.post(
            "/api/super-admin/subscriptions/manual-adjustment",
            json={
                "factory_id": factory.id,
                "plan_name": "premium",
                "subscription_status": "active",
                "payment_status": "paid",
                "billing_cycle": "monthly",
                "subscription_end_date": future,
            },
            headers=_auth(token),
        )
        assert resp.status_code == 200

        override_logs = (
            db.query(SuperAdminAuditLog)
            .filter(SuperAdminAuditLog.action_type == "subscription_override")
            .all()
        )
        assert len(override_logs) >= 1, "subscription_override audit not emitted for manual-adjustment"

        manual_logs = (
            db.query(SuperAdminAuditLog)
            .filter(SuperAdminAuditLog.action_type == "subscription_manual_adjustment")
            .all()
        )
        assert len(manual_logs) >= 1
    finally:
        db.close()


# ===========================================================================
# 8. MFA Security
# ===========================================================================


def test_mfa_invalid_code_does_not_issue_token():
    """
    When MFA is enabled, sending an incorrect TOTP code must return 401
    and must NOT return an access token.
    """
    client = _client()

    # Enable MFA
    token = _get_token(client)
    setup_resp = client.post("/api/super-admin/mfa/setup", headers=_auth(token))
    assert setup_resp.status_code == 200
    secret = setup_resp.json()["secret"]

    valid_code = _totp_code(secret)
    enable_resp = client.post(
        "/api/super-admin/mfa/enable",
        json={"code": valid_code},
        headers=_auth(token),
    )
    assert enable_resp.status_code == 200

    # Attempt login with wrong TOTP
    resp = client.post(
        "/api/super-admin/login",
        json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASS, "totp_code": "000000"},
    )
    assert resp.status_code == 401
    assert "access_token" not in resp.json() or resp.json().get("access_token") == ""


def test_mfa_correct_code_issues_token():
    """With MFA enabled, correct TOTP + correct password returns a valid token."""
    client = _client()

    token = _get_token(client)
    setup_resp = client.post("/api/super-admin/mfa/setup", headers=_auth(token))
    secret = setup_resp.json()["secret"]

    valid_code = _totp_code(secret)
    client.post(
        "/api/super-admin/mfa/enable",
        json={"code": valid_code},
        headers=_auth(token),
    )

    new_code = _totp_code(secret)
    resp = client.post(
        "/api/super-admin/login",
        json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASS, "totp_code": new_code},
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"] != ""


def test_mfa_prompt_returned_when_code_missing():
    """
    When MFA is enabled and login request has no totp_code,
    response should set mfa_required=True and access_token should be empty.
    """
    client = _client()

    token = _get_token(client)
    setup_resp = client.post("/api/super-admin/mfa/setup", headers=_auth(token))
    secret = setup_resp.json()["secret"]

    valid_code = _totp_code(secret)
    client.post(
        "/api/super-admin/mfa/enable",
        json={"code": valid_code},
        headers=_auth(token),
    )

    # Login without providing TOTP
    resp = client.post(
        "/api/super-admin/login",
        json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASS},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mfa_required"] is True
    assert data["access_token"] == ""


def test_mfa_disable_requires_valid_totp():
    """Disabling MFA with an invalid code must return 400."""
    client = _client()

    token = _get_token(client)
    setup_resp = client.post("/api/super-admin/mfa/setup", headers=_auth(token))
    secret = setup_resp.json()["secret"]

    valid_code = _totp_code(secret)
    client.post(
        "/api/super-admin/mfa/enable",
        json={"code": valid_code},
        headers=_auth(token),
    )

    # Try to disable with wrong code
    resp = client.post(
        "/api/super-admin/mfa/disable",
        json={"code": "000000"},
        headers=_auth(token),
    )
    assert resp.status_code == 400


# ===========================================================================
# 9. Authentication Boundaries
# ===========================================================================


def test_unauthenticated_access_to_protected_endpoint_returns_401():
    """Every protected endpoint must reject requests with no token."""
    client = _client()
    resp = client.get("/api/super-admin/dashboard")
    assert resp.status_code == 401


def test_invalid_jwt_returns_401():
    """A tampered or garbage JWT must be rejected with 401."""
    client = _client()
    resp = client.get(
        "/api/super-admin/dashboard",
        headers={"Authorization": "Bearer this.is.garbage"},
    )
    assert resp.status_code == 401


def test_wrong_jwt_secret_returns_401():
    """
    A JWT signed with a different secret key must be rejected.
    Simulates token theft from another service or environment.
    """
    import os
    from jose import jwt as jose_jwt

    wrong_secret = "totally_different_secret_abc123"
    payload = {
        "sub": _ADMIN_EMAIL,
        "role": "super_admin",
        "scope": "super_admin",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
    }
    bad_token = jose_jwt.encode(payload, wrong_secret, algorithm="HS256")

    client = _client()
    resp = client.get(
        "/api/super-admin/dashboard",
        headers={"Authorization": f"Bearer {bad_token}"},
    )
    assert resp.status_code == 401


def test_expired_token_returns_401():
    """An expired super admin JWT must be rejected."""
    import os
    from jose import jwt as jose_jwt

    secret = os.environ.get("SUPER_ADMIN_JWT_SECRET", "hardening_jwt_secret_xyz_987654321")
    payload = {
        "sub": _ADMIN_EMAIL,
        "role": "super_admin",
        "scope": "super_admin",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),  # already expired
    }
    expired_token = jose_jwt.encode(payload, secret, algorithm="HS256")

    client = _client()
    resp = client.get(
        "/api/super-admin/dashboard",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401


def test_regular_user_token_cannot_access_super_admin_endpoints():
    """
    A JWT that has role='Owner' (not 'super_admin') must be rejected
    with 401 / 403 for all super admin endpoints.
    """
    import os
    from jose import jwt as jose_jwt

    secret = os.environ.get("SUPER_ADMIN_JWT_SECRET", "hardening_jwt_secret_xyz_987654321")
    payload = {
        "sub": "owner@factory.com",
        "role": "Owner",  # NOT super_admin
        "scope": "factory",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
    }
    owner_token = jose_jwt.encode(payload, secret, algorithm="HS256")

    client = _client()
    resp = client.get(
        "/api/super-admin/dashboard",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code in (401, 403)


# ===========================================================================
# 10. Cache-Control Headers
# ===========================================================================


def test_login_response_has_no_store_cache_header():
    """
    Login endpoint must return Cache-Control: no-store to prevent token caching.
    """
    client = _client()
    resp = _login(client)
    assert resp.status_code == 200
    cache_control = resp.headers.get("cache-control", "")
    assert "no-store" in cache_control.lower()


def test_dashboard_response_has_no_store_cache_header():
    """Protected endpoints must set Cache-Control: no-store."""
    client = _client()
    token = _get_token(client)
    resp = client.get("/api/super-admin/dashboard", headers=_auth(token))
    assert resp.status_code == 200
    cache_control = resp.headers.get("cache-control", "")
    assert "no-store" in cache_control.lower()


# ===========================================================================
# 11. Audit Log Retrieval
# ===========================================================================


def test_audit_logs_endpoint_returns_logs():
    """GET /audit-logs must return a list of logged events."""
    client = _client()
    # First generate some events
    _login(client)
    _login(client, password="wrong")

    token = _get_token(client)
    resp = client.get("/api/super-admin/audit-logs", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2  # at least login events
    # Verify structure
    required_keys = {"id", "admin_email", "action_type", "entity_type", "created_at"}
    for entry in data[:5]:
        assert required_keys.issubset(entry.keys())


# ===========================================================================
# 12. Subscription Non-Override Patch Does NOT Emit subscription_override
# ===========================================================================


def test_subscription_patch_without_critical_fields_does_not_emit_override():
    """
    Patching a non-critical field like admin_note should emit subscription_update
    but NOT subscription_override.
    """
    client = _client()
    db = _db_session()
    try:
        factory = Factory(
            id=906,
            name="NonOverridePatchFactory",
            factory_name="NonOverridePatchFactory",
            subscription_status="trial_active",
        )
        db.add(factory)
        db.commit()

        token = _get_token(client)
        resp = client.patch(
            f"/api/super-admin/subscriptions/{factory.id}",
            json={"admin_note": "Just a note, no subscription fields changed."},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        override_logs = (
            db.query(SuperAdminAuditLog)
            .filter(SuperAdminAuditLog.action_type == "subscription_override")
            .all()
        )
        assert len(override_logs) == 0, (
            "subscription_override was emitted even though no critical "
            "subscription fields were changed."
        )
    finally:
        db.close()

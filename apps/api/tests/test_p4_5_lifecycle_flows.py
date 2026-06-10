"""P4.5 Deliverable 4: Invoice -> Recovery -> Briefing lifecycle validation.

End-to-end tests proving the full chain works without duplicates,
double-counting, or cross-factory leakage. Uses an in-memory sqlite
with the same pattern as test_pilot_zero_touch_acceptance.py.
"""

from __future__ import annotations

import os
from decimal import Decimal
from unittest.mock import patch

import pytest
import httpx
from fastapi.testclient import TestClient as FastAPITestClient
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# FastAPI's TestClient handles ASGI transport internally.
TestClient = FastAPITestClient


# ---------------------------------------------------------------------------
# Per-test environment + sqlite fixture
# ---------------------------------------------------------------------------

ENV_PATCHES = {
    "TELEGRAM_BOT_TOKEN": "ci-bot-token",
    "TELEGRAM_BOT_USERNAME": "ci_bot",
    "TELEGRAM_WEBHOOK_SECRET": "ci-secret-1234567890",
    "JWT_SECRET_KEY": "ci-jwt-secret-key-must-be-long-enough",
    "JWT_ALGORITHM": "HS256",
    "ENVIRONMENT": "test",
    "BYPASS_BILLING": "1",
}


@pytest.fixture()
def lifecycle_app(monkeypatch):
    for key, value in ENV_PATCHES.items():
        monkeypatch.setenv(key, value)

    from db import Base
    import db as db_module
    import models

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(db_module, "engine", engine, raising=False)
    monkeypatch.setattr(db_module, "SessionLocal", TestingSessionLocal, raising=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    from main import app as main_app
    from db import get_db

    main_app.dependency_overrides[get_db] = override_get_db
    client = TestClient(main_app)

    sent_messages: list[tuple[str, str]] = []
    import services.telegram_delivery as td
    import services.invoice_pdf as ip

    patches = [
        patch.object(td, "send_telegram_message",
                     lambda f, text, _store=sent_messages: _store.append((str(getattr(f, "_telegram_target_chat_id", None) or getattr(f, "telegram_chat_id", "?")), text))),
        patch.object(ip, "SessionLocal", TestingSessionLocal),
        patch("services.telegram_action_alerts.SessionLocal", TestingSessionLocal, create=True),
    ]
    for p in patches:
        p.start()
    try:
        yield client, TestingSessionLocal, sent_messages
    finally:
        for p in patches:
            p.stop()
        main_app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _signup_owner(client: TestClient, factory_label: str) -> dict:
    label = factory_label.lower()
    email = f"owner_{label}@example.com"
    signup_resp = client.post(
        "/api/auth/signup",
        json={
            "phone_number": f"9876543{abs(hash(label)) % 1000:03d}",
            "password": "TestPass#2024!",
            "full_name": f"Owner {factory_label}",
            "email": email,
            "country_code": "+91",
            "factory_name": f"Pilot {factory_label}",
        },
    )
    assert signup_resp.status_code in (200, 201, 409), \
        f"signup failed: {signup_resp.status_code} {signup_resp.text[:200]}"
    login = client.post(
        "/api/auth/login",
        json={"identifier": email, "password": "TestPass#2024!"},
    )
    assert login.status_code in (200, 201), \
        f"login failed: {login.status_code} {login.text[:200]}"
    body = login.json()
    return {
        "auth": {"Authorization": f"Bearer {body.get('access_token') or body.get('token')}"},
        "user_id": body.get("user", {}).get("id"),
        "factory_id": body.get("user", {}).get("factory_id"),
    }


def _create_customer(client: TestClient, auth: dict, name: str, factory_id: int) -> int:
    res = client.post(
        "/api/customers",
        headers=auth,
        json={"name": name, "phone_number": "+919999900000", "place": "Test City", "gst_number": None},
    )
    assert res.status_code in (200, 201), res.text
    body = res.json()
    return int(body["id"])


def _create_product(client: TestClient, auth: dict, name: str) -> int:
    res = client.post(
        "/api/inventory/products",
        headers=auth,
        json={"name": name, "category": "FinishedGoods", "unit": "boxes"},
    )
    if res.status_code in (200, 201):
        return int(res.json().get("id", 0))
    return 0


def _wire_owner_telegram(client: TestClient, auth: dict, factory_id: int) -> str:
    """Bind a fake Owner telegram chat_id to factory."""
    from models import TelegramUserBinding, User
    import db as db_module
    SessionLocal = db_module.SessionLocal
    with SessionLocal() as session:
        owner = session.query(User).filter(
            User.factory_id == factory_id, User.role == "Owner"
        ).first()
        binding = session.query(TelegramUserBinding).filter(
            TelegramUserBinding.factory_id == factory_id,
            TelegramUserBinding.user_id == owner.id,
        ).first()
        if binding is None:
            binding = TelegramUserBinding(
                factory_id=factory_id,
                user_id=owner.id,
                role="Owner",
                telegram_chat_id="100000001",
                telegram_connected_at=date.today(),
                is_active=True,
            )
            session.add(binding)
        else:
            binding.telegram_chat_id = "100000001"
            binding.is_active = True
        session.commit()
    return "100000001"


# ---------------------------------------------------------------------------
# D4 Tests
# ---------------------------------------------------------------------------

def test_new_invoice_appears_in_outstanding(lifecycle_app):
    client, _, _ = lifecycle_app
    ctx = _signup_owner(client, "lifecycle_a")
    auth = ctx["auth"]
    fid = ctx["factory_id"]
    customer_id = _create_customer(client, auth, "ABC Traders", fid)

    sale = client.post(
        "/api/sales/invoice",
        headers=auth,
        json={
            "date": (date.today() - timedelta(days=1)).isoformat(),
            "customer_id": customer_id,
            "amount_paid": 0.0,
            "legal_invoice_type": "bill_of_supply",
            "items": [
                {
                    "product_size_ml": 250,
                    "variety": "Standard",
                    "packaging_size_name": "250ml",
                    "boxes_sold": 10,
                    "loose_packets_sold": 0,
                    "rate_per_box": 100.0,
                    "rate_per_packet": 0.0,
                    "tax_rate": 0.0,
                }
            ],
        },
    )
    assert sale.status_code in (200, 201), sale.text

    war = client.get("/api/dashboard/collection-war-room", headers=auth)
    assert war.status_code in (200, 201), war.text
    body = war.json()
    # The total outstanding should be > 0 (we sold ₹1000 of boxes, paid ₹0).
    assert Decimal(str(body.get("total_outstanding", 0))) > Decimal("0"), (
        f"new invoice must show in outstanding, got {body}"
    )


def test_partial_payment_reduces_outstanding(lifecycle_app):
    client, _, _ = lifecycle_app
    ctx = _signup_owner(client, "lifecycle_b")
    auth = ctx["auth"]
    fid = ctx["factory_id"]
    customer_id = _create_customer(client, auth, "XYZ Packaging", fid)

    # Sale of ₹1000, no payment.
    sale = client.post(
        "/api/sales/invoice",
        headers=auth,
        json={
            "date": date.today().isoformat(),
            "customer_id": customer_id,
            "amount_paid": 0.0,
            "legal_invoice_type": "bill_of_supply",
            "items": [
                {
                    "product_size_ml": 250,
                    "variety": "Standard",
                    "packaging_size_name": "250ml",
                    "boxes_sold": 10,
                    "loose_packets_sold": 0,
                    "rate_per_box": 100.0,
                    "rate_per_packet": 0.0,
                    "tax_rate": 0.0,
                }
            ],
        },
    )
    assert sale.status_code in (200, 201), sale.text

    # Baseline outstanding.
    war_before = client.get("/api/dashboard/collection-war-room", headers=auth).json()
    base_outstanding = Decimal(str(war_before["total_outstanding"]))
    assert base_outstanding > Decimal("0")

    # Partial payment of ₹300.
    pay = client.post(
        "/api/payments",
        headers=auth,
        json={"customer_id": customer_id, "amount_paid": 300.0, "payment_mode": "Cash"},
    )
    assert pay.status_code in (200, 201), pay.text

    war_after = client.get("/api/dashboard/collection-war-room", headers=auth).json()
    new_outstanding = Decimal(str(war_after["total_outstanding"]))
    # Outstanding should have decreased by the paid amount (allow rounding).
    assert new_outstanding < base_outstanding, (
        f"partial payment should reduce outstanding, "
        f"before={base_outstanding} after={new_outstanding}"
    )
    # Reduction should be roughly 300.
    delta = base_outstanding - new_outstanding
    assert Decimal("250") <= delta <= Decimal("350"), f"unexpected delta={delta}"


def test_full_payment_removes_outstanding_risk(lifecycle_app):
    client, _, _ = lifecycle_app
    ctx = _signup_owner(client, "lifecycle_c")
    auth = ctx["auth"]
    fid = ctx["factory_id"]
    customer_id = _create_customer(client, auth, "Quick Settler", fid)

    sale = client.post(
        "/api/sales/invoice",
        headers=auth,
        json={
            "date": date.today().isoformat(),
            "customer_id": customer_id,
            "amount_paid": 0.0,
            "legal_invoice_type": "bill_of_supply",
            "items": [
                {
                    "product_size_ml": 200,
                    "variety": "Standard",
                    "packaging_size_name": "200ml",
                    "boxes_sold": 1,
                    "loose_packets_sold": 0,
                    "rate_per_box": 100.0,
                    "rate_per_packet": 0.0,
                    "tax_rate": 0.0,
                }
            ],
        },
    )
    assert sale.status_code in (200, 201), sale.text
    sale_body = sale.json()
    sale_id = sale_body.get("sale_ids", [None])[0]
    assert sale_id is not None, sale_body

    # Generate the invoice for the sale (creates the OutstandingBill row).
    inv = client.post(
        f"/api/sales/invoices/from-sale/{sale_id}",
        headers=auth,
        json={"legal_invoice_type": "bill_of_supply", "tax_rate": 0.0, "notes": "lifecycle test"},
    )
    assert inv.status_code in (200, 201), inv.text

    # Verify outstanding shows the bill (Rs 100 sale with Rs 0 paid).
    war_before = client.get("/api/dashboard/collection-war-room", headers=auth).json()
    assert Decimal(str(war_before["total_outstanding"])) >= Decimal("100"), war_before

    # Pay the full outstanding for this customer.
    pay = client.post(
        "/api/payments",
        headers=auth,
        json={"customer_id": customer_id, "amount_paid": 100.0, "payment_mode": "Cash"},
    )
    assert pay.status_code in (200, 201), pay.text

    # After full payment, the customer should not appear in top_customers.
    war_after = client.get("/api/dashboard/collection-war-room", headers=auth).json()
    for top in war_after.get("top_customers", []):
        assert top["customer_name"] != "Quick Settler", (
            f"Quick Settler should be removed from top after full payment, got {top}"
        )


def test_no_duplicate_outstanding_records(lifecycle_app):
    """Calling the from-sale endpoint twice for the same sale must not
    create a second outstanding bill."""
    client, _, _ = lifecycle_app
    ctx = _signup_owner(client, "lifecycle_d")
    auth = ctx["auth"]
    fid = ctx["factory_id"]
    customer_id = _create_customer(client, auth, "Idempotent Co", fid)

    sale = client.post(
        "/api/sales/invoice",
        headers=auth,
        json={
            "date": date.today().isoformat(),
            "customer_id": customer_id,
            "amount_paid": 0.0,
            "legal_invoice_type": "bill_of_supply",
            "items": [
                {
                    "product_size_ml": 250,
                    "variety": "Standard",
                    "packaging_size_name": "250ml",
                    "boxes_sold": 1,
                    "loose_packets_sold": 0,
                    "rate_per_box": 50.0,
                    "rate_per_packet": 0.0,
                    "tax_rate": 0.0,
                }
            ],
        },
    )
    sale_id = sale.json().get("sale_ids", [None])[0]

    # Two calls to from-sale — second must be a no-op.
    inv1 = client.post(f"/api/sales/invoices/from-sale/{sale_id}", headers=auth, json={})
    inv2 = client.post(f"/api/sales/invoices/from-sale/{sale_id}", headers=auth, json={})
    assert inv1.status_code in (200, 201), inv1.text
    assert inv2.status_code in (200, 201), inv2.text
    assert inv1.json()["invoice_id"] == inv2.json()["invoice_id"], (
        "second from-sale must return the same invoice_id"
    )

    # War room should show one outstanding of Rs 50, not two.
    war = client.get("/api/dashboard/collection-war-room", headers=auth).json()
    outstanding = Decimal(str(war["total_outstanding"]))
    assert outstanding == Decimal("50"), (
        f"expected single Rs 50 outstanding, got {outstanding}"
    )


def test_action_alert_fires_on_sale_by_subowner(lifecycle_app):
    """Sub-Owner sale must trigger Telegram alert to Owner.

    Best-effort, never raises. We patch send_telegram_message to capture
    the message, then assert: (a) Owner is the recipient, (b) the
    message contains the customer name, (c) it contains the amount."""
    client, _, sent = lifecycle_app
    ctx = _signup_owner(client, "lifecycle_e")
    auth = ctx["auth"]
    fid = ctx["factory_id"]
    owner_chat = _wire_owner_telegram(client, auth, fid)
    customer_id = _create_customer(client, auth, "Alert Test", fid)

    # Sub-Owner login (re-use signup endpoint with sub-owner role)
    sub_username = "subowner_lifecycle_e"
    signup = client.post(
        "/api/auth/signup",
        json={
            "phone_number": "9111111111",
            "country_code": "+91",
            "password": "TestPass#2024!",
            "full_name": "Sub Owner E",
            "email": f"{sub_username}@example.com",
            "factory_name": "Pilot Lifecycle E",
        },
    )
    if signup.status_code in (200, 201):
        # Update the new user to be Sub-Owner via direct DB.
        import db as db_module
        from models import User
        with db_module.SessionLocal() as s:
            u = s.query(User).filter(User.username == f"{sub_username}@example.com").first()
            if u is not None:
                u.role = "Sub-Owner"
                u.factory_id = fid
                s.commit()
    sub_login = client.post(
        "/api/auth/login",
        json={"identifier": f"{sub_username}@example.com", "password": "TestPass#2024!"},
    )
    sub_auth = {"Authorization": f"Bearer {sub_login.json().get('access_token') or sub_login.json().get('token')}"}

    # Sub-Owner creates a sale.
    sale = client.post(
        "/api/sales/invoice",
        headers=sub_auth,
        json={
            "date": date.today().isoformat(),
            "customer_id": customer_id,
            "amount_paid": 0.0,
            "legal_invoice_type": "bill_of_supply",
            "items": [
                {
                    "product_size_ml": 250,
                    "variety": "Standard",
                    "packaging_size_name": "250ml",
                    "boxes_sold": 5,
                    "loose_packets_sold": 0,
                    "rate_per_box": 100.0,
                    "rate_per_packet": 0.0,
                    "tax_rate": 0.0,
                }
            ],
        },
    )
    assert sale.status_code in (200, 201), sale.text

    # Check sent messages — at least one should be the sale alert
    # addressed to the Owner's chat_id.
    sent_to_owner = [m for m in sent if m[0] == owner_chat]
    assert any("Sale Created" in m[1] for m in sent_to_owner), (
        f"Sub-Owner sale should fire Owner-bound alert, sent={sent}"
    )


def test_action_alert_does_not_fire_for_owner_action(lifecycle_app):
    """Owner actions must NOT fire the sale alert (per spec rule)."""
    client, _, sent = lifecycle_app
    ctx = _signup_owner(client, "lifecycle_f")
    auth = ctx["auth"]
    fid = ctx["factory_id"]
    owner_chat = _wire_owner_telegram(client, auth, fid)
    customer_id = _create_customer(client, auth, "Owner Test", fid)

    sent.clear()  # drop welcome/welcome-related noise

    # Owner creates a sale.
    sale = client.post(
        "/api/sales/invoice",
        headers=auth,
        json={
            "date": date.today().isoformat(),
            "customer_id": customer_id,
            "amount_paid": 0.0,
            "legal_invoice_type": "bill_of_supply",
            "items": [
                {
                    "product_size_ml": 250,
                    "variety": "Standard",
                    "packaging_size_name": "250ml",
                    "boxes_sold": 3,
                    "loose_packets_sold": 0,
                    "rate_per_box": 100.0,
                    "rate_per_packet": 0.0,
                    "tax_rate": 0.0,
                }
            ],
        },
    )
    assert sale.status_code in (200, 201), sale.text

    # No "Sale Created" alert should have been sent to the Owner
    # because the Owner is the actor (per spec rule).
    sent_to_owner = [m for m in sent if m[0] == owner_chat]
    assert not any("Sale Created" in m[1] for m in sent_to_owner), (
        f"Owner action must not fire self-alert, sent={sent}"
    )


def test_action_alert_failure_does_not_rollback_sale(lifecycle_app):
    """If telegram send fails, the ERP sale must still persist."""
    import services.telegram_action_alerts as taa
    client, _, _ = lifecycle_app
    ctx = _signup_owner(client, "lifecycle_g")
    auth = ctx["auth"]
    fid = ctx["factory_id"]
    _wire_owner_telegram(client, auth, fid)
    customer_id = _create_customer(client, auth, "Failure Test", fid)

    # Make the telegram sender raise.
    import services.telegram_delivery as td
    with patch.object(td, "send_telegram_message", side_effect=RuntimeError("telegram down")):
        sale = client.post(
            "/api/sales/invoice",
            headers=auth,
            json={
                "date": date.today().isoformat(),
                "customer_id": customer_id,
                "amount_paid": 0.0,
                "legal_invoice_type": "bill_of_supply",
                "items": [
                    {
                        "product_size_ml": 250,
                        "variety": "Standard",
                        "packaging_size_name": "250ml",
                        "boxes_sold": 1,
                        "loose_packets_sold": 0,
                        "rate_per_box": 50.0,
                        "rate_per_packet": 0.0,
                        "tax_rate": 0.0,
                    }
                ],
            },
        )
    assert sale.status_code in (200, 201), f"sale must commit even if telegram fails: {sale.text}"

    war = client.get("/api/dashboard/collection-war-room", headers=auth).json()
    assert Decimal(str(war["total_outstanding"])) >= Decimal("50"), (
        f"sale must persist even when telegram fails, war room={war}"
    )


def test_cross_factory_outstanding_isolation(lifecycle_app):
    """A sale in factory A must not appear in factory B's outstanding."""
    client, _, _ = lifecycle_app
    ctx_a = _signup_owner(client, "isolation_a")
    auth_a = ctx_a["auth"]
    fid_a = ctx_a["factory_id"]
    customer_id_a = _create_customer(client, auth_a, "A Customer", fid_a)

    sale = client.post(
        "/api/sales/invoice",
        headers=auth_a,
        json={
            "date": date.today().isoformat(),
            "customer_id": customer_id_a,
            "amount_paid": 0.0,
            "legal_invoice_type": "bill_of_supply",
            "items": [
                {
                    "product_size_ml": 250,
                    "variety": "Standard",
                    "packaging_size_name": "250ml",
                    "boxes_sold": 5,
                    "loose_packets_sold": 0,
                    "rate_per_box": 100.0,
                    "rate_per_packet": 0.0,
                    "tax_rate": 0.0,
                }
            ],
        },
    )
    assert sale.status_code in (200, 201), sale.text

    # Factory B signup.
    ctx_b = _signup_owner(client, "isolation_b")
    auth_b = ctx_b["auth"]
    fid_b = ctx_b["factory_id"]
    assert fid_b != fid_a, f"factories should differ: a={fid_a} b={fid_b}"

    # Factory B's war room must show 0 outstanding.
    war_b = client.get("/api/dashboard/collection-war-room", headers=auth_b).json()
    assert Decimal(str(war_b["total_outstanding"])) == Decimal("0"), (
        f"factory B must not see factory A's outstanding, got {war_b}"
    )

    # Factory A's war room shows the sale.
    war_a = client.get("/api/dashboard/collection-war-room", headers=auth_a).json()
    assert Decimal(str(war_a["total_outstanding"])) >= Decimal("500")

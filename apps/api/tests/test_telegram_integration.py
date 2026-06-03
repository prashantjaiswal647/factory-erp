import os
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_12345678901234567890")
os.environ.setdefault("N8N_API_KEY", "test-n8n-secret")

import pytest
from decimal import Decimal
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base, get_db
from models import Factory, User, Customer, PackagingProfile, Inventory, SalesInvoice
from telegram_crypto import decrypt_token, encrypt_token, get_encryption_key
from routers.integrations import router
from routers.integrations import (
    internal_bot_lookup, basic_generate_invoice, BotLookupRequest, InvoiceGenerateRequest,
    internal_bot_context, get_reports_summary, generate_mode_invoice,
    BotContextRequest, InvoiceGenerateModeRequest
)

# In-memory SQLite DB for testing
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
def setup_db():
    """Rebuild database structure on each test run"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # Seed mock factory and owner user
    factory = Factory(
        id=1,
        name="Test Telegram Factory",
        telegram_token=encrypt_token("mock-telegram-token-12345"),
        telegram_bot_username="test_supervisor_bot",
        telegram_chat_id="987654321",
    )
    user = User(
        id=1,
        factory_id=1,
        username="owner",
        password_hash="hash",
        role="Owner",
        is_verified=True,
    )
    db.add(factory)
    db.add(user)
    db.commit()
    db.close()


def test_telegram_cryptography_encryption_and_decryption():
    raw_token = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
    ciphertext = encrypt_token(raw_token)
    
    # Assert ciphertext is secure and not plaintext
    assert ciphertext != raw_token
    assert len(ciphertext) > 50
    
    # Decrypt and verify match
    decrypted = decrypt_token(ciphertext)
    assert decrypted == raw_token


def test_telegram_cryptography_requires_jwt_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        get_encryption_key()


def test_bot_lookup_unauthorized_header_raises_exception():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: TestingSessionLocal()
    ensure_testclient_compatibility()
    client = TestClient(app)

    response = client.post(
        "/api/ai/n8n-webhook",
        json={"factory_id": 1, "user_message": "status"},
        headers={"X-N8N-API-KEY": "wrong-key"},
    )

    assert response.status_code == 401


def test_ai_n8n_webhook_missing_secret_fails_closed(monkeypatch):
    monkeypatch.delenv("N8N_API_KEY", raising=False)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: TestingSessionLocal()
    ensure_testclient_compatibility()
    client = TestClient(app)

    response = client.post(
        "/api/ai/n8n-webhook",
        json={"factory_id": 1, "user_message": "status"},
        headers={"X-N8N-API-KEY": "anything"},
    )

    assert response.status_code == 503


def test_bot_lookup_authorized_and_valid_chat_id_returns_data():
    db = TestingSessionLocal()
    payload = BotLookupRequest(bot_username="test_supervisor_bot", chat_id="987654321")
    
    res = internal_bot_lookup(payload=payload, db=db)
    
    assert res.factory_id == 1
    assert res.verified is True
    assert res.telegram_bot_token == "mock-telegram-token-12345"
    db.close()


def test_bot_lookup_mismatched_chat_id_raises_forbidden_isolation_breach():
    db = TestingSessionLocal()
    # Owner chat_id is seeded as '987654321', incoming is '555555555' (spoofing attempt)
    payload = BotLookupRequest(bot_username="test_supervisor_bot", chat_id="555555555")
    
    with pytest.raises(HTTPException) as exc:
        internal_bot_lookup(payload=payload, db=db)
        
    assert exc.value.status_code == 403
    assert "Forbidden" in exc.value.detail
    db.close()


def test_bot_lookup_empty_chat_id_binds_dynamically():
    db = TestingSessionLocal()
    # Seed a factory with no chat ID registered yet
    factory = Factory(
        id=2,
        name="Dynamic onboarding factory",
        telegram_token=encrypt_token("dynamic-bot-token"),
        telegram_bot_username="onboard_bot",
        telegram_chat_id=None
    )
    db.add(factory)
    db.commit()
    
    payload = BotLookupRequest(bot_username="onboard_bot", chat_id="222222222")
    res = internal_bot_lookup(payload=payload, db=db)
    
    assert res.factory_id == 2
    assert res.verified is True
    assert res.telegram_bot_token == "dynamic-bot-token"
    
    # Verify it committed back to the database!
    updated_factory = db.query(Factory).filter(Factory.id == 2).first()
    assert updated_factory.telegram_chat_id == "222222222"
    db.close()


def test_invoice_generation_creates_records_and_outputs_clean_markdown():
    db = TestingSessionLocal()
    payload = InvoiceGenerateRequest(factory_id=1)
    
    res = basic_generate_invoice(payload=payload, db=db)
    
    assert res.status == "SUCCESS"
    assert res.invoice_id > 0
    assert "E-INVOICE GENERATED" in res.text_summary
    assert "*Est. Material Weight:* 90.00 kg" in res.text_summary
    assert "*Subtotal:* ₹15,000.00" in res.text_summary
    
    # Verify invoice transaction saved in DB
    invoice = db.query(SalesInvoice).filter(SalesInvoice.id == res.invoice_id).first()
    assert invoice is not None
    assert invoice.total_amount == Decimal("15000.00")
    assert invoice.boxes_sold == 10
    db.close()


def test_bot_context_verification_returns_authorized_data():
    db = TestingSessionLocal()
    payload = BotContextRequest(
        bot_token="mock-telegram-token-12345",
        chat_id="987654321"
    )
    res = internal_bot_context(payload=payload, db=db)
    
    assert res.factory_id == 1
    assert res.is_authorized is True
    assert res.owner_name == "owner"
    db.close()


def test_reports_summary_calculates_correct_metrics():
    db = TestingSessionLocal()
    res = get_reports_summary(factory_id=1, db=db)
    
    assert res["status"] == "HEALTHY"
    assert res["factory_name"] == "Test Telegram Factory"
    assert "metrics" in res
    assert res["metrics"]["total_sales_invoices"] == 0
    db.close()


def test_invoice_generation_basic_mode_calculates_wastage():
    db = TestingSessionLocal()
    payload = InvoiceGenerateModeRequest(factory_id=1, invoice_mode="basic")
    res = generate_mode_invoice(payload=payload, db=db)
    
    assert res.status == "SUCCESS"
    assert res.invoice_mode == "basic"
    assert res.total_amount == Decimal("18000.00")
    assert "INTERNAL BILL GENERATED" in res.text_summary
    assert "*Operational Shifts:* `2` shifts" in res.text_summary
    assert "*Scrap Wastage Reduction:* 1.8% (-1.94 kg)" in res.text_summary
    assert "*Net Billed Weight:* 106.06 kg" in res.text_summary
    db.close()


def test_invoice_generation_gst_mode_calculates_taxes():
    db = TestingSessionLocal()
    payload = InvoiceGenerateModeRequest(factory_id=1, invoice_mode="gst")
    res = generate_mode_invoice(payload=payload, db=db)
    
    assert res.status == "SUCCESS"
    assert res.invoice_mode == "gst"
    assert res.invoice_number == "MNS-2026-0001"
    assert res.subtotal == Decimal("18000.00")
    assert res.cgst == Decimal("1080.00")
    assert res.sgst == Decimal("1080.00")
    assert res.igst == Decimal("0.00")
    assert res.total_amount == Decimal("20160.00")
    assert "TAX INVOICE GENERATED" in res.text_summary
    assert "*Product HSN:* `4823 6900` (Paper Cups)" in res.text_summary
    assert "*CGST (6%):* ₹1,080.00" in res.text_summary
    db.close()

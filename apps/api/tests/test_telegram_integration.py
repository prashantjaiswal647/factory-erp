import os
import pytest
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import Factory, User, Customer, PackagingProfile, Inventory, SalesInvoice
from telegram_crypto import encrypt_token, decrypt_token
from routers.integrations import internal_bot_lookup, basic_generate_invoice, BotLookupRequest, InvoiceGenerateRequest

# In-memory SQLite DB for testing
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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


def test_bot_lookup_unauthorized_header_raises_exception():
    db = TestingSessionLocal()
    payload = BotLookupRequest(bot_username="test_supervisor_bot", chat_id="987654321")
    
    with pytest.raises(HTTPException) as exc:
        internal_bot_lookup(payload=payload, x_n8n_api_key="wrong-key", db=db)
        
    assert exc.value.status_code == 401
    db.close()


def test_bot_lookup_authorized_and_valid_chat_id_returns_data():
    db = TestingSessionLocal()
    payload = BotLookupRequest(bot_username="test_supervisor_bot", chat_id="987654321")
    
    # Match the environment's actual key for local/Docker testing
    api_key = os.getenv("N8N_API_KEY", "replace_with_a_strong_n8n_to_api_secret")
    res = internal_bot_lookup(payload=payload, x_n8n_api_key=api_key, db=db)
    
    assert res.factory_id == 1
    assert res.verified is True
    assert res.telegram_bot_token == "mock-telegram-token-12345"
    db.close()


def test_bot_lookup_mismatched_chat_id_raises_forbidden_isolation_breach():
    db = TestingSessionLocal()
    # Owner chat_id is seeded as '987654321', incoming is '555555555' (spoofing attempt)
    payload = BotLookupRequest(bot_username="test_supervisor_bot", chat_id="555555555")
    
    api_key = os.getenv("N8N_API_KEY", "replace_with_a_strong_n8n_to_api_secret")
    with pytest.raises(HTTPException) as exc:
        internal_bot_lookup(payload=payload, x_n8n_api_key=api_key, db=db)
        
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
    api_key = os.getenv("N8N_API_KEY", "replace_with_a_strong_n8n_to_api_secret")
    
    res = internal_bot_lookup(payload=payload, x_n8n_api_key=api_key, db=db)
    
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
    
    api_key = os.getenv("N8N_API_KEY", "replace_with_a_strong_n8n_to_api_secret")
    res = basic_generate_invoice(payload=payload, x_n8n_api_key=api_key, db=db)
    
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

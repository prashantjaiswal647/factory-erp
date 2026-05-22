from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import authenticate_user, hash_password, normalize_phone_number
from db import Base
from models import User

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def test_india_phone_normalizes_to_e164_and_local_digits():
    full_phone, normalized = normalize_phone_number("9876543210", "+91")

    assert full_phone == "+919876543210"
    assert normalized == "9876543210"


def test_us_phone_normalizes_to_e164_and_local_digits():
    full_phone, normalized = normalize_phone_number("5551234567", "+1")

    assert full_phone == "+15551234567"
    assert normalized == "5551234567"


def test_uae_phone_normalizes_to_e164_and_local_digits():
    full_phone, normalized = normalize_phone_number("501234567", "+971")

    assert full_phone == "+971501234567"
    assert normalized == "501234567"


def test_login_with_local_phone_uses_normalized_lookup():
    db = init_db()
    try:
        user = User(
            id=1,
            user_id="phone-login-user",
            factory_id=1,
            username="owner@example.com",
            email="owner@example.com",
            phone_number="+919876543210",
            phone_number_normalized="9876543210",
            full_name="Owner",
            password_hash=hash_password("secret123"),
            role="Owner",
            is_verified=True,
        )
        db.add(user)
        db.commit()

        found = authenticate_user(db, "9876543210", "secret123")

        assert found is not None
        assert found.phone_number == "+919876543210"
    finally:
        db.close()


def test_email_login_still_works():
    db = init_db()
    try:
        user = User(
            id=2,
            user_id="email-login-user",
            factory_id=1,
            username="owner2@example.com",
            email="owner2@example.com",
            phone_number="+15551234567",
            phone_number_normalized="5551234567",
            full_name="Owner 2",
            password_hash=hash_password("secret123"),
            role="Owner",
            is_verified=True,
        )
        db.add(user)
        db.commit()

        found = authenticate_user(db, "owner2@example.com", "secret123")

        assert found is not None
        assert found.phone_number == "+15551234567"
    finally:
        db.close()

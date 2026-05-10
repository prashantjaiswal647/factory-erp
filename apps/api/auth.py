from datetime import datetime, timedelta, timezone
import os
import random
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from db import get_db
from models import OTPStore, User


JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES") or "480")
OTP_EXPIRE_MINUTES = int(os.getenv("OTP_EXPIRE_MINUTES") or "10")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_jwt_secret_key() -> str:
    secret_key = os.getenv("JWT_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("JWT_SECRET_KEY environment variable is required")
    return secret_key


def ensure_auth_config() -> None:
    get_jwt_secret_key()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(subject: str, role: str, factory_id: Optional[int]) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": subject,
        "role": role,
        "factory_id": factory_id,
        "exp": expires_at,
    }
    return jwt.encode(payload, get_jwt_secret_key(), algorithm=JWT_ALGORITHM)


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return (
        db.query(User)
        .filter(sql_func.lower(User.username) == username.lower())
        .first()
    )


def get_user_by_phone(db: Session, phone_number: str) -> Optional[User]:
    return (
        db.query(User)
        .filter(sql_func.lower(User.phone_number) == phone_number.lower())
        .first()
    )


def get_user_by_subject(db: Session, subject: str) -> Optional[User]:
    # Try phone first, then fallback to username
    user = (
        db.query(User)
        .filter(sql_func.lower(User.phone_number) == subject.lower())
        .first()
    )
    if user is not None:
        return user
    return get_user_by_username(db, subject)


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = get_user_by_username(db, username)
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, get_jwt_secret_key(), algorithms=[JWT_ALGORITHM])
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise credentials_error
    except JWTError as exc:
        raise credentials_error from exc

    user = get_user_by_subject(db, subject)
    if user is None:
        raise credentials_error
    return user


def require_owner(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "Owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner role is required",
        )
    return current_user


# ---------------------------------------------------------------------------
# OTP Helpers
# ---------------------------------------------------------------------------

def generate_otp() -> str:
    return str(random.randint(100000, 999999))


def store_otp(db: Session, phone_number: str, otp_code: str) -> OTPStore:
    # Invalidate previous OTPs for this phone
    db.query(OTPStore).filter(
        sql_func.lower(OTPStore.phone_number) == phone_number.lower()
    ).delete(synchronize_session=False)

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRE_MINUTES)
    record = OTPStore(
        phone_number=phone_number,
        otp_code=otp_code,
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()
    return record


def verify_stored_otp(db: Session, phone_number: str, otp_code: str) -> bool:
    record = (
        db.query(OTPStore)
        .filter(sql_func.lower(OTPStore.phone_number) == phone_number.lower())
        .filter(OTPStore.otp_code == otp_code)
        .first()
    )
    if record is None:
        return False
    if datetime.now(timezone.utc) > record.expires_at:
        return False
    # Clean up used OTP
    db.delete(record)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Auth Endpoints
# ---------------------------------------------------------------------------

from schemas import OTPRequest, OTPVerifyRequest, TokenResponse


@router.post("/request-otp", status_code=status.HTTP_202_ACCEPTED)
def request_otp(
    payload: OTPRequest,
    db: Session = Depends(get_db),
):
    otp = generate_otp()
    store_otp(db, payload.phone_number, otp)
    # MOCK: In production, integrate Twilio / AWS SNS / MSG91 here.
    print(f"[MOCK OTP] Phone: {payload.phone_number} | OTP: {otp}")
    return {"message": "OTP sent successfully (mock)", "phone_number": payload.phone_number}


@router.post("/verify-otp", response_model=TokenResponse)
def verify_otp(
    payload: OTPVerifyRequest,
    db: Session = Depends(get_db),
):
    if not verify_stored_otp(db, payload.phone_number, payload.otp):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP",
        )

    user = get_user_by_phone(db, payload.phone_number)
    if user is None:
        # Auto-register user as Owner on first verified OTP
        user = User(
            username=payload.phone_number,
            phone_number=payload.phone_number,
            password_hash=hash_password(payload.password),
            role="Owner",
            is_verified=True,
            factory_id=0,  # Temporary; will be updated at Step 1
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.is_verified = True
        if payload.password:
            user.password_hash = hash_password(payload.password)
        db.commit()
        db.refresh(user)

    token = create_access_token(
        subject=user.phone_number,
        role=user.role,
        factory_id=user.factory_id if user.factory_id > 0 else None,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        phone_number=user.phone_number,
        role=user.role,
        factory_id=user.factory_id if user.factory_id > 0 else None,
    )


@router.post("/token", response_model=TokenResponse)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    subject = user.phone_number if user.phone_number else user.username
    token = create_access_token(
        subject=subject,
        role=user.role,
        factory_id=user.factory_id if user.factory_id > 0 else None,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        phone_number=user.phone_number or user.username,
        role=user.role,
        factory_id=user.factory_id if user.factory_id > 0 else None,
    )

from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import Factory, FactoryAuthorizedSignature, User
from routers.onboarding import upload_authorized_signature
from services.invoice_pdf import resolve_authorized_signature_path


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _image_bytes(image_format="PNG"):
    buffer = BytesIO()
    Image.new("RGB", (20, 10), "black").save(buffer, format=image_format)
    return buffer.getvalue()


def _user(factory_id, user_id, role):
    return SimpleNamespace(id=user_id, factory_id=factory_id, role=role)


@pytest.mark.anyio
async def test_upload_role_signatures_and_tenant_isolation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _session()
    db.add_all([
        Factory(id=1, name="Factory A"),
        Factory(id=2, name="Factory B"),
        User(id=1, factory_id=1, username="owner", password_hash="x", role="Owner"),
    ])
    db.commit()

    for role in ("owner", "sub_owner", "supervisor"):
        upload = UploadFile(filename=f"{role}.png", file=BytesIO(_image_bytes()), headers={"content-type": "image/png"})
        await upload_authorized_signature(role, upload, current_user=_user(1, 1, "Owner"), db=db)

    assert db.query(FactoryAuthorizedSignature).filter_by(factory_id="1").count() == 3
    assert db.query(FactoryAuthorizedSignature).filter_by(factory_id="2").count() == 0
    assert resolve_authorized_signature_path(db, 1, "Sub-Owner").name == "sub_owner.png"
    assert resolve_authorized_signature_path(db, 1, "Supervisor").name == "supervisor.png"


@pytest.mark.anyio
async def test_missing_role_signature_falls_back_to_owner(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _session()
    db.add_all([
        Factory(id=1, name="Factory A"),
        User(id=1, factory_id=1, username="owner", password_hash="x", role="Owner"),
    ])
    db.commit()
    upload = UploadFile(filename="owner.webp", file=BytesIO(_image_bytes("WEBP")), headers={"content-type": "image/webp"})
    await upload_authorized_signature("owner", upload, current_user=_user(1, 1, "Owner"), db=db)

    assert resolve_authorized_signature_path(db, 1, "Sub-Owner").name == "owner.webp"
    assert resolve_authorized_signature_path(db, 1, "Supervisor").name == "owner.webp"
    assert resolve_authorized_signature_path(db, 2, "Owner") is None


@pytest.mark.anyio
async def test_invalid_type_and_file_size_are_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _session()
    db.add(Factory(id=1, name="Factory A"))
    db.commit()

    invalid = UploadFile(filename="signature.txt", file=BytesIO(b"not-image"), headers={"content-type": "text/plain"})
    with pytest.raises(HTTPException) as invalid_error:
        await upload_authorized_signature("owner", invalid, current_user=_user(1, 1, "Owner"), db=db)
    assert invalid_error.value.status_code == 422

    oversized = UploadFile(
        filename="signature.png",
        file=BytesIO(b"x" * (2 * 1024 * 1024 + 1)),
        headers={"content-type": "image/png"},
    )
    with pytest.raises(HTTPException) as size_error:
        await upload_authorized_signature("owner", oversized, current_user=_user(1, 1, "Owner"), db=db)
    assert size_error.value.status_code == 422

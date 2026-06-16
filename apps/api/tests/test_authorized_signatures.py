from io import BytesIO
from types import SimpleNamespace
from datetime import date

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import Factory, FactoryAuthorizedSignature, InvoiceDocument, User
from routers.onboarding import list_authorized_signatures, upload_authorized_signature
from routers.sales import _invoice_pdf_snapshot
from services.invoice_pdf import build_invoice_pdf_bytes, resolve_authorized_signature_path


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


def test_no_signature_and_missing_file_return_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _session()
    db.add(Factory(id=1, name="Factory A"))
    db.add(FactoryAuthorizedSignature(
        factory_id=1,
        role="owner",
        file_path="volumes/media/factory_signatures/1/missing.png",
        original_filename="missing.png",
        uploaded_by_user_id=1,
    ))
    db.commit()

    assert resolve_authorized_signature_path(db, 2, "Owner") is None
    assert resolve_authorized_signature_path(db, 1, "Owner") is None


def test_signature_path_traversal_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    outside = tmp_path / "outside.png"
    outside.write_bytes(_image_bytes())
    factory = SimpleNamespace(authorized_signature_path="../outside.png")

    assert resolve_authorized_signature_path(factory) is None


def test_legacy_factory_signature_path_resolves_inside_allowed_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    signature = tmp_path / "volumes" / "media" / "signatures" / "1" / "owner.png"
    signature.parent.mkdir(parents=True)
    signature.write_bytes(_image_bytes())
    factory = SimpleNamespace(signature_path=str(signature))

    assert resolve_authorized_signature_path(factory) == signature.resolve()


def test_invoice_pdf_does_not_crash_without_signature():
    pdf = build_invoice_pdf_bytes({
        "invoice": {
            "invoice_id": "INV-1",
            "invoice_date": "2026-06-14",
            "customer_name": "Customer",
            "bill_total": 100,
        },
        "items": [{"description": "Paper Cups", "quantity": 1, "rate": 100}],
    })

    assert pdf.startswith(b"%PDF")


def _invoice_payload(role):
    return {
        "factory_id": 1,
        "generated_by_role": role,
        "invoice": {
            "invoice_id": "INV-1",
            "invoice_date": "2026-06-15",
            "customer_name": "Customer",
            "bill_total": 100,
            "generated_by_role": role,
        },
        "items": [{"description": "Paper Cups", "quantity": 1, "rate": 100}],
    }


@pytest.mark.anyio
async def test_invoice_pdf_renders_owner_signature(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _session()
    db.add_all([
        Factory(id=1, name="Factory A"),
        User(id=1, factory_id=1, username="owner", password_hash="x", role="Owner"),
    ])
    db.commit()
    upload = UploadFile(
        filename="owner.png",
        file=BytesIO(_image_bytes()),
        headers={"content-type": "image/png"},
    )
    await upload_authorized_signature("owner", upload, current_user=_user(1, 1, "Owner"), db=db)
    monkeypatch.setattr("services.invoice_pdf.SessionLocal", lambda: db)
    rendered_paths = []
    real_image = __import__("services.invoice_pdf", fromlist=["Image"]).Image

    def capture_image(path, *args, **kwargs):
        rendered_paths.append(path)
        return real_image(path, *args, **kwargs)

    monkeypatch.setattr("services.invoice_pdf.Image", capture_image)
    pdf = build_invoice_pdf_bytes(_invoice_payload("Owner"))

    assert pdf.startswith(b"%PDF")
    assert len(rendered_paths) == 1
    assert rendered_paths[0].endswith("owner.png")


@pytest.mark.anyio
async def test_invoice_pdf_sub_owner_falls_back_to_owner_signature(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _session()
    db.add_all([
        Factory(id=1, name="Factory A"),
        User(id=1, factory_id=1, username="owner", password_hash="x", role="Owner"),
    ])
    db.commit()
    upload = UploadFile(
        filename="owner.webp",
        file=BytesIO(_image_bytes("WEBP")),
        headers={"content-type": "image/webp"},
    )
    await upload_authorized_signature("owner", upload, current_user=_user(1, 1, "Owner"), db=db)
    monkeypatch.setattr("services.invoice_pdf.SessionLocal", lambda: db)
    rendered_paths = []
    real_image = __import__("services.invoice_pdf", fromlist=["Image"]).Image
    monkeypatch.setattr(
        "services.invoice_pdf.Image",
        lambda path, *args, **kwargs: (
            rendered_paths.append(path),
            real_image(path, *args, **kwargs),
        )[1],
    )

    pdf = build_invoice_pdf_bytes(_invoice_payload("Sub-Owner"))

    assert pdf.startswith(b"%PDF")
    assert len(rendered_paths) == 1
    assert rendered_paths[0].endswith("owner.webp")


def test_invoice_pdf_missing_signature_file_falls_back_to_text(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _session()
    db.add(Factory(id=1, name="Factory A"))
    db.add(FactoryAuthorizedSignature(
        factory_id=1,
        role="owner",
        file_path="factory_signatures/1/missing.png",
        original_filename="missing.png",
        uploaded_by_user_id=1,
    ))
    db.commit()
    monkeypatch.setattr("services.invoice_pdf.SessionLocal", lambda: db)
    monkeypatch.setattr(
        "services.invoice_pdf.Image",
        lambda *args, **kwargs: pytest.fail("missing signature must not be rendered"),
    )

    pdf = build_invoice_pdf_bytes(_invoice_payload("Owner"))

    assert pdf.startswith(b"%PDF")


def test_invoice_snapshot_passes_factory_and_generated_role(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _session()
    db.add(Factory(id=1, name="Factory A"))
    invoice = InvoiceDocument(
        factory_id=1,
        invoice_number="INV-1",
        invoice_date=date(2026, 6, 15),
        customer_name="Customer",
        payment_method="Cash",
        bill_total=100,
        amount_paid=0,
        customer_total_due=100,
        payload_json=_invoice_payload("Sub-Owner"),
        generated_by_role="Sub-Owner",
    )
    db.add(invoice)
    db.commit()
    captured = {}

    def capture_payload(payload):
        captured.update(payload)
        return b"%PDF-test"

    monkeypatch.setattr("routers.sales.build_invoice_pdf_bytes", capture_payload)

    assert _invoice_pdf_snapshot(db, invoice) == b"%PDF-test"
    assert captured["factory_id"] == 1
    assert captured["generated_by_role"] == "Sub-Owner"
    assert captured["invoice"]["factory_id"] == 1


def test_signature_endpoints(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from fastapi.testclient import TestClient
    from main import app
    from db import get_db
    from dependencies import check_permissions, FACTORY_VIEW_ROLES
    
    db = _session()
    db.add_all([
        Factory(id=1, name="Factory A"),
        Factory(id=2, name="Factory B"),
        User(id=1, factory_id=1, username="owner", password_hash="x", role="Owner"),
        User(id=2, factory_id=2, username="owner2", password_hash="x", role="Owner"),
    ])
    db.commit()

    mock_user = db.query(User).filter_by(id=1).first()
    from auth import get_current_user, get_current_active_user

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_current_active_user] = lambda: mock_user
    app.dependency_overrides[check_permissions(FACTORY_VIEW_ROLES)] = lambda: mock_user

    client = TestClient(app)

    # 1. no signatures returns 200 empty slots
    response = client.get("/api/onboarding/signatures")
    assert response.status_code == 200
    data = response.json()
    assert data == {
        role: {
            "uploaded": False,
            "role": role,
            "file_url": None,
            "original_filename": None,
            "updated_at": None,
            "created_at": None,
        }
        for role in ("owner", "sub_owner", "supervisor")
    }

    # 2. upload signature then list returns 200
    img_data = _image_bytes()
    upload_response = client.post(
        "/api/onboarding/signatures/owner",
        files={"file": ("owner.png", img_data, "image/png")}
    )
    assert upload_response.status_code == 200
    assert upload_response.json()["role"] == "owner"

    response = client.get("/api/onboarding/signatures")
    assert response.status_code == 200
    data = response.json()
    assert data["owner"]["uploaded"] is True
    assert data["owner"]["role"] == "owner"
    assert data["owner"]["file_url"] == "/api/onboarding/signatures/owner/file"
    assert data["owner"]["original_filename"] == "owner.png"
    assert isinstance(data["owner"]["updated_at"], str)
    assert isinstance(data["owner"]["created_at"], str)

    file_response = client.get(data["owner"]["file_url"])
    assert file_response.status_code == 200
    assert file_response.headers["content-type"] == "image/png"
    assert file_response.content == img_data

    # 3. tenant isolation
    mock_user2 = db.query(User).filter_by(id=2).first()
    app.dependency_overrides[get_current_user] = lambda: mock_user2
    app.dependency_overrides[get_current_active_user] = lambda: mock_user2
    app.dependency_overrides[check_permissions(FACTORY_VIEW_ROLES)] = lambda: mock_user2

    response2 = client.get("/api/onboarding/signatures")
    assert response2.status_code == 200
    assert response2.json() == {
        role: {
            "uploaded": False,
            "role": role,
            "file_url": None,
            "original_filename": None,
            "updated_at": None,
            "created_at": None,
        }
        for role in ("owner", "sub_owner", "supervisor")
    }
    assert client.get("/api/onboarding/signatures/owner/file").status_code == 404

    # Clean up overrides
    app.dependency_overrides.clear()


def test_signature_listing_returns_frontend_schema(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _session()
    db.add(Factory(id=1, name="Factory A"))
    db.add(FactoryAuthorizedSignature(
        factory_id=1,
        role="owner",
        file_path="volumes/media/factory_signatures/1/owner.png",
        original_filename="owner.png",
        uploaded_by_user_id=1,
    ))
    db.commit()

    response = list_authorized_signatures(current_user=_user(1, 1, "Owner"), db=db)

    assert set(response) == {"owner", "sub_owner", "supervisor"}
    for role, slot in response.items():
        assert set(slot) == {
            "uploaded", "role", "file_url", "original_filename", "updated_at", "created_at"
        }
        assert isinstance(slot["uploaded"], bool)
        assert slot["role"] == role
        assert slot["file_url"] is None or slot["file_url"].startswith("/api/onboarding/signatures/")
        assert "volumes/media" not in (slot["file_url"] or "")
        assert slot["updated_at"] is None or isinstance(slot["updated_at"], str)
        assert slot["created_at"] is None or isinstance(slot["created_at"], str)
    assert response["owner"]["uploaded"] is True

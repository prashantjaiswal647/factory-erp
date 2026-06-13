import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID
from fastapi.testclient import TestClient
from main import app

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

@app.get("/api/test-error-trigger-500-route")
def error_trigger_route():
    raise ValueError("Sensitive database structure / internal query execution details leaked!")


@app.get("/api/test-http-exception-500-route")
def http_exception_500_route():
    try:
        raise RuntimeError("postgresql://private-user:private-password@database/internal")
    except RuntimeError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail=f"Database query failed: {exc}") from exc


@app.get("/api/test-http-exception-400-route")
def http_exception_400_route():
    from fastapi import HTTPException

    raise HTTPException(status_code=400, detail="Actionable validation message")


@app.get("/api/test-http-exception-complex-detail-route")
def http_exception_complex_detail_route():
    from fastapi import HTTPException

    raise HTTPException(
        status_code=422,
        detail={
            "amount": Decimal("12.50"),
            "date": date(2026, 6, 13),
            "timestamp": datetime(2026, 6, 13, 10, 30, tzinfo=timezone.utc),
            "id": UUID("12345678-1234-5678-1234-567812345678"),
        },
    )


def test_unhandled_exception_sanitizer():
    ensure_testclient_compatibility()
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/test-error-trigger-500-route")
    
    assert response.status_code == 500
    data = response.json()
    
    # Assert details are generic and do not leak the ValueError message/trace
    assert "detail" in data
    assert "An internal server error occurred." in data["detail"]
    assert "Sensitive database structure" not in data["detail"]
    assert "ValueError" not in data["detail"]
    
    # Assert Request ID is present in the response
    assert "request_id" in data
    assert len(data["request_id"]) > 0

def test_unhandled_exception_custom_request_id():
    ensure_testclient_compatibility()
    client = TestClient(app, raise_server_exceptions=False)
    # Pass an explicit Request ID header to verify it gets used/returned
    test_req_id = "custom-test-req-id-12345"
    response = client.get(
        "/api/test-error-trigger-500-route",
        headers={"x-request-id": test_req_id}
    )
    
    assert response.status_code == 500
    data = response.json()
    assert data["request_id"] == test_req_id


def test_explicit_http_500_detail_is_sanitized():
    ensure_testclient_compatibility()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/test-http-exception-500-route")

    assert response.status_code == 500
    data = response.json()
    assert data["detail"] == "An internal server error occurred."
    assert data["request_id"]
    assert "private-password" not in response.text
    assert "Database query failed" not in response.text


def test_http_4xx_detail_remains_actionable():
    ensure_testclient_compatibility()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/test-http-exception-400-route")

    assert response.status_code == 400
    assert response.json() == {"detail": "Actionable validation message"}


def test_http_exception_complex_detail_is_json_safe():
    ensure_testclient_compatibility()
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/test-http-exception-complex-detail-route"
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "amount": 12.5,
        "date": "2026-06-13",
        "timestamp": "2026-06-13T10:30:00+00:00",
        "id": "12345678-1234-5678-1234-567812345678",
    }

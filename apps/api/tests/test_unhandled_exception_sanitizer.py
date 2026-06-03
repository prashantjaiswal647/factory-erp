import pytest
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

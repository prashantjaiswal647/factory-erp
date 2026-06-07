import httpx
import pytest

from payments.cashfree_client import CashfreeAPIError, CashfreeClient


def client():
    return CashfreeClient("client", "secret", "https://sandbox.cashfree.com/pg", "sandbox")


def test_create_customer_uses_current_cashfree_contract(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return httpx.Response(200, json={"customer_uid": "cf_customer"})

    monkeypatch.setattr(httpx, "request", fake_request)
    result = client().create_customer("factory_1", "owner@test.com", "+919999999999", "Owner")
    assert result["customer_uid"] == "cf_customer"
    assert captured["headers"]["x-api-version"] == "2025-01-01"
    assert captured["headers"]["x-client-id"] == "client"
    assert captured["json"]["customer_phone"] == "9999999999"


def test_cashfree_error_and_timeout_are_sanitized(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "request",
        lambda *args, **kwargs: httpx.Response(400, json={"code": "invalid", "message": "bad request"}),
    )
    with pytest.raises(CashfreeAPIError) as error:
        client().create_customer("factory_1", "owner@test.com", "9999999999", "Owner")
    assert error.value.code == "invalid"

    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(httpx, "request", timeout)
    with pytest.raises(CashfreeAPIError) as timeout_error:
        client().get_subscription("sub_1")
    assert timeout_error.value.code == "timeout"


def test_create_subscription_body(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return httpx.Response(200, json={"subscription_id": "sub_1", "subscription_session_id": "https://cashfree.test/auth"})

    monkeypatch.setattr(httpx, "request", fake_request)
    result = client().create_subscription("customer", "plan", "sub_1", "note")
    assert result["subscription_id"] == "sub_1"
    assert captured["json"]["plan_id"] == "plan"
    assert captured["json"]["subscription_id"] == "sub_1"


def test_create_order_uses_payment_gateway_order_contract(monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return httpx.Response(200, json={"order_id": "order_1", "payment_session_id": "session_1"})

    monkeypatch.setattr(httpx, "request", fake_request)
    result = client().create_order(
        {
            "order_id": "order_1",
            "order_amount": 999,
            "order_currency": "INR",
            "customer_details": {"customer_id": "factory_1", "customer_phone": "9999999999"},
        }
    )
    assert result["payment_session_id"] == "session_1"
    assert captured["url"].endswith("/orders")
    assert captured["json"]["order_id"] == "order_1"

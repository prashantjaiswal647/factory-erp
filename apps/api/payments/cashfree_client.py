from __future__ import annotations

from typing import Any

import httpx


class CashfreeAPIError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class CashfreeClient:
    def __init__(self, client_id: str, client_secret: str, api_base: str, env: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_base = api_base.rstrip("/")
        self.env = env

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict:
        headers = {
            "x-client-id": self.client_id,
            "x-client-secret": self.client_secret,
            "x-api-version": "2025-01-01",
            "content-type": "application/json",
        }
        try:
            response = httpx.request(
                method,
                f"{self.api_base}{path}",
                headers=headers,
                json=body,
                timeout=10,
            )
        except httpx.TimeoutException as exc:
            raise CashfreeAPIError("timeout", "Cashfree request timed out") from exc
        except httpx.HTTPError as exc:
            raise CashfreeAPIError("network_error", "Cashfree request failed") from exc
        if not response.is_success:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            raise CashfreeAPIError(
                str(payload.get("code") or payload.get("type") or "cashfree_error"),
                str(payload.get("message") or "Cashfree rejected the request"),
                response.status_code,
            )
        return response.json()

    def create_customer(self, customer_id: str, email: str, phone: str, full_name: str) -> dict:
        # Cashfree generates customer_uid; customer_id remains our local correlation key.
        payload = self._request(
            "POST",
            "/customers",
            {
                "customer_email": email,
                "customer_phone": phone[-10:],
                "customer_name": full_name,
            },
        )
        payload.setdefault("customer_id", customer_id)
        return payload

    def create_subscription(
        self,
        customer_id: str,
        plan_id: str,
        subscription_id: str,
        subscription_note: str,
        *,
        customer_details: dict[str, Any] | None = None,
    ) -> dict:
        body = {
            "subscription_id": subscription_id,
            "plan_id": plan_id,
            "subscription_note": subscription_note,
            "customer_details": customer_details or {"customer_id": customer_id},
        }
        return self._request("POST", "/subscriptions", body)

    def get_subscription(self, subscription_id: str) -> dict:
        return self._request("GET", f"/subscriptions/{subscription_id}")

    def cancel_subscription(self, subscription_id: str) -> dict:
        return self._request(
            "PATCH",
            f"/subscriptions/{subscription_id}",
            {"subscription_status": "CANCELLED"},
        )

import logging
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger("uvicorn")

N8N_INVOICE_WEBHOOK_URL = "http://factory-erp-n8n-1:5678/webhook/generate-invoice"
N8N_INVOICE_WEBHOOK_FALLBACK_URL = "https://n8n.munshiai.co.in/webhook/generate-invoice"


def _json_safe(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _json_safe(value.model_dump())
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def push_invoice_to_n8n_bg(payload: dict[str, Any]) -> None:
    primary_url = os.getenv("N8N_INVOICE_WEBHOOK_URL", N8N_INVOICE_WEBHOOK_URL).strip()
    fallback_url = os.getenv("N8N_INVOICE_WEBHOOK_FALLBACK_URL", N8N_INVOICE_WEBHOOK_FALLBACK_URL).strip()
    webhook_urls = [primary_url]
    if fallback_url and fallback_url not in webhook_urls:
        webhook_urls.append(fallback_url)

    safe_payload = _json_safe(payload)
    invoice_context = safe_payload.get("invoice", {}) if isinstance(safe_payload, dict) else {}
    factory_id = safe_payload.get("factory_id") if isinstance(safe_payload, dict) else None
    invoice_id = invoice_context.get("invoice_id") if isinstance(invoice_context, dict) else None

    for webhook_url in webhook_urls:
        try:
            logger.info(
                "Dispatching invoice data body context to n8n endpoint. "
                "webhook_url=%s factory_id=%s invoice_id=%s",
                webhook_url,
                factory_id,
                invoice_id,
            )
            with httpx.Client(timeout=12.0) as client:
                response = client.post(webhook_url, json=safe_payload)
            logger.info(
                "Dispatched data body context to n8n node endpoint. "
                "Server response string trace status: %s",
                response.status_code,
            )
            logger.info(
                "N8N invoice workflow response trace: webhook_url=%s response_body=%s",
                webhook_url,
                response.text[:500],
            )
            response.raise_for_status()
            print(f"N8N invoice workflow accepted: webhook_url={webhook_url}, status_code={response.status_code}")
            return
        except Exception as exc:
            logger.exception(
                "N8N invoice workflow endpoint failed and was ignored for this endpoint. "
                "webhook_url=%s factory_id=%s invoice_id=%s error=%s",
                webhook_url,
                factory_id,
                invoice_id,
                exc,
            )
            print(f"N8N invoice workflow failed and was ignored: webhook_url={webhook_url}, error={exc}")

    logger.error(
        "N8N invoice workflow dispatch failed for all configured endpoints. "
        "factory_id=%s invoice_id=%s attempted_urls=%s",
        factory_id,
        invoice_id,
        webhook_urls,
    )

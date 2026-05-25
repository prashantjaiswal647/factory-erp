import logging
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

N8N_INVOICE_WEBHOOK_URL = "http://factory-erp-n8n-1:5678/webhook/generate-invoice"


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
    webhook_url = os.getenv("N8N_INVOICE_WEBHOOK_URL", N8N_INVOICE_WEBHOOK_URL).strip()

    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.post(webhook_url, json=_json_safe(payload))
            response.raise_for_status()
        print(f"N8N invoice workflow accepted: status_code={response.status_code}")
    except Exception as exc:
        logger.exception("N8N invoice workflow failed and was ignored")
        print(f"N8N invoice workflow failed and was ignored: webhook_url={webhook_url}, error={exc}")

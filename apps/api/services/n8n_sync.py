import logging
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

import httpx
from pydantic import BaseModel

logger = logging.getLogger("uvicorn")

N8N_SYNC_WEBHOOK_URL = "http://factory-erp-n8n-1:5678/webhook/sync-data"
N8N_SYNC_WEBHOOK_FALLBACK_URL = "https://n8n.munshiai.co.in/webhook/sync-data"
SyncType = Literal["production", "onboarding", "sales", "worker"]
SyncAction = Literal["insert", "delete"]


def _serialize_for_json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _serialize_for_json(value.model_dump())
    if isinstance(value, dict):
        return {key: _serialize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_for_json(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def sync_data_to_n8n_bg(
    factory_id: str,
    sync_type: SyncType,
    action: SyncAction,
    data: dict[str, Any] | BaseModel,
) -> None:
    primary_url = os.getenv("N8N_SYNC_WEBHOOK_URL", N8N_SYNC_WEBHOOK_URL).strip()
    fallback_url = os.getenv("N8N_SYNC_WEBHOOK_FALLBACK_URL", N8N_SYNC_WEBHOOK_FALLBACK_URL).strip()
    webhook_urls = [primary_url]
    if fallback_url and fallback_url not in webhook_urls:
        webhook_urls.append(fallback_url)
    payload = {
        "factory_id": str(factory_id),
        "sync_type": sync_type,
        "action": action,
        "data": _serialize_for_json(data),
    }

    logger.info("N8N live sync queued: factory_id=%s sync_type=%s action=%s", factory_id, sync_type, action)
    for webhook_url in webhook_urls:
        try:
            logger.info(
                "Dispatching live sync data body context to n8n endpoint. "
                "factory_id=%s sync_type=%s action=%s",
                factory_id,
                sync_type,
                action,
            )
            with httpx.Client(timeout=8.0) as client:
                response = client.post(webhook_url, json=payload)
            logger.info(
                "Dispatched data body context to n8n node endpoint. "
                "Server response string trace status: %s",
                response.status_code,
            )
            response.raise_for_status()
            logger.info("N8N live sync succeeded with status_code=%s", response.status_code)
            return
        except Exception as exc:
            logger.exception(
                "N8N live sync endpoint failed and was ignored for this endpoint. "
                "factory_id=%s sync_type=%s action=%s error=%s",
                factory_id,
                sync_type,
                action,
                exc,
            )

    logger.error(
        "N8N live sync failed for all configured endpoints. "
        "factory_id=%s sync_type=%s action=%s attempted_endpoint_count=%s",
        factory_id,
        sync_type,
        action,
        len(webhook_urls),
    )

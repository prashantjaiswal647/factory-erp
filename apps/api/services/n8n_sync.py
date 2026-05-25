import logging
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

N8N_SYNC_WEBHOOK_URL = "http://factory-erp-n8n-1:5678/webhook/sync-data"
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
    webhook_url = os.getenv("N8N_SYNC_WEBHOOK_URL", N8N_SYNC_WEBHOOK_URL).strip()
    payload = {
        "factory_id": str(factory_id),
        "sync_type": sync_type,
        "action": action,
        "data": _serialize_for_json(data),
    }

    print(f"N8N live sync queued: factory_id={factory_id}, sync_type={sync_type}, action={action}")
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.post(webhook_url, json=payload)
            response.raise_for_status()
        print(f"N8N live sync succeeded: status_code={response.status_code}")
    except Exception as exc:
        logger.exception("N8N live sync failed and was ignored")
        print(f"N8N live sync failed and was ignored: webhook_url={webhook_url}, error={exc}")

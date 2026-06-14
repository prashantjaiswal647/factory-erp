from __future__ import annotations

import asyncio
from datetime import date
from io import BytesIO
import json
import logging
import os
from pathlib import Path
from typing import Awaitable, Callable

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from sqlalchemy.orm import Session

from models import Factory, User
from services.master_backup import BACKUP_ROOT, build_master_backup


logger = logging.getLogger(__name__)
DELIVERY_ROOT = BACKUP_ROOT / "scheduled-email"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def resolve_owner_email(owner: User) -> str | None:
    email = (owner.email or "").strip()
    if email:
        return email
    username = (owner.username or "").strip()
    return username if "@" in username else None


def build_mail_config() -> ConnectionConfig | None:
    smtp_user = (os.getenv("SMTP_USER") or os.getenv("MAIL_USERNAME") or "").strip()
    smtp_password = (os.getenv("SMTP_PASSWORD") or os.getenv("MAIL_PASSWORD") or "").strip()
    smtp_from = (os.getenv("SMTP_FROM") or os.getenv("MAIL_FROM") or smtp_user).strip()
    smtp_server = (os.getenv("SMTP_HOST") or os.getenv("MAIL_SERVER") or "").strip()
    smtp_port = int(os.getenv("SMTP_PORT") or os.getenv("MAIL_PORT") or "587")
    if not smtp_user or not smtp_password or not smtp_from or not smtp_server:
        return None
    return ConnectionConfig(
        MAIL_USERNAME=smtp_user,
        MAIL_PASSWORD=smtp_password,
        MAIL_FROM=smtp_from,
        MAIL_PORT=smtp_port,
        MAIL_SERVER=smtp_server,
        MAIL_STARTTLS=(os.getenv("SMTP_STARTTLS") or "true").lower() == "true",
        MAIL_SSL_TLS=(os.getenv("SMTP_SSL_TLS") or "false").lower() == "true",
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True,
    )


async def send_backup_email(
    *,
    recipient: str,
    subject: str,
    body: str,
    backup_bytes: bytes,
    filename: str,
) -> None:
    config = build_mail_config()
    if config is None:
        raise RuntimeError("SMTP configuration is incomplete")
    message = MessageSchema(
        subject=subject,
        recipients=[recipient],
        body=body,
        subtype=MessageType.plain,
        attachments=[{
            "file": BytesIO(backup_bytes),
            "filename": filename,
            "content_type": XLSX_CONTENT_TYPE,
        }],
    )
    await FastMail(config).send_message(message)


def period_key(frequency: str, target_date: date) -> str:
    if frequency == "weekly":
        year, week, _ = target_date.isocalendar()
        return f"{year}-W{week:02d}"
    if frequency == "monthly":
        return target_date.strftime("%Y-%m")
    raise ValueError("Unsupported backup email frequency")


def delivery_marker_path(factory_id: int, frequency: str, key: str) -> Path:
    return DELIVERY_ROOT / str(factory_id) / frequency / f"{key}.json"


def _reserve_delivery(marker: Path) -> bool:
    marker.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump({"status": "sending"}, handle)
    return True


def _complete_delivery(marker: Path, payload: dict) -> None:
    marker.write_text(json.dumps({"status": "sent", **payload}, ensure_ascii=True), encoding="utf-8")


async def deliver_master_backup(
    db: Session,
    factory: Factory,
    owner: User,
    frequency: str,
    target_date: date,
    *,
    sender: Callable[..., Awaitable[None]] = send_backup_email,
) -> bool:
    key = period_key(frequency, target_date)
    marker = delivery_marker_path(int(factory.id), frequency, key)
    if not _reserve_delivery(marker):
        return False

    recipient = resolve_owner_email(owner)
    if not recipient:
        marker.unlink(missing_ok=True)
        raise RuntimeError("Active owner email is not configured")

    safe_frequency = "Weekly" if frequency == "weekly" else "Monthly"
    filename = f"munshi_ai_{frequency}_backup_factory_{factory.id}_{key}.xlsx"
    backup_bytes = build_master_backup(db, int(factory.id)).getvalue()
    try:
        await sender(
            recipient=recipient,
            subject=f"Munshi AI {safe_frequency} Master Backup - {key}",
            body=(
                f"Attached is the {frequency} master backup for "
                f"{factory.factory_name or factory.name}. Keep this file secure."
            ),
            backup_bytes=backup_bytes,
            filename=filename,
        )
    except Exception:
        marker.unlink(missing_ok=True)
        raise
    _complete_delivery(marker, {"recipient": recipient, "filename": filename})
    return True


def run_async(coroutine) -> None:
    asyncio.run(coroutine)

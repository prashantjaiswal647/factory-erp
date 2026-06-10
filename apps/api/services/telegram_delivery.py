from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from models import Factory, TelegramUserBinding, User
from telegram_crypto import decrypt_token


class TelegramDeliveryError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def send_telegram_message(
    factory: Factory,
    message_text: str,
    timeout_seconds: float = 15.0,
    reply_markup: dict | None = None,
) -> None:
    token = decrypt_token(factory.telegram_token) if factory.telegram_token else (factory.telegram_bot_token or "")
    chat_id = (getattr(factory, "_telegram_target_chat_id", None) or factory.telegram_chat_id or "").strip()
    if not token or not chat_id:
        raise TelegramDeliveryError("Telegram bot token or chat ID is not configured")

    try:
        payload = {"chat_id": chat_id, "text": message_text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
            timeout=timeout_seconds,
        )
        payload = response.json()
    except httpx.ConnectError as exc:
        raise TelegramDeliveryError("Telegram connection failed", retryable=True) from exc
    except httpx.TimeoutException as exc:
        # Telegram sendMessage has no idempotency key. A timeout may mean the
        # message was accepted, so retrying could create a duplicate.
        raise TelegramDeliveryError("Telegram request timed out") from exc
    except httpx.HTTPError as exc:
        raise TelegramDeliveryError(f"Telegram request failed: {type(exc).__name__}") from exc
    except ValueError as exc:
        raise TelegramDeliveryError("Telegram returned an invalid response") from exc

    if response.status_code >= 400 or not payload.get("ok"):
        description = str(payload.get("description") or "Telegram rejected the message")
        raise TelegramDeliveryError(
            description[:500],
            retryable=response.status_code == 429 or response.status_code >= 500,
        )


def get_owner_telegram_targets(db: Session, factory_id: int) -> list[str]:
    targets = [
        row.telegram_chat_id
        for row in db.query(TelegramUserBinding).filter(
            TelegramUserBinding.factory_id == factory_id,
            TelegramUserBinding.role == "Owner",
            TelegramUserBinding.is_active.is_(True),
        ).all()
        if row.telegram_chat_id
    ]
    if targets:
        return list(dict.fromkeys(targets))
    factory = db.query(Factory).filter(Factory.id == factory_id).first()
    return [factory.telegram_chat_id] if factory and factory.telegram_chat_id else []


def get_sub_owner_telegram_targets(db: Session, factory_id: int) -> list[str]:
    return list(dict.fromkeys(
        row.telegram_chat_id
        for row in db.query(TelegramUserBinding).filter(
            TelegramUserBinding.factory_id == factory_id,
            TelegramUserBinding.role == "Sub-Owner",
            TelegramUserBinding.is_active.is_(True),
        ).all()
        if row.telegram_chat_id
    ))


def send_message_to_targets(factory: Factory, message_text: str, targets: list[str]) -> int:
    sent = 0
    for chat_id in dict.fromkeys(targets):
        factory._telegram_target_chat_id = chat_id
        send_telegram_message(factory, message_text)
        sent += 1
    return sent


def send_owner_action_alert(
    db: Session,
    factory_id: int,
    actor_user: User,
    action_type: str,
    entity_type: str,
    entity_id: int | str | None,
    summary: str,
) -> int:
    if actor_user.role not in {"Sub-Owner", "Supervisor"}:
        return 0
    factory = db.query(Factory).filter(Factory.id == factory_id).first()
    if factory is None or actor_user.factory_id != factory_id:
        return 0
    message = (
        "🔔 Munshi AI Action Alert\n\n"
        f"Factory: {factory.name}\n"
        f"Action by: {actor_user.full_name or actor_user.username} ({actor_user.role})\n"
        f"Module: {entity_type}\n"
        f"Action: {action_type}\n"
        f"Details: {summary[:300]}\n"
        f"Time: {datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%d %b %Y, %I:%M %p')}"
    )
    return send_message_to_targets(factory, message, get_owner_telegram_targets(db, factory_id))


def send_role_briefing(db: Session, factory_id: int, role: str, message_text: str) -> int:
    factory = db.query(Factory).filter(Factory.id == factory_id).first()
    if factory is None:
        return 0
    if role == "Owner":
        targets = get_owner_telegram_targets(db, factory_id)
    elif role == "Sub-Owner":
        targets = get_sub_owner_telegram_targets(db, factory_id)
    else:
        return 0
    return send_message_to_targets(factory, message_text, targets)

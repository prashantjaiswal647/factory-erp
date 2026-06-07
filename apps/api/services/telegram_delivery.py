from __future__ import annotations

import httpx

from models import Factory
from telegram_crypto import decrypt_token


class TelegramDeliveryError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def send_telegram_message(factory: Factory, message_text: str, timeout_seconds: float = 15.0) -> None:
    token = decrypt_token(factory.telegram_token) if factory.telegram_token else (factory.telegram_bot_token or "")
    chat_id = (factory.telegram_chat_id or "").strip()
    if not token or not chat_id:
        raise TelegramDeliveryError("Telegram bot token or chat ID is not configured")

    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message_text},
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

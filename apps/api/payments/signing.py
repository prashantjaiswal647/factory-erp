import base64
import hashlib
import hmac
import os
import time


def verify_cashfree_signature(
    raw_body: bytes,
    signature: str,
    timestamp: str,
    webhook_secret: str,
    *,
    max_age_seconds: int = 300,
) -> bool:
    if not signature or not timestamp or not webhook_secret:
        return False
    try:
        timestamp_value = int(timestamp)
    except (TypeError, ValueError):
        return False
    timestamp_seconds = timestamp_value / 1000 if timestamp_value > 10_000_000_000 else timestamp_value
    if abs(time.time() - timestamp_seconds) > max_age_seconds:
        return False
    digest = hmac.new(
        webhook_secret.encode("utf-8"),
        timestamp.encode("utf-8") + raw_body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature)


def get_webhook_secret() -> str:
    secret = os.getenv("CASHFREE_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise RuntimeError("CASHFREE_WEBHOOK_SECRET is not configured")
    return secret

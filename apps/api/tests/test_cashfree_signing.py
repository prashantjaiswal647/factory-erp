import base64
import hashlib
import hmac
import time

from payments.signing import verify_cashfree_signature


def sign(body: bytes, timestamp: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def test_valid_signature():
    body = b'{"event_id":"evt_1"}'
    timestamp = str(int(time.time() * 1000))
    assert verify_cashfree_signature(body, sign(body, timestamp, "secret"), timestamp, "secret")


def test_invalid_signature_and_tampering_are_rejected():
    body = b'{"event_id":"evt_1"}'
    timestamp = str(int(time.time() * 1000))
    signature = sign(body, timestamp, "secret")
    assert not verify_cashfree_signature(body, "bad", timestamp, "secret")
    assert not verify_cashfree_signature(body + b" ", signature, timestamp, "secret")
    assert not verify_cashfree_signature(body, signature, str(int(timestamp) + 1), "secret")


def test_missing_headers_and_stale_timestamp_are_rejected():
    body = b"{}"
    stale = str(int((time.time() - 3600) * 1000))
    assert not verify_cashfree_signature(body, "", stale, "secret")
    assert not verify_cashfree_signature(body, sign(body, stale, "secret"), stale, "secret")

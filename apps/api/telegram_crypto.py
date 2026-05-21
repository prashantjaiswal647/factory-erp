import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes

def get_encryption_key() -> bytes:
    """
    Derives a cryptographically secure 32-byte URL-safe base64 key
    from the JWT_SECRET_KEY environment variable.
    """
    secret = os.getenv("JWT_SECRET_KEY", "fallback-secret-key-for-telegram-encryption-12345")
    digest = hashes.Hash(hashes.SHA256())
    digest.update(secret.encode())
    key_bytes = digest.finalize()
    return base64.urlsafe_b64encode(key_bytes)

def encrypt_token(token: str) -> str:
    """
    Encrypts a plaintext Telegram bot token using Fernet encryption.
    """
    if not token:
        return ""
    f = Fernet(get_encryption_key())
    return f.encrypt(token.strip().encode()).decode()

def decrypt_token(token_ciphertext: str) -> str:
    """
    Decrypts an encrypted Telegram bot token using Fernet encryption.
    """
    if not token_ciphertext:
        return ""
    f = Fernet(get_encryption_key())
    try:
        return f.decrypt(token_ciphertext.strip().encode()).decode()
    except Exception:
        # Fallback to returning the ciphertext directly if it's not actually encrypted (backward compatibility)
        return token_ciphertext

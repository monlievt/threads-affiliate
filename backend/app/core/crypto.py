"""app/core/crypto.py — Symmetric encryption for sensitive tokens (Threads OAuth tokens).

Tokens are stored encrypted as BLOB in the database and never logged in plaintext.
Uses Fernet (AES-128-CBC + HMAC-SHA256 authenticated encryption).
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _derive_fernet_key(raw_key: str) -> bytes:
    """Derive a valid 32-byte urlsafe-base64 Fernet key from raw configuration.

    If raw_key is already a valid Fernet key (32 base64url-encoded bytes), it is used directly.
    Otherwise, SHA-256 is used to derive a deterministic 32-byte key.
    """
    try:
        raw_bytes = raw_key.encode("utf-8")
        decoded = base64.urlsafe_b64decode(raw_bytes)
        if len(decoded) == 32:
            return raw_bytes
    except Exception:
        pass

    # Derive 32 bytes via SHA-256 and base64url-encode
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def generate_encryption_key() -> str:
    """Generate a new secure 32-byte base64url-encoded Fernet key."""
    return Fernet.generate_key().decode("ascii")


def _get_fernet() -> Fernet:
    """Instantiate Fernet using the configured TOKEN_ENCRYPTION_KEY."""
    key = _derive_fernet_key(settings.TOKEN_ENCRYPTION_KEY)
    return Fernet(key)


def encrypt_token(plaintext: str) -> bytes:
    """Encrypt a plaintext OAuth token or sensitive string to ciphertext bytes.

    Args:
        plaintext: Raw token string to encrypt.

    Returns:
        Encrypted ciphertext bytes suitable for storing in a BLOB column.
    """
    if not plaintext:
        return b""
    fernet = _get_fernet()
    return fernet.encrypt(plaintext.encode("utf-8"))


def decrypt_token(ciphertext: bytes) -> str:
    """Decrypt ciphertext bytes back to the original plaintext token.

    Args:
        ciphertext: Encrypted BLOB bytes from the database.

    Returns:
        Decrypted plaintext token string.

    Raises:
        ValueError: If decryption fails (corrupt data or invalid key).
    """
    if not ciphertext:
        return ""
    fernet = _get_fernet()
    try:
        decrypted_bytes = fernet.decrypt(ciphertext)
        return decrypted_bytes.decode("utf-8")
    except InvalidToken as exc:
        logger.error("Token decryption failed: invalid token or mismatched encryption key")
        raise ValueError("Decryption failed: invalid ciphertext or mismatched key") from exc


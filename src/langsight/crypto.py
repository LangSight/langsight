"""Envelope encryption for secrets stored in Postgres (provider API keys).

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the ``cryptography`` library.
The encryption key is derived from LANGSIGHT_SECRET_KEY via PBKDF2-SHA256
with a fixed salt so the same env var always produces the same Fernet key.

When LANGSIGHT_SECRET_KEY is not set, encryption is disabled and values are
stored/returned as-is — this matches the pre-encryption behaviour for local
dev. A warning is logged on every startup when the key is absent.
"""

from __future__ import annotations

import base64
import hashlib
import os

import structlog

logger = structlog.get_logger()

_PREFIX = "enc:fernet:"

_fernet_instance: object | None = None  # lazy — avoid import cost if unused
_encryption_available: bool = False


def _get_fernet() -> object | None:
    """Return a Fernet instance keyed from LANGSIGHT_SECRET_KEY, or None."""
    global _fernet_instance, _encryption_available  # noqa: PLW0603
    if _fernet_instance is not None:
        return _fernet_instance

    secret = os.environ.get("LANGSIGHT_SECRET_KEY", "")
    if not secret:
        _encryption_available = False
        return None

    try:
        from cryptography.fernet import Fernet

        # Derive a 32-byte key via PBKDF2 → base64 encode for Fernet
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            secret.encode(),
            b"langsight-provider-keys-v1",
            iterations=480_000,
        )
        key = base64.urlsafe_b64encode(dk[:32])
        _fernet_instance = Fernet(key)
        _encryption_available = True
        return _fernet_instance
    except ImportError:
        logger.warning(
            "crypto.cryptography_not_installed",
            hint="pip install cryptography to enable provider key encryption",
        )
        _encryption_available = False
        return None


def is_encryption_available() -> bool:
    """Return True if encryption is configured and usable."""
    _get_fernet()
    return _encryption_available


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns prefixed ciphertext, or plaintext if encryption unavailable."""
    if not plaintext:
        return plaintext
    f = _get_fernet()
    if f is None:
        return plaintext
    token = f.encrypt(plaintext.encode())  # type: ignore[union-attr]
    return _PREFIX + token.decode()


def decrypt_value(stored: str) -> str:
    """Decrypt a stored value. Handles both encrypted (prefixed) and legacy plaintext."""
    if not stored:
        return stored
    if not stored.startswith(_PREFIX):
        # Legacy plaintext — return as-is
        return stored
    f = _get_fernet()
    if f is None:
        logger.error(
            "crypto.decrypt_failed_no_key",
            hint="LANGSIGHT_SECRET_KEY is required to decrypt stored provider keys",
        )
        return ""
    try:
        ciphertext = stored[len(_PREFIX) :].encode()
        return f.decrypt(ciphertext).decode()  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        logger.error("crypto.decrypt_failed", hint="Stored value may be corrupted or key changed")
        return ""

"""
Secure payload utilities — signing, verification, and optional encryption.

Design principle: **plaintext at rest, signed on boundary, encrypted on wire.**

Data flows through a pipeline as normal Payload dicts. At the boundary
(before transmitting to RemoteFilter, writing to checkpoint, or persisting
to external storage), you sign or encrypt. On the receiving side, you
verify or decrypt.

This module provides the functional helpers:
- ``seal_payload``   — HMAC-SHA256 sign a payload dict.
- ``verify_payload`` — verify a signed payload dict.
- ``encrypt_data``   — symmetric encrypt a dict to a base64 string.
- ``decrypt_data``   — decrypt a base64 string back to a dict.
- ``SecurePayloadError`` — raised on tamper, wrong key, or expiry.

Filter wrappers live in their own files (CUP convention):
- ``sign_filter.py``    → ``SignFilter``
- ``verify_filter.py``  → ``VerifyFilter``
- ``encrypt_filter.py`` → ``EncryptFilter``
- ``decrypt_filter.py`` → ``DecryptFilter``

Zero external dependencies — stdlib only (hashlib, hmac, secrets, base64, json).

Absorbed from the Zero-Trust Deploy Config prototype's crypto concepts.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Dict, Optional

__all__ = [
    "seal_payload",
    "verify_payload",
    "encrypt_data",
    "decrypt_data",
    "SecurePayloadError",
]


class SecurePayloadError(Exception):
    """Raised when signature verification fails or data is tampered."""


# ── Functional helpers ──────────────────────────────────


def _compute_hmac(data_bytes: bytes, key: bytes) -> str:
    """Compute HMAC-SHA256 and return hex digest."""
    return hmac.new(key, data_bytes, hashlib.sha256).hexdigest()


def seal_payload(
    data: Dict[str, Any],
    key: bytes,
    *,
    timestamp: bool = True,
) -> Dict[str, Any]:
    """Sign a payload dict with HMAC-SHA256.

    Returns a new dict with ``_signature``, ``_signed_at`` (optional),
    and the original data nested under ``_data``.

    Args:
        data: The payload data to sign.
        key: HMAC signing key (bytes).
        timestamp: Include signing timestamp (default True).
    """
    envelope: Dict[str, Any] = {"_data": data}
    if timestamp:
        envelope["_signed_at"] = time.time()
    # Canonical JSON for deterministic signing
    canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    envelope["_signature"] = _compute_hmac(canonical.encode("utf-8"), key)
    return envelope


def verify_payload(
    envelope: Dict[str, Any],
    key: bytes,
    *,
    max_age: Optional[float] = None,
) -> Dict[str, Any]:
    """Verify a signed payload envelope and return the inner data.

    Args:
        envelope: The signed envelope from ``seal_payload``.
        key: HMAC signing key (must match the one used to sign).
        max_age: Maximum age in seconds (None = no expiry check).

    Returns:
        The original data dict.

    Raises:
        SecurePayloadError: If signature is invalid or payload is expired.
    """
    if "_signature" not in envelope or "_data" not in envelope:
        raise SecurePayloadError("Missing _signature or _data — not a signed payload")

    sig = envelope.pop("_signature")
    canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    expected = _compute_hmac(canonical.encode("utf-8"), key)

    if not hmac.compare_digest(sig, expected):
        raise SecurePayloadError("HMAC signature mismatch — payload was tampered")

    if max_age is not None and "_signed_at" in envelope:
        age = time.time() - envelope["_signed_at"]
        if age > max_age:
            raise SecurePayloadError(
                f"Payload expired: signed {age:.0f}s ago, max_age={max_age}s"
            )

    return envelope["_data"]


# ── Encrypt / Decrypt helpers ───────────────────────────
# Lightweight symmetric encryption using stdlib.
# Format: base64(salt:16 + nonce:16 + hmac:32 + ciphertext)
# Uses XOR with a PBKDF2-derived keystream + HMAC-SHA256 for auth.
# This is NOT equivalent to AES-GCM — it's a lightweight envelope
# for data-at-rest that doesn't require external dependencies.
# For production encryption needs, use cryptography.fernet or similar.

_SALT_LEN = 16
_NONCE_LEN = 16
_HMAC_LEN = 32
_KDF_ITERATIONS = 100_000


def _derive_key(passphrase: bytes, salt: bytes) -> bytes:
    """PBKDF2-HMAC-SHA256 key derivation."""
    return hashlib.pbkdf2_hmac("sha256", passphrase, salt, _KDF_ITERATIONS)


def _xor_bytes(data: bytes, keystream: bytes) -> bytes:
    """XOR data with repeating keystream."""
    ks_len = len(keystream)
    return bytes(d ^ keystream[i % ks_len] for i, d in enumerate(data))


def encrypt_data(data: Dict[str, Any], key: bytes) -> str:
    """Encrypt a dict to a base64 string with HMAC authentication.

    Args:
        data: Dict to encrypt.
        key: Encryption key (bytes).

    Returns:
        Base64-encoded encrypted string with "cup_enc:" prefix.
    """
    plaintext = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    salt = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    derived = _derive_key(key, salt + nonce)

    # XOR encrypt
    ciphertext = _xor_bytes(plaintext, derived)

    # HMAC over salt + nonce + ciphertext for authentication
    mac = hmac.new(derived, salt + nonce + ciphertext, hashlib.sha256).digest()

    # Pack: salt + nonce + mac + ciphertext
    packed = salt + nonce + mac + ciphertext
    return "cup_enc:" + base64.b64encode(packed).decode("ascii")


def decrypt_data(encrypted: str, key: bytes) -> Dict[str, Any]:
    """Decrypt a base64 string back to a dict.

    Args:
        encrypted: String from ``encrypt_data`` (with "cup_enc:" prefix).
        key: Encryption key (must match).

    Returns:
        The original dict.

    Raises:
        SecurePayloadError: If authentication fails or data is corrupt.
    """
    prefix = "cup_enc:"
    if not encrypted.startswith(prefix):
        raise SecurePayloadError("Not an encrypted payload — missing cup_enc: prefix")

    try:
        packed = base64.b64decode(encrypted[len(prefix):])
    except Exception as exc:
        raise SecurePayloadError(f"Invalid base64: {exc}") from exc

    if len(packed) < _SALT_LEN + _NONCE_LEN + _HMAC_LEN + 1:
        raise SecurePayloadError("Encrypted payload too short")

    salt = packed[:_SALT_LEN]
    nonce = packed[_SALT_LEN:_SALT_LEN + _NONCE_LEN]
    mac = packed[_SALT_LEN + _NONCE_LEN:_SALT_LEN + _NONCE_LEN + _HMAC_LEN]
    ciphertext = packed[_SALT_LEN + _NONCE_LEN + _HMAC_LEN:]

    derived = _derive_key(key, salt + nonce)

    # Verify HMAC before decrypting
    expected_mac = hmac.new(derived, salt + nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected_mac):
        raise SecurePayloadError("HMAC mismatch — wrong key or tampered ciphertext")

    plaintext = _xor_bytes(ciphertext, derived)
    try:
        return json.loads(plaintext.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SecurePayloadError(f"Decrypted data is not valid JSON: {exc}") from exc

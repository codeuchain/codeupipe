"""
Tests for codeupipe.core.secure — functional helpers: signing, verification, encryption, decryption.
"""

import time

import pytest

from codeupipe.core.secure import (
    SecurePayloadError,
    decrypt_data,
    encrypt_data,
    seal_payload,
    verify_payload,
)


# ── seal / verify round-trip ────────────────────────────


class TestSealVerify:
    def test_round_trip(self):
        key = b"test-secret-key-for-hmac"
        data = {"user_id": 42, "role": "admin", "nested": {"a": 1}}
        sealed = seal_payload(data, key)
        result = verify_payload(sealed, key)
        assert result == data

    def test_tamper_detection(self):
        key = b"my-secret"
        data = {"amount": 100}
        sealed = seal_payload(data, key)
        # Tamper with the data
        sealed["_data"]["amount"] = 999
        with pytest.raises(SecurePayloadError, match="tampered"):
            verify_payload(sealed, key)

    def test_wrong_key_fails(self):
        data = {"x": 1}
        sealed = seal_payload(data, b"key-a")
        with pytest.raises(SecurePayloadError, match="tampered"):
            verify_payload(sealed, b"key-b")

    def test_timestamp_included(self):
        sealed = seal_payload({"a": 1}, b"k", timestamp=True)
        assert "_signed_at" in sealed
        assert isinstance(sealed["_signed_at"], float)

    def test_no_timestamp(self):
        sealed = seal_payload({"a": 1}, b"k", timestamp=False)
        assert "_signed_at" not in sealed
        # Still verifiable
        result = verify_payload(sealed, b"k")
        assert result == {"a": 1}

    def test_max_age_ok(self):
        key = b"k"
        sealed = seal_payload({"a": 1}, key)
        result = verify_payload(sealed, key, max_age=60)
        assert result == {"a": 1}

    def test_max_age_expired(self):
        key = b"k"
        sealed = seal_payload({"a": 1}, key)
        # Backdate the timestamp
        sealed.pop("_signature")
        sealed["_signed_at"] = time.time() - 120
        # Re-sign with the backdated timestamp
        import json, hmac, hashlib
        canonical = json.dumps(sealed, sort_keys=True, separators=(",", ":"))
        sealed["_signature"] = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
        with pytest.raises(SecurePayloadError, match="expired"):
            verify_payload(sealed, key, max_age=60)

    def test_missing_signature_raises(self):
        with pytest.raises(SecurePayloadError, match="Missing"):
            verify_payload({"_data": {}}, b"k")

    def test_missing_data_raises(self):
        with pytest.raises(SecurePayloadError, match="Missing"):
            verify_payload({"_signature": "abc"}, b"k")


# ── encrypt / decrypt round-trip ────────────────────────


class TestEncryptDecrypt:
    def test_round_trip(self):
        key = b"encryption-key-32-bytes-long-ok!"
        data = {"secret": "value", "list": [1, 2, 3]}
        encrypted = encrypt_data(data, key)
        assert encrypted.startswith("cup_enc:")
        result = decrypt_data(encrypted, key)
        assert result == data

    def test_wrong_key_fails(self):
        data = {"x": 1}
        encrypted = encrypt_data(data, b"key-a")
        with pytest.raises(SecurePayloadError, match="HMAC mismatch"):
            decrypt_data(encrypted, b"key-b")

    def test_tampered_ciphertext_fails(self):
        data = {"x": 1}
        encrypted = encrypt_data(data, b"key")
        # Flip a character in the ciphertext portion
        parts = encrypted.split(":", 1)
        mangled = parts[0] + ":" + parts[1][:-2] + ("AA" if parts[1][-2:] != "AA" else "BB")
        with pytest.raises(SecurePayloadError):
            decrypt_data(mangled, b"key")

    def test_not_encrypted_raises(self):
        with pytest.raises(SecurePayloadError, match="missing cup_enc"):
            decrypt_data("plain text", b"key")

    def test_different_encryptions_differ(self):
        # Random salt/nonce means same data encrypts differently each time
        key = b"key"
        data = {"a": 1}
        e1 = encrypt_data(data, key)
        e2 = encrypt_data(data, key)
        assert e1 != e2  # Different random salt/nonce
        # But both decrypt to same data
        assert decrypt_data(e1, key) == decrypt_data(e2, key)

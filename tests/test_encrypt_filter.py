"""Tests for codeupipe.core.encrypt_filter — EncryptFilter."""

import pytest

from codeupipe import Payload
from codeupipe.core.encrypt_filter import EncryptFilter
from codeupipe.core.decrypt_filter import DecryptFilter
from codeupipe.core.secure import SecurePayloadError


class TestEncryptFilter:
    @pytest.mark.asyncio
    async def test_encrypt_decrypt_pipeline(self):
        key = b"pipeline-encryption-key"
        data = {"db_url": "postgres://...", "api_key": "sk-..."}

        encrypted = await EncryptFilter(key=key).call(Payload(data))
        assert encrypted.get("_encrypted") is not None
        assert encrypted.get("_encrypted").startswith("cup_enc:")

        decrypted = await DecryptFilter(key=key).call(encrypted)
        assert decrypted.get("db_url") == "postgres://..."
        assert decrypted.get("api_key") == "sk-..."

    @pytest.mark.asyncio
    async def test_encrypt_produces_string(self):
        key = b"enc-key"
        result = await EncryptFilter(key=key).call(Payload({"x": 1}))
        assert isinstance(result.get("_encrypted"), str)

    @pytest.mark.asyncio
    async def test_different_encryptions_differ(self):
        key = b"enc-key"
        p = Payload({"x": 1})
        r1 = await EncryptFilter(key=key).call(p)
        r2 = await EncryptFilter(key=key).call(p)
        assert r1.get("_encrypted") != r2.get("_encrypted")

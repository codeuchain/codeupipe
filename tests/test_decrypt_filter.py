"""Tests for codeupipe.core.decrypt_filter — DecryptFilter."""

import pytest

from codeupipe import Payload
from codeupipe.core.encrypt_filter import EncryptFilter
from codeupipe.core.decrypt_filter import DecryptFilter
from codeupipe.core.secure import SecurePayloadError


class TestDecryptFilter:
    @pytest.mark.asyncio
    async def test_decrypt_missing_raises(self):
        with pytest.raises(SecurePayloadError, match="missing _encrypted"):
            await DecryptFilter(key=b"k").call(Payload({"no_data": True}))

    @pytest.mark.asyncio
    async def test_wrong_key_decrypt_raises(self):
        encrypted = await EncryptFilter(key=b"key-a").call(Payload({"x": 1}))
        with pytest.raises(SecurePayloadError, match="HMAC mismatch"):
            await DecryptFilter(key=b"key-b").call(encrypted)

    @pytest.mark.asyncio
    async def test_round_trip(self):
        key = b"round-trip-key"
        data = {"secret": "value", "nested": {"a": [1, 2, 3]}}
        encrypted = await EncryptFilter(key=key).call(Payload(data))
        decrypted = await DecryptFilter(key=key).call(encrypted)
        assert decrypted.get("secret") == "value"
        assert decrypted.get("nested") == {"a": [1, 2, 3]}

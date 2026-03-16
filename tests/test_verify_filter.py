"""Tests for codeupipe.core.verify_filter — VerifyFilter."""

import pytest

from codeupipe import Payload
from codeupipe.core.secure import SecurePayloadError
from codeupipe.core.sign_filter import SignFilter
from codeupipe.core.verify_filter import VerifyFilter


class TestVerifyFilter:
    @pytest.mark.asyncio
    async def test_missing_sealed_raises(self):
        f = VerifyFilter(key=b"k")
        with pytest.raises(SecurePayloadError, match="missing _sealed"):
            await f.call(Payload({"not_sealed": True}))

    @pytest.mark.asyncio
    async def test_tampered_sealed_raises(self):
        key = b"k"
        signed = await SignFilter(key=key).call(Payload({"x": 1}))
        # Tamper
        sealed = dict(signed.get("_sealed"))
        sealed["_data"]["x"] = 999
        tampered = Payload({"_sealed": sealed})
        with pytest.raises(SecurePayloadError, match="tampered"):
            await VerifyFilter(key=key).call(tampered)

    @pytest.mark.asyncio
    async def test_verify_restores_data(self):
        key = b"verify-key"
        data = {"name": "codeupipe", "version": 10}
        signed = await SignFilter(key=key).call(Payload(data))
        restored = await VerifyFilter(key=key).call(signed)
        assert restored.get("name") == "codeupipe"
        assert restored.get("version") == 10

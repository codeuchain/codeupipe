"""Tests for codeupipe.core.sign_filter — SignFilter."""

import pytest

from codeupipe import Payload
from codeupipe.core.sign_filter import SignFilter
from codeupipe.core.verify_filter import VerifyFilter


class TestSignFilter:
    @pytest.mark.asyncio
    async def test_sign_produces_sealed(self):
        f = SignFilter(key=b"my-key")
        p = Payload({"user": "alice", "score": 99})
        result = await f.call(p)
        assert result.get("_sealed") is not None
        sealed = result.get("_sealed")
        assert "_signature" in sealed
        assert "_data" in sealed

    @pytest.mark.asyncio
    async def test_sign_verify_pipeline(self):
        key = b"shared-secret"
        data = {"action": "deploy", "target": "production"}

        signed = await SignFilter(key=key).call(Payload(data))
        restored = await VerifyFilter(key=key).call(signed)

        assert restored.get("action") == "deploy"
        assert restored.get("target") == "production"

    @pytest.mark.asyncio
    async def test_no_timestamp(self):
        f = SignFilter(key=b"k", include_timestamp=False)
        result = await f.call(Payload({"x": 1}))
        sealed = result.get("_sealed")
        assert "_signed_at" not in sealed

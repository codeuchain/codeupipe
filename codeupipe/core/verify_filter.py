"""VerifyFilter — verifies HMAC signature and unpacks original payload data."""

from typing import Optional

from .payload import Payload
from .secure import SecurePayloadError, verify_payload


class VerifyFilter:
    """Filter that verifies a signed payload and unpacks the original data.

    Expects a payload with ``_sealed`` containing the signed envelope.

    Usage::

        pipeline.add(VerifyFilter(key=my_secret_key), "verify_input")
    """

    def __init__(self, key: bytes, *, max_age: Optional[float] = None):
        self._key = key
        self._max_age = max_age

    async def call(self, payload: "Payload") -> "Payload":
        sealed = payload.get("_sealed")
        if sealed is None:
            raise SecurePayloadError("Payload missing _sealed envelope")
        # Make a mutable copy since verify_payload pops _signature
        envelope = dict(sealed)
        data = verify_payload(envelope, self._key, max_age=self._max_age)
        return Payload(data)

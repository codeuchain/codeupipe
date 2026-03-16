"""SignFilter — HMAC-SHA256 signs payload data at a pipeline boundary."""

from typing import Optional

from .payload import Payload
from .secure import seal_payload


class SignFilter:
    """Filter that HMAC-signs the payload at a pipeline boundary.

    Reads all payload data, signs it, and returns a new payload
    containing the signed envelope under ``_sealed``.

    Usage::

        pipeline.add(SignFilter(key=my_secret_key), "sign_output")
    """

    def __init__(self, key: bytes, *, include_timestamp: bool = True):
        self._key = key
        self._timestamp = include_timestamp

    async def call(self, payload: "Payload") -> "Payload":
        data = payload.to_dict()
        sealed = seal_payload(data, self._key, timestamp=self._timestamp)
        return Payload({"_sealed": sealed})

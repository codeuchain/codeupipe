"""DecryptFilter — decrypts payload data encrypted by EncryptFilter."""

from .payload import Payload
from .secure import SecurePayloadError, decrypt_data


class DecryptFilter:
    """Filter that decrypts a payload encrypted by EncryptFilter.

    Expects ``_encrypted`` in the payload.

    Usage::

        pipeline.add(DecryptFilter(key=my_secret_key), "decrypt_input")
    """

    def __init__(self, key: bytes):
        self._key = key

    async def call(self, payload: "Payload") -> "Payload":
        encrypted = payload.get("_encrypted")
        if encrypted is None:
            raise SecurePayloadError("Payload missing _encrypted field")
        data = decrypt_data(encrypted, self._key)
        return Payload(data)

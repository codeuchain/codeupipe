"""EncryptFilter — encrypts entire payload to a single authenticated string."""

from .payload import Payload
from .secure import encrypt_data


class EncryptFilter:
    """Filter that encrypts the entire payload to a single string.

    Returns a payload with ``_encrypted`` containing the ciphertext.

    Usage::

        pipeline.add(EncryptFilter(key=my_secret_key), "encrypt_output")
    """

    def __init__(self, key: bytes):
        self._key = key

    async def call(self, payload: "Payload") -> "Payload":
        data = payload.to_dict()
        encrypted = encrypt_data(data, self._key)
        return Payload({"_encrypted": encrypted})

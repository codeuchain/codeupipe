"""CleanupSessionLink — Teardown provider, session, and client.

Supports both the new provider-based lifecycle and legacy
direct session/client cleanup for backward compatibility.

Input:  provider (optional), session (optional), client (optional)
Output: cleaned_up (bool)
"""

from codeupipe import Payload


class CleanupSessionLink:
    """Teardown provider (or legacy session/client) gracefully."""

    async def call(self, payload: Payload) -> Payload:
        # New: provider-based cleanup
        provider = payload.get("provider")
        if provider and hasattr(provider, "stop"):
            await provider.stop()
            return payload.insert("cleaned_up", True)

        # Legacy: direct session/client cleanup
        session = payload.get("session")
        if session:
            await session.destroy()

        client = payload.get("client")
        if client:
            await client.stop()

        return payload.insert("cleaned_up", True)

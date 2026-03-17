"""RED PHASE — Tests for CleanupSessionLink.

CleanupSessionLink tears down the session and stops the client.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from codeupipe import Payload

from codeupipe.ai.filters.session_cleanup import CleanupSessionLink


@pytest.mark.unit
class TestCleanupSessionLink:
    """Unit tests for CleanupSessionLink."""

    @pytest.mark.asyncio
    async def test_destroys_session(self):
        """Link calls session.destroy()."""
        link = CleanupSessionLink()

        mock_session = MagicMock()
        mock_session.destroy = AsyncMock()
        mock_client = MagicMock()
        mock_client.stop = AsyncMock()

        ctx = Payload({"session": mock_session, "client": mock_client})
        await link.call(ctx)

        mock_session.destroy.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stops_client(self):
        """Link calls client.stop()."""
        link = CleanupSessionLink()

        mock_session = MagicMock()
        mock_session.destroy = AsyncMock()
        mock_client = MagicMock()
        mock_client.stop = AsyncMock()

        ctx = Payload({"session": mock_session, "client": mock_client})
        await link.call(ctx)

        mock_client.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_marks_cleaned_up(self):
        """Link sets cleaned_up=True on context."""
        link = CleanupSessionLink()

        mock_session = MagicMock()
        mock_session.destroy = AsyncMock()
        mock_client = MagicMock()
        mock_client.stop = AsyncMock()

        ctx = Payload({"session": mock_session, "client": mock_client})
        result = await link.call(ctx)

        assert result.get("cleaned_up") is True

    @pytest.mark.asyncio
    async def test_handles_missing_session_gracefully(self):
        """Link doesn't crash if session is missing."""
        link = CleanupSessionLink()

        mock_client = MagicMock()
        mock_client.stop = AsyncMock()

        ctx = Payload({"client": mock_client})
        result = await link.call(ctx)

        assert result.get("cleaned_up") is True

    @pytest.mark.asyncio
    async def test_handles_missing_client_gracefully(self):
        """Link doesn't crash if client is missing."""
        link = CleanupSessionLink()
        ctx = Payload({})

        result = await link.call(ctx)
        assert result.get("cleaned_up") is True

"""Tests for middleware — logging and timing."""

import logging

import pytest
from codeupipe import Payload

from codeupipe.ai.hooks.logging_hook import LoggingMiddleware
from codeupipe.ai.hooks.timing_hook import TimingMiddleware


class _MockFilter:
    """Lightweight stand-in for a real filter to supply a name."""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name


@pytest.mark.unit
class TestLoggingMiddleware:
    """Unit tests for LoggingMiddleware."""

    @pytest.mark.asyncio
    async def test_before_logs_starting(self, caplog):
        """before() logs a starting message."""
        mw = LoggingMiddleware()
        filt = _MockFilter("test_link")
        with caplog.at_level(logging.INFO, logger="codeupipe.ai"):
            await mw.before(filt, Payload({}))
        assert "test_link" in caplog.text
        assert "starting" in caplog.text

    @pytest.mark.asyncio
    async def test_after_logs_completed(self, caplog):
        """after() logs a completion message."""
        mw = LoggingMiddleware()
        filt = _MockFilter("test_link")
        with caplog.at_level(logging.INFO, logger="codeupipe.ai"):
            await mw.after(filt, Payload({}))
        assert "completed" in caplog.text

    @pytest.mark.asyncio
    async def test_on_error_logs_failure(self, caplog):
        """on_error() logs the error."""
        mw = LoggingMiddleware()
        filt = _MockFilter("test_link")
        with caplog.at_level(logging.ERROR, logger="codeupipe.ai"):
            await mw.on_error(filt, ValueError("boom"), Payload({}))
        assert "failed" in caplog.text
        assert "boom" in caplog.text


@pytest.mark.unit
class TestTimingMiddleware:
    """Unit tests for TimingMiddleware."""

    @pytest.mark.asyncio
    async def test_measures_elapsed_time(self, caplog):
        """Timing middleware logs elapsed time."""
        mw = TimingMiddleware()
        filt = _MockFilter("test_link")
        with caplog.at_level(logging.INFO, logger="codeupipe.ai"):
            await mw.before(filt, Payload({}))
            await mw.after(filt, Payload({}))
        assert "took" in caplog.text

    @pytest.mark.asyncio
    async def test_measures_error_time(self, caplog):
        """Timing middleware logs elapsed time on error."""
        mw = TimingMiddleware()
        filt = _MockFilter("test_link")
        with caplog.at_level(logging.WARNING, logger="codeupipe.ai"):
            await mw.before(filt, Payload({}))
            await mw.on_error(filt, RuntimeError("fail"), Payload({}))
        assert "failed after" in caplog.text

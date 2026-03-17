"""Logging Middleware — logs link execution start/finish/errors.

Adapted for codeupipe Hook API. Extracts filter name from the filter
object passed by the pipeline.
"""

import logging
from typing import Optional

from codeupipe import Payload
from codeupipe.core.hook import Hook


logger = logging.getLogger("codeupipe.ai")


def _filter_name(f: object) -> str:
    """Extract a human-readable name from a filter or pipeline step."""
    if f is None:
        return "pipeline"
    if hasattr(f, "name"):
        return f.name
    return type(f).__name__


class LoggingMiddleware(Hook):
    """Log each link's execution lifecycle."""

    async def before(self, filter: Optional[object], payload: Payload) -> None:
        logger.info("▶ [%s] starting", _filter_name(filter))

    async def after(self, filter: Optional[object], payload: Payload) -> None:
        logger.info("✓ [%s] completed", _filter_name(filter))

    async def on_error(self, filter: Optional[object], err: Exception, payload: Payload) -> None:
        logger.error("✗ [%s] failed: %s", _filter_name(filter), err)

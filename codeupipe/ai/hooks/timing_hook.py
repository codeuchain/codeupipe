"""Timing Middleware — measures link execution duration.

Adapted for codeupipe Hook API. Extracts filter name from the filter
object passed by the pipeline.
"""

import logging
import time
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


class TimingMiddleware(Hook):
    """Measure and log execution time for each link."""

    def __init__(self) -> None:
        self._start_times: dict[str, float] = {}

    async def before(self, filter: Optional[object], payload: Payload) -> None:
        self._start_times[_filter_name(filter)] = time.perf_counter()

    async def after(self, filter: Optional[object], payload: Payload) -> None:
        name = _filter_name(filter)
        elapsed = time.perf_counter() - self._start_times.pop(name, 0)
        logger.info("⏱ [%s] took %.3fs", name, elapsed)

    async def on_error(self, filter: Optional[object], err: Exception, payload: Payload) -> None:
        name = _filter_name(filter)
        elapsed = time.perf_counter() - self._start_times.pop(name, 0)
        logger.warning("⏱ [%s] failed after %.3fs: %s", name, elapsed, err)

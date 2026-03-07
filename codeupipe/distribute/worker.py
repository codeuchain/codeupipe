"""
WorkerPool: Execute callables in thread or process pools.

Use inside filters for CPU-bound or blocking work without stalling
the async pipeline event loop.
"""

import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Any, Callable, List, Optional

__all__ = ["WorkerPool"]


class WorkerPool:
    """Execute callables in a thread or process pool.

    Usage inside a filter:
        pool = WorkerPool("thread", max_workers=4)

        class HeavyFilter:
            async def call(self, payload):
                result = await pool.run(expensive_fn, payload.get("data"))
                return payload.insert("result", result)
    """

    def __init__(self, kind: str = "thread", max_workers: Optional[int] = None):
        if kind == "thread":
            self._executor = ThreadPoolExecutor(max_workers=max_workers)
        elif kind == "process":
            self._executor = ProcessPoolExecutor(max_workers=max_workers)
        else:
            raise ValueError(f"Unknown pool kind '{kind}'. Use 'thread' or 'process'.")
        self._kind = kind

    async def run(self, fn: Callable, *args: Any) -> Any:
        """Run a callable in the pool, returning the result."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, fn, *args)

    async def map(self, fn: Callable, items: List[Any]) -> List[Any]:
        """Run fn(item) for each item concurrently in the pool."""
        loop = asyncio.get_running_loop()
        futures = [loop.run_in_executor(self._executor, fn, item) for item in items]
        return list(await asyncio.gather(*futures))

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the pool."""
        self._executor.shutdown(wait=wait)

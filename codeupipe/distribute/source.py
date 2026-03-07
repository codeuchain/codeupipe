"""
Source Adapters: Feed payloads into Pipeline.stream() from external sources.

Built-in adapters use only stdlib. Custom adapters implement the async iterator
protocol — any async iterable of Payload works with pipeline.stream().
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..core.payload import Payload

__all__ = ["IterableSource", "FileSource"]


class IterableSource:
    """Wrap a list of dicts or Payloads as an async payload stream.

    Usage:
        source = IterableSource([{"x": 1}, {"x": 2}, {"x": 3}])
        async for result in pipeline.stream(source):
            print(result)
    """

    def __init__(self, items: List[Union[Dict[str, Any], Payload]]):
        self._items = items
        self._index = 0

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self) -> Payload:
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        if isinstance(item, Payload):
            return item
        return Payload(item)


class FileSource:
    """Read lines from a file as payloads — each line becomes a Payload.

    Usage:
        source = FileSource("data.txt", key="line")
        async for result in pipeline.stream(source):
            print(result.get("line"))
    """

    def __init__(self, path: str, *, key: str = "line"):
        self._path = Path(path)
        self._key = key
        self._lines: List[str] = []
        self._index = 0

    def __aiter__(self):
        self._lines = self._path.read_text().splitlines()
        self._index = 0
        return self

    async def __anext__(self) -> Payload:
        if self._index >= len(self._lines):
            raise StopAsyncIteration
        line = self._lines[self._index]
        self._index += 1
        return Payload({self._key: line, "line_number": self._index})

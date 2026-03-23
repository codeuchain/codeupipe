"""Immutable result from a single ADB invocation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


__all__ = ["AdbResult"]


@dataclass(frozen=True)
class AdbResult:
    """Immutable result from a single ``adb`` invocation.

    Mirrors ``BrowserResult`` from ``codeupipe.browser``.
    """

    stdout: str
    stderr: str
    returncode: int
    command: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def output(self) -> str:
        """Primary output — stdout when successful, stderr on failure."""
        return self.stdout if self.ok else self.stderr

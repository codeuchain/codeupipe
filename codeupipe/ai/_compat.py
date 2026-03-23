"""Python version compatibility shims for codeupipe.ai.

Provides backports for stdlib additions that landed in Python 3.11+.
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum  # noqa: F401
else:
    from enum import Enum

    class StrEnum(str, Enum):
        """Backport of enum.StrEnum for Python < 3.11.

        Members compare equal to and hash the same as their string value,
        and str(member) returns the value (not 'ClassName.MEMBER_NAME').
        """

        def __str__(self) -> str:  # type: ignore[override]
            return self.value

        def __format__(self, format_spec: str) -> str:
            return format(self.value, format_spec)

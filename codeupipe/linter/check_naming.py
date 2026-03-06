"""
CheckNaming: CUP007 — snake_case file name enforcement.
"""

import re

from codeupipe import Payload


_SNAKE_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")


def _to_snake(name: str) -> str:
    """Convert PascalCase or mixed to snake_case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return re.sub(r"[\s\-]+", "_", s).lower()


class CheckNaming:
    """
    Filter (sync): Check that file names follow snake_case convention.

    Input keys:
        - files (list[dict]): file analyses from ScanDirectory
        - issues (list): accumulated lint issues

    Output keys (modified):
        - issues (list): with CUP007 violations appended
    """

    def call(self, payload: Payload) -> Payload:
        files = payload.get("files", [])
        issues = list(payload.get("issues", []))

        for info in files:
            stem = info["stem"]
            rel = info["path"]
            if not _SNAKE_RE.match(stem):
                expected = _to_snake(stem)
                issues.append((
                    "CUP007", "warning", rel,
                    f"File name '{stem}.py' is not snake_case. "
                    f"Expected: '{expected}.py'"
                ))

        return payload.insert("issues", issues)

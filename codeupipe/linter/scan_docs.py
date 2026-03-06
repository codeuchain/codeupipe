"""
ScanDocs: Extract cup:ref markers from markdown files.

Scans all .md files in a directory for <!-- cup:ref ... --> markers
and produces a list of doc-code references for downstream validation.
"""

import re
from pathlib import Path

from codeupipe import Payload


_MARKER_RE = re.compile(
    r"<!--\s*cup:ref\s+(.*?)\s*-->",
    re.IGNORECASE,
)

_ATTR_RE = re.compile(r"(\w+)=(\S+)")


class ScanDocs:
    """
    Filter (sync): Scan .md files for cup:ref markers.

    Input keys:
        - directory (str): root directory to scan

    Output keys (added):
        - doc_refs (list[dict]): extracted references, each with:
            file, symbols, hash, doc_path, line
    """

    def call(self, payload: Payload) -> Payload:
        directory = Path(payload.get("directory", "."))
        refs = []

        for md_path in sorted(directory.glob("*.md")):
            content = md_path.read_text(encoding="utf-8", errors="replace")
            for line_num, line in enumerate(content.splitlines(), start=1):
                match = _MARKER_RE.search(line)
                if not match:
                    continue

                attrs_str = match.group(1)
                attrs = dict(_ATTR_RE.findall(attrs_str))

                if "file" not in attrs:
                    continue

                symbols_raw = attrs.get("symbols", "")
                symbols = [s for s in symbols_raw.split(",") if s]

                refs.append({
                    "file": attrs["file"],
                    "symbols": symbols,
                    "hash": attrs.get("hash", None),
                    "doc_path": str(md_path),
                    "line": line_num,
                })

        return payload.insert("doc_refs", refs)

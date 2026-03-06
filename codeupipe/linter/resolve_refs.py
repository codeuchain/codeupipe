"""
ResolveRefs: Verify source files exist and compute current content hashes.

Takes the doc_refs from ScanDocs and enriches each with existence checks
and current file content hashes for drift detection.
"""

import hashlib
from pathlib import Path

from codeupipe import Payload


class ResolveRefs:
    """
    Filter (sync): Resolve file references and compute current hashes.

    Input keys:
        - directory (str): root directory
        - doc_refs (list[dict]): from ScanDocs

    Output keys (added):
        - resolved_refs (list[dict]): enriched refs with:
            exists (bool), current_hash (str|None), abs_path (str)
    """

    def call(self, payload: Payload) -> Payload:
        directory = Path(payload.get("directory", "."))
        doc_refs = payload.get("doc_refs", [])
        resolved = []

        for ref in doc_refs:
            abs_path = directory / ref["file"]
            exists = abs_path.is_file()

            current_hash = None
            if exists:
                content = abs_path.read_bytes()
                current_hash = hashlib.sha256(content).hexdigest()[:7]

            resolved.append({
                **ref,
                "exists": exists,
                "current_hash": current_hash,
                "abs_path": str(abs_path),
            })

        return payload.insert("resolved_refs", resolved)

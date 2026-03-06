"""
CheckIndex: Verify INDEX.md covers the project's key source files.

Scans the project for Python source files under the package directory
and checks that each is referenced (directly or via its parent __init__)
in cup:ref markers within INDEX.md. Reports unmapped files as issues.
"""

from pathlib import Path

from codeupipe import Payload


# Files/patterns that don't need explicit index coverage
_IGNORE_PATTERNS = {
    "__pycache__",
    ".pyc",
    "py.typed",
}


class CheckIndex:
    """
    Filter (sync): Verify INDEX.md maps the project structure.

    Input keys:
        - directory (str): root directory to scan
        - doc_refs (list[dict]): from ScanDocs (all cup:ref markers)

    Output keys (added):
        - index_issues (list[dict]): unmapped files, each with:
            file (str), message (str)
    """

    def call(self, payload: Payload) -> Payload:
        directory = Path(payload.get("directory", "."))
        doc_refs = payload.get("doc_refs", [])

        # Collect all file paths referenced in cup:ref markers across all docs
        referenced = set()
        for ref in doc_refs:
            referenced.add(ref["file"])

        # Discover key source files: __init__.py is the structural anchor,
        # plus any .py files that define public exports (non-__init__)
        package_dir = directory / "codeupipe"
        if not package_dir.is_dir():
            return payload.insert("index_issues", [])

        source_files = set()
        for py_file in sorted(package_dir.rglob("*.py")):
            rel = str(py_file.relative_to(directory))

            # Skip __pycache__ and other noise
            if any(p in rel for p in _IGNORE_PATTERNS):
                continue

            # Skip individual filter files inside linter/ and converter/
            # (the __init__.py for those packages is sufficient coverage)
            parts = py_file.parts
            in_subpackage = False
            for sub in ("linter", "converter"):
                if sub in parts:
                    sub_idx = parts.index(sub)
                    # If it's deeper than the direct children, always skip
                    if len(parts) > sub_idx + 2:
                        in_subpackage = True
                    # Direct children that aren't __init__.py or *_pipeline.py
                    elif (len(parts) == sub_idx + 2
                          and py_file.name != "__init__.py"
                          and not py_file.name.endswith("_pipeline.py")):
                        in_subpackage = True

            if in_subpackage:
                continue

            source_files.add(rel)

        # Check which source files are not referenced
        issues = []
        for src in sorted(source_files):
            if src not in referenced:
                issues.append({
                    "file": src,
                    "message": f"Source file '{src}' not referenced in any cup:ref marker",
                })

        return payload.insert("index_issues", issues)

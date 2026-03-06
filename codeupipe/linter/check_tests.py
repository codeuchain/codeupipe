"""
CheckTests: CUP002 — missing test file detection.
"""

from pathlib import Path

from codeupipe import Payload


class CheckTests:
    """
    Filter (sync): Flag components that have no corresponding test file.

    Input keys:
        - files (list[dict]): file analyses from ScanDirectory
        - issues (list): accumulated lint issues
        - tests_dir (str, optional): path to tests directory (default: "tests")

    Output keys (modified):
        - issues (list): with CUP002 violations appended
    """

    def call(self, payload: Payload) -> Payload:
        files = payload.get("files", [])
        issues = list(payload.get("issues", []))
        tests_dir = payload.get("tests_dir", "tests")

        for info in files:
            if info["error"]:
                continue

            stem = info["stem"]
            test_file = Path(tests_dir) / f"test_{stem}.py"

            has_components = any(
                ctype is not None for _, ctype, _ in info["classes"]
            )
            has_builders = any(
                f.startswith("build_") for f in info["functions"]
            )

            if (has_components or has_builders) and not test_file.exists():
                issues.append((
                    "CUP002", "warning", info["path"],
                    f"No test file found. Expected: {test_file}"
                ))

        return payload.insert("issues", issues)

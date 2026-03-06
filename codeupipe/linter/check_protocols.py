"""
CheckProtocols: CUP003–CUP006 — protocol compliance enforcement.
"""

from codeupipe import Payload


_HOOK_METHODS = {"before", "after", "on_error"}


class CheckProtocols:
    """
    Filter (sync): Verify each component has its required protocol methods.

    Rules:
        CUP003: Filter missing call()
        CUP004: Tap missing observe()
        CUP005: StreamFilter missing stream()
        CUP006: Hook missing lifecycle methods (before, after, on_error)

    Input keys:
        - files (list[dict]): file analyses from ScanDirectory
        - issues (list): accumulated lint issues

    Output keys (modified):
        - issues (list): with CUP003–CUP006 violations appended
    """

    def call(self, payload: Payload) -> Payload:
        files = payload.get("files", [])
        issues = list(payload.get("issues", []))

        for info in files:
            if info["error"]:
                issues.append((
                    "CUP000", "error", info["path"],
                    f"Syntax error: {info['error']}"
                ))
                continue

            for class_name, ctype, methods in info["classes"]:
                if ctype is None:
                    continue

                if ctype == "filter" and "call" not in methods:
                    issues.append((
                        "CUP003", "error", info["path"],
                        f"Filter '{class_name}' is missing call() method."
                    ))

                if ctype == "tap" and "observe" not in methods:
                    issues.append((
                        "CUP004", "error", info["path"],
                        f"Tap '{class_name}' is missing observe() method."
                    ))

                if ctype == "stream-filter" and "stream" not in methods:
                    issues.append((
                        "CUP005", "error", info["path"],
                        f"StreamFilter '{class_name}' is missing stream() method."
                    ))

                if ctype == "hook":
                    missing = _HOOK_METHODS - methods
                    if missing:
                        issues.append((
                            "CUP006", "error", info["path"],
                            f"Hook '{class_name}' is missing: "
                            f"{', '.join(sorted(missing))}. "
                            f"Hooks need before(), after(), and on_error()."
                        ))

        return payload.insert("issues", issues)

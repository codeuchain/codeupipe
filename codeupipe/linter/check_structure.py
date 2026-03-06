"""
CheckStructure: CUP001 — one component per file enforcement.
"""

from codeupipe import Payload


class CheckStructure:
    """
    Filter (sync): Flag files containing multiple CUP components.

    Input keys:
        - files (list[dict]): file analyses from ScanDirectory
        - issues (list): accumulated lint issues

    Output keys (modified):
        - issues (list): with CUP001 violations appended
    """

    def call(self, payload: Payload) -> Payload:
        files = payload.get("files", [])
        issues = list(payload.get("issues", []))

        for info in files:
            if info["error"]:
                continue

            component_classes = [
                (name, ctype)
                for name, ctype, _ in info["classes"]
                if ctype is not None
            ]
            if len(component_classes) > 1:
                names = [f"{n} ({t})" for n, t in component_classes]
                issues.append((
                    "CUP001", "error", info["path"],
                    f"Multiple components in one file: {', '.join(names)}. "
                    f"Use one component per file."
                ))

        return payload.insert("issues", issues)

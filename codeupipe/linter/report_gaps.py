"""
ReportGaps: Compute summary statistics and coverage gaps from coverage data.
"""

from codeupipe import Payload


class ReportGaps:
    """
    Filter (sync): Produce a human-readable summary from coverage data.

    Input keys:
        - coverage (list[dict]): from MapCoverage

    Output keys (added):
        - summary (dict): with keys:
            - total_components (int)
            - tested_components (int): components with at least one test
            - untested_components (int): components with zero tests
            - total_methods (int)
            - tested_methods (int)
            - untested_methods (int)
            - overall_pct (float): aggregate method coverage %
        - gaps (list[dict]): components with coverage < 100%, each with:
            - name (str)
            - kind (str)
            - file (str)
            - coverage_pct (float)
            - missing (list[str]): untested method names
    """

    def call(self, payload: Payload) -> Payload:
        coverage = payload.get("coverage", [])

        total_components = len(coverage)
        tested_components = sum(1 for c in coverage if c["has_test_file"])
        untested_components = total_components - tested_components

        total_methods = sum(len(c["methods"]) for c in coverage)
        tested_methods = sum(len(c["tested_methods"]) for c in coverage)
        untested_methods = total_methods - tested_methods

        overall_pct = (tested_methods / total_methods * 100) if total_methods > 0 else 100.0

        summary = {
            "total_components": total_components,
            "tested_components": tested_components,
            "untested_components": untested_components,
            "total_methods": total_methods,
            "tested_methods": tested_methods,
            "untested_methods": untested_methods,
            "overall_pct": round(overall_pct, 1),
        }

        gaps = []
        for c in coverage:
            if c["coverage_pct"] < 100.0:
                gaps.append({
                    "name": c["name"],
                    "kind": c["kind"],
                    "file": c["file"],
                    "coverage_pct": c["coverage_pct"],
                    "missing": c["untested_methods"],
                })

        payload = payload.insert("summary", summary)
        payload = payload.insert("gaps", gaps)
        return payload

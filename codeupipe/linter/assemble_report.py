"""
AssembleReport: Merge all analysis data into a unified health report.
"""

from datetime import datetime, timezone

from codeupipe import Payload


STALE_THRESHOLD_DAYS = 90


def _compute_health_score(coverage_pct: float, orphan_count: int,
                          stale_count: int, total_components: int) -> str:
    """Compute a letter grade health score.

    Scoring:
        Start at 100 points.
        - Deduct (100 - coverage_pct) * 0.6   (coverage is 60% of score)
        - Deduct orphan_ratio * 20              (orphans are 20% of score)
        - Deduct stale_ratio * 20               (staleness is 20% of score)

    Grades: A >= 90, B >= 80, C >= 70, D >= 60, F < 60
    """
    if total_components == 0:
        return "A"

    score = 100.0
    score -= (100.0 - coverage_pct) * 0.6
    orphan_ratio = orphan_count / total_components if total_components else 0
    score -= orphan_ratio * 20
    stale_ratio = stale_count / total_components if total_components else 0
    score -= stale_ratio * 20

    score = max(0.0, min(100.0, score))

    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"


class AssembleReport:
    """
    Filter (sync): Merge coverage, orphan, and git data into a unified report.

    Input keys:
        - coverage (list[dict]): from MapCoverage
        - summary (dict): from ReportGaps
        - gaps (list[dict]): from ReportGaps
        - orphaned_components (list[dict]): from DetectOrphans
        - orphaned_tests (list[dict]): from DetectOrphans
        - import_map (dict): from DetectOrphans
        - git_info (dict): from GitHistory
        - directory (str): component directory

    Output keys (added):
        - report (dict): unified report structure
    """

    def call(self, payload: Payload) -> Payload:
        coverage = payload.get("coverage", [])
        summary = payload.get("summary", {})
        gaps = payload.get("gaps", [])
        orphaned_components = payload.get("orphaned_components", [])
        orphaned_tests = payload.get("orphaned_tests", [])
        import_map = payload.get("import_map", {})
        git_info = payload.get("git_info", {})
        directory = payload.get("directory", "")

        orphaned_names = {o["name"] for o in orphaned_components}

        # Build enriched component list
        components = []
        for cov in coverage:
            file_path = cov["file"]
            git = git_info.get(file_path, {
                "last_modified": None,
                "last_author": None,
                "commit_count": 0,
                "days_since_change": None,
            })

            components.append({
                "name": cov["name"],
                "kind": cov["kind"],
                "file": file_path,
                "methods": cov["methods"],
                "coverage_pct": cov["coverage_pct"],
                "test_count": cov["test_count"],
                "untested_methods": cov["untested_methods"],
                "orphaned": cov["name"] in orphaned_names,
                "imported_by": import_map.get(cov["name"], []),
                "git": git,
            })

        # Detect stale files
        stale_files = []
        for file_path, info in git_info.items():
            days = info.get("days_since_change")
            if days is not None and days > STALE_THRESHOLD_DAYS:
                stale_files.append({
                    "file": file_path,
                    "days_since_change": days,
                    "last_modified": info.get("last_modified"),
                    "last_author": info.get("last_author"),
                })

        # Compute health score
        total = summary.get("total_components", 0)
        health_score = _compute_health_score(
            coverage_pct=summary.get("overall_pct", 100.0),
            orphan_count=len(orphaned_components),
            stale_count=len(stale_files),
            total_components=total,
        )

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "directory": directory,
            "components": components,
            "orphaned_components": orphaned_components,
            "orphaned_tests": orphaned_tests,
            "stale_files": stale_files,
            "summary": {
                **summary,
                "orphaned_count": len(orphaned_components),
                "orphaned_test_count": len(orphaned_tests),
                "stale_count": len(stale_files),
                "health_score": health_score,
            },
        }

        return payload.insert("report", report)

"""Tests for AssembleReport filter — RED phase first."""

from datetime import datetime

import pytest

from codeupipe import Payload
from codeupipe.linter.assemble_report import AssembleReport


def _cov(name, kind="filter", pct=100.0, has_test=True, test_count=5,
         methods=None, tested=None, untested=None):
    methods = methods if methods is not None else ["call"]
    tested = tested if tested is not None else methods
    untested = untested if untested is not None else []
    return {
        "name": name, "kind": kind,
        "file": f"/fake/{name.lower()}.py",
        "has_test_file": has_test, "test_count": test_count,
        "methods": methods, "tested_methods": tested,
        "untested_methods": untested, "coverage_pct": pct,
    }


class TestAssembleReport:
    """Unit tests for AssembleReport filter."""

    def test_assembles_basic_report(self):
        coverage = [_cov("Auth")]
        payload = Payload({
            "coverage": coverage,
            "summary": {"total_components": 1, "tested_components": 1,
                        "untested_components": 0, "total_methods": 1,
                        "tested_methods": 1, "untested_methods": 0, "overall_pct": 100.0},
            "gaps": [],
            "orphaned_components": [],
            "orphaned_tests": [],
            "import_map": {"Auth": ["pipeline.py"]},
            "git_info": {},
            "directory": "/fake",
        })
        result = AssembleReport().call(payload)
        report = result.get("report")

        assert "generated_at" in report
        assert report["directory"] == "/fake"
        assert isinstance(report["components"], list)
        assert len(report["components"]) == 1
        assert report["summary"]["health_score"] is not None

    def test_merges_git_info_into_components(self):
        coverage = [_cov("Auth")]
        git_info = {
            "/fake/auth.py": {
                "last_modified": "2026-03-01",
                "last_author": "jwink",
                "commit_count": 5,
                "days_since_change": 5,
            }
        }
        payload = Payload({
            "coverage": coverage,
            "summary": {"total_components": 1, "tested_components": 1,
                        "untested_components": 0, "total_methods": 1,
                        "tested_methods": 1, "untested_methods": 0, "overall_pct": 100.0},
            "gaps": [],
            "orphaned_components": [],
            "orphaned_tests": [],
            "import_map": {"Auth": ["pipeline.py"]},
            "git_info": git_info,
            "directory": "/fake",
        })
        result = AssembleReport().call(payload)
        comp = result.get("report")["components"][0]

        assert comp["git"]["last_modified"] == "2026-03-01"
        assert comp["git"]["last_author"] == "jwink"
        assert comp["git"]["commit_count"] == 5

    def test_merges_orphan_status(self):
        coverage = [_cov("Auth"), _cov("Dead")]
        payload = Payload({
            "coverage": coverage,
            "summary": {"total_components": 2, "tested_components": 2,
                        "untested_components": 0, "total_methods": 2,
                        "tested_methods": 2, "untested_methods": 0, "overall_pct": 100.0},
            "gaps": [],
            "orphaned_components": [{"name": "Dead", "kind": "filter", "file": "/fake/dead.py"}],
            "orphaned_tests": [],
            "import_map": {"Auth": ["pipeline.py"], "Dead": []},
            "git_info": {},
            "directory": "/fake",
        })
        result = AssembleReport().call(payload)
        comps = result.get("report")["components"]

        auth = next(c for c in comps if c["name"] == "Auth")
        dead = next(c for c in comps if c["name"] == "Dead")
        assert auth["orphaned"] is False
        assert dead["orphaned"] is True

    def test_merges_imported_by(self):
        coverage = [_cov("Auth")]
        payload = Payload({
            "coverage": coverage,
            "summary": {"total_components": 1, "tested_components": 1,
                        "untested_components": 0, "total_methods": 1,
                        "tested_methods": 1, "untested_methods": 0, "overall_pct": 100.0},
            "gaps": [],
            "orphaned_components": [],
            "orphaned_tests": [],
            "import_map": {"Auth": ["pipeline.py", "main.py"]},
            "git_info": {},
            "directory": "/fake",
        })
        result = AssembleReport().call(payload)
        comp = result.get("report")["components"][0]
        assert comp["imported_by"] == ["pipeline.py", "main.py"]

    def test_stale_files_detected(self):
        """Files with >90 days since change are marked stale."""
        coverage = [_cov("Old")]
        git_info = {
            "/fake/old.py": {
                "last_modified": "2025-01-01",
                "last_author": "someone",
                "commit_count": 1,
                "days_since_change": 120,
            }
        }
        payload = Payload({
            "coverage": coverage,
            "summary": {"total_components": 1, "tested_components": 1,
                        "untested_components": 0, "total_methods": 1,
                        "tested_methods": 1, "untested_methods": 0, "overall_pct": 100.0},
            "gaps": [],
            "orphaned_components": [],
            "orphaned_tests": [],
            "import_map": {},
            "git_info": git_info,
            "directory": "/fake",
        })
        result = AssembleReport().call(payload)
        report = result.get("report")
        assert len(report["stale_files"]) == 1
        assert report["stale_files"][0]["file"] == "/fake/old.py"

    def test_health_score_A(self):
        """100% coverage, no orphans, no stale → 'A'."""
        payload = Payload({
            "coverage": [_cov("A")],
            "summary": {"total_components": 1, "tested_components": 1,
                        "untested_components": 0, "total_methods": 1,
                        "tested_methods": 1, "untested_methods": 0, "overall_pct": 100.0},
            "gaps": [],
            "orphaned_components": [],
            "orphaned_tests": [],
            "import_map": {"A": ["p.py"]},
            "git_info": {},
            "directory": "/fake",
        })
        result = AssembleReport().call(payload)
        assert result.get("report")["summary"]["health_score"] == "A"

    def test_health_score_degrades_with_orphans(self):
        """Orphaned components should lower health score."""
        payload = Payload({
            "coverage": [_cov("A")],
            "summary": {"total_components": 1, "tested_components": 1,
                        "untested_components": 0, "total_methods": 1,
                        "tested_methods": 1, "untested_methods": 0, "overall_pct": 100.0},
            "gaps": [],
            "orphaned_components": [{"name": "A", "kind": "filter", "file": "/fake/a.py"}],
            "orphaned_tests": [],
            "import_map": {},
            "git_info": {},
            "directory": "/fake",
        })
        result = AssembleReport().call(payload)
        score = result.get("report")["summary"]["health_score"]
        assert score != "A"

    def test_health_score_degrades_with_low_coverage(self):
        """Low coverage lowers health score."""
        payload = Payload({
            "coverage": [_cov("A", pct=30.0, tested=[], untested=["call"])],
            "summary": {"total_components": 1, "tested_components": 0,
                        "untested_components": 1, "total_methods": 1,
                        "tested_methods": 0, "untested_methods": 1, "overall_pct": 30.0},
            "gaps": [{"name": "A", "kind": "filter", "file": "/f.py",
                      "coverage_pct": 30.0, "missing": ["call"]}],
            "orphaned_components": [],
            "orphaned_tests": [],
            "import_map": {},
            "git_info": {},
            "directory": "/fake",
        })
        result = AssembleReport().call(payload)
        score = result.get("report")["summary"]["health_score"]
        assert score in ("C", "D", "F")

    def test_empty_codebase(self):
        payload = Payload({
            "coverage": [],
            "summary": {"total_components": 0, "tested_components": 0,
                        "untested_components": 0, "total_methods": 0,
                        "tested_methods": 0, "untested_methods": 0, "overall_pct": 100.0},
            "gaps": [],
            "orphaned_components": [],
            "orphaned_tests": [],
            "import_map": {},
            "git_info": {},
            "directory": "/fake",
        })
        result = AssembleReport().call(payload)
        report = result.get("report")
        assert report["components"] == []
        assert report["summary"]["health_score"] == "A"

    def test_orphaned_tests_in_report(self):
        payload = Payload({
            "coverage": [],
            "summary": {"total_components": 0, "tested_components": 0,
                        "untested_components": 0, "total_methods": 0,
                        "tested_methods": 0, "untested_methods": 0, "overall_pct": 100.0},
            "gaps": [],
            "orphaned_components": [],
            "orphaned_tests": [{"file": "tests/test_old.py", "stem": "old"}],
            "import_map": {},
            "git_info": {},
            "directory": "/fake",
        })
        result = AssembleReport().call(payload)
        report = result.get("report")
        assert len(report["orphaned_tests"]) == 1

    def test_no_git_info_still_works(self):
        """Components with no git_info get null git fields."""
        coverage = [_cov("Auth")]
        payload = Payload({
            "coverage": coverage,
            "summary": {"total_components": 1, "tested_components": 1,
                        "untested_components": 0, "total_methods": 1,
                        "tested_methods": 1, "untested_methods": 0, "overall_pct": 100.0},
            "gaps": [],
            "orphaned_components": [],
            "orphaned_tests": [],
            "import_map": {},
            "git_info": {},
            "directory": "/fake",
        })
        result = AssembleReport().call(payload)
        comp = result.get("report")["components"][0]
        assert comp["git"]["last_modified"] is None
        assert comp["git"]["commit_count"] == 0

"""Tests for ReportGaps filter."""

import pytest

from codeupipe import Payload
from codeupipe.linter.report_gaps import ReportGaps


def _cov(name, kind="filter", pct=100.0, has_test=True, test_count=5,
         methods=None, tested=None, untested=None):
    methods = methods if methods is not None else ["call"]
    tested = tested if tested is not None else methods
    untested = untested if untested is not None else []
    return {
        "name": name,
        "kind": kind,
        "file": f"/fake/{name.lower()}.py",
        "has_test_file": has_test,
        "test_count": test_count,
        "methods": methods,
        "tested_methods": tested,
        "untested_methods": untested,
        "coverage_pct": pct,
    }


class TestReportGaps:
    """Unit tests for ReportGaps filter."""

    def test_all_covered(self):
        cov = [_cov("A"), _cov("B")]
        result = ReportGaps().call(Payload({"coverage": cov}))
        summary = result.get("summary")
        assert summary["total_components"] == 2
        assert summary["tested_components"] == 2
        assert summary["untested_components"] == 0
        assert summary["overall_pct"] == 100.0
        assert result.get("gaps") == []

    def test_partial_coverage(self):
        cov = [
            _cov("A", pct=100.0, methods=["call"], tested=["call"], untested=[]),
            _cov("B", pct=50.0, methods=["call", "extra"], tested=["call"], untested=["extra"]),
        ]
        result = ReportGaps().call(Payload({"coverage": cov}))
        summary = result.get("summary")
        assert summary["total_methods"] == 3
        assert summary["tested_methods"] == 2
        assert summary["untested_methods"] == 1
        assert summary["overall_pct"] == 66.7
        gaps = result.get("gaps")
        assert len(gaps) == 1
        assert gaps[0]["name"] == "B"
        assert "extra" in gaps[0]["missing"]

    def test_no_tests_at_all(self):
        cov = [_cov("A", pct=0.0, has_test=False, test_count=0,
                     methods=["call"], tested=[], untested=["call"])]
        result = ReportGaps().call(Payload({"coverage": cov}))
        summary = result.get("summary")
        assert summary["tested_components"] == 0
        assert summary["untested_components"] == 1
        assert summary["overall_pct"] == 0.0

    def test_empty_coverage(self):
        result = ReportGaps().call(Payload({"coverage": []}))
        summary = result.get("summary")
        assert summary["total_components"] == 0
        assert summary["overall_pct"] == 100.0
        assert result.get("gaps") == []

    def test_gaps_include_file_and_kind(self):
        cov = [_cov("Auth", kind="filter", pct=50.0,
                     methods=["call", "validate"], tested=["call"], untested=["validate"])]
        result = ReportGaps().call(Payload({"coverage": cov}))
        gap = result.get("gaps")[0]
        assert gap["kind"] == "filter"
        assert "auth" in gap["file"].lower()
        assert gap["coverage_pct"] == 50.0

    def test_multiple_gaps(self):
        cov = [
            _cov("A", pct=50.0, untested=["x"]),
            _cov("B", pct=0.0, untested=["y", "z"]),
            _cov("C", pct=100.0),
        ]
        result = ReportGaps().call(Payload({"coverage": cov}))
        assert len(result.get("gaps")) == 2

    def test_summary_preserves_payload(self):
        result = ReportGaps().call(Payload({"coverage": [], "extra": "kept"}))
        assert result.get("extra") == "kept"
        assert result.get("summary") is not None
        assert result.get("gaps") is not None

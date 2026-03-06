"""Tests for MapCoverage filter."""

import pytest

from codeupipe import Payload
from codeupipe.linter.map_coverage import MapCoverage


def _comp(name, kind="filter", methods=None, stem="auth"):
    return {
        "file": f"/fake/{stem}.py",
        "stem": stem,
        "name": name,
        "kind": kind,
        "methods": methods or ["call"],
    }


def _test_entry(stem, test_methods=None, referenced=None, imports=None):
    return {
        "test_file": f"tests/test_{stem}.py",
        "stem": stem,
        "test_methods": test_methods or ["test_happy"],
        "referenced_methods": referenced or set(),
        "imports": imports or set(),
    }


class TestMapCoverage:
    """Unit tests for MapCoverage filter."""

    def test_fully_covered_filter(self):
        comps = [_comp("Auth", methods=["call", "validate"])]
        tests = [_test_entry("auth", referenced={"call", "validate"})]
        result = MapCoverage().call(Payload({"components": comps, "test_map": tests}))
        cov = result.get("coverage")
        assert len(cov) == 1
        assert cov[0]["coverage_pct"] == 100.0
        assert cov[0]["untested_methods"] == []
        assert cov[0]["has_test_file"] is True

    def test_partially_covered_filter(self):
        comps = [_comp("Auth", methods=["call", "validate", "refresh"])]
        tests = [_test_entry("auth", referenced={"call"})]
        result = MapCoverage().call(Payload({"components": comps, "test_map": tests}))
        cov = result.get("coverage")[0]
        assert cov["coverage_pct"] == 33.3
        assert "validate" in cov["untested_methods"]
        assert "refresh" in cov["untested_methods"]

    def test_uncovered_filter(self):
        comps = [_comp("Auth", methods=["call"])]
        result = MapCoverage().call(Payload({"components": comps, "test_map": []}))
        cov = result.get("coverage")[0]
        assert cov["coverage_pct"] == 0.0
        assert cov["has_test_file"] is False
        assert cov["untested_methods"] == ["call"]

    def test_builder_covered_by_import(self):
        comps = [_comp("build_auth_pipeline", kind="builder", methods=[], stem="pipeline")]
        tests = [_test_entry("pipeline", imports={"build_auth_pipeline"})]
        result = MapCoverage().call(Payload({"components": comps, "test_map": tests}))
        cov = result.get("coverage")[0]
        assert cov["coverage_pct"] == 100.0

    def test_builder_not_imported(self):
        comps = [_comp("build_auth_pipeline", kind="builder", methods=[], stem="pipeline")]
        tests = [_test_entry("pipeline", imports={"SomeOther"})]
        result = MapCoverage().call(Payload({"components": comps, "test_map": tests}))
        cov = result.get("coverage")[0]
        assert cov["coverage_pct"] == 0.0

    def test_multiple_components(self):
        comps = [
            _comp("A", methods=["call"], stem="a"),
            _comp("B", methods=["observe"], stem="b"),
        ]
        tests = [_test_entry("a", referenced={"call"})]
        result = MapCoverage().call(Payload({"components": comps, "test_map": tests}))
        cov = result.get("coverage")
        assert cov[0]["coverage_pct"] == 100.0
        assert cov[1]["coverage_pct"] == 0.0

    def test_empty_components(self):
        result = MapCoverage().call(Payload({"components": [], "test_map": []}))
        assert result.get("coverage") == []

    def test_test_count_matches(self):
        comps = [_comp("Auth")]
        tests = [_test_entry("auth", test_methods=["test_a", "test_b", "test_c"])]
        result = MapCoverage().call(Payload({"components": comps, "test_map": tests}))
        assert result.get("coverage")[0]["test_count"] == 3

    def test_no_methods_full_coverage(self):
        """A component with no public methods is 100% covered by default."""
        comps = [{"file": "/f.py", "stem": "f", "name": "F", "kind": "filter", "methods": []}]
        result = MapCoverage().call(Payload({"components": comps, "test_map": []}))
        assert result.get("coverage")[0]["coverage_pct"] == 100.0

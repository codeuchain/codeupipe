"""Integration tests for the CUP coverage pipeline."""

import asyncio

import pytest

from codeupipe import Payload
from codeupipe.linter.coverage_pipeline import build_coverage_pipeline


def run(coro):
    return asyncio.run(coro)


class TestCoveragePipeline:
    """Integration tests for the composed coverage pipeline."""

    def test_state_tracks_all_four_steps(self, tmp_path):
        (tmp_path / "auth.py").write_text("class Auth:\n    def call(self, p): ...\n")
        pipeline = build_coverage_pipeline()
        run(pipeline.run(Payload({"directory": str(tmp_path)})))
        executed = pipeline.state.executed
        assert "scan_components" in executed
        assert "scan_tests" in executed
        assert "map_coverage" in executed
        assert "report_gaps" in executed

    def test_fully_covered_component(self, tmp_path):
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        (comp_dir / "auth.py").write_text(
            "class Auth:\n    def call(self, p): return p\n"
        )
        tests_dir = tmp_path / "my_tests"
        tests_dir.mkdir()
        (tests_dir / "test_auth.py").write_text(
            "from src.auth import Auth\n\n"
            "class TestAuth:\n"
            "    def test_call(self):\n"
            "        Auth().call(None)\n"
        )
        pipeline = build_coverage_pipeline()
        result = run(pipeline.run(Payload({
            "directory": str(comp_dir),
            "tests_dir": str(tests_dir),
        })))
        assert result.get("summary")["overall_pct"] == 100.0
        assert result.get("gaps") == []

    def test_uncovered_component(self, tmp_path):
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        (comp_dir / "auth.py").write_text(
            "class Auth:\n    def call(self, p): return p\n"
        )
        pipeline = build_coverage_pipeline()
        result = run(pipeline.run(Payload({
            "directory": str(comp_dir),
            "tests_dir": str(tmp_path / "no_tests"),
        })))
        summary = result.get("summary")
        assert summary["untested_components"] == 1
        assert summary["overall_pct"] == 0.0
        assert len(result.get("gaps")) == 1
        assert result.get("gaps")[0]["name"] == "Auth"

    def test_empty_directory(self, tmp_path):
        pipeline = build_coverage_pipeline()
        result = run(pipeline.run(Payload({"directory": str(tmp_path)})))
        assert result.get("coverage") == []
        assert result.get("summary")["total_components"] == 0
        assert result.get("gaps") == []

    def test_directory_not_found(self, tmp_path):
        pipeline = build_coverage_pipeline()
        with pytest.raises(FileNotFoundError):
            run(pipeline.run(Payload({"directory": str(tmp_path / "nope")})))

    def test_coverage_of_own_linter_package(self):
        """Coverage pipeline can analyze its own linter package (dogfooding meta-test)."""
        pipeline = build_coverage_pipeline()
        result = run(pipeline.run(Payload({
            "directory": "codeupipe/linter",
            "tests_dir": "tests",
        })))
        summary = result.get("summary")
        assert summary["total_components"] > 0
        assert summary["overall_pct"] > 0

    def test_mixed_coverage(self, tmp_path):
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        (comp_dir / "a.py").write_text("class A:\n    def call(self, p): ...\n")
        (comp_dir / "b.py").write_text("class B:\n    def call(self, p): ...\n")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_a.py").write_text(
            "from src.a import A\n\n"
            "class TestA:\n"
            "    def test_call(self): A().call(None)\n"
        )
        pipeline = build_coverage_pipeline()
        result = run(pipeline.run(Payload({
            "directory": str(comp_dir),
            "tests_dir": str(tests_dir),
        })))
        summary = result.get("summary")
        assert summary["tested_components"] == 1
        assert summary["untested_components"] == 1
        gaps = result.get("gaps")
        assert len(gaps) == 1
        assert gaps[0]["name"] == "B"

    def test_returns_payload_with_all_keys(self, tmp_path):
        (tmp_path / "x.py").write_text("class X:\n    def call(self, p): ...\n")
        pipeline = build_coverage_pipeline()
        result = run(pipeline.run(Payload({"directory": str(tmp_path)})))
        assert result.get("directory") == str(tmp_path)
        assert isinstance(result.get("components"), list)
        assert isinstance(result.get("test_map"), list)
        assert isinstance(result.get("coverage"), list)
        assert isinstance(result.get("summary"), dict)
        assert isinstance(result.get("gaps"), list)

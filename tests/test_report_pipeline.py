"""Integration tests for the CUP report pipeline — RED phase first."""

import asyncio
import subprocess

import pytest

from codeupipe import Payload
from codeupipe.linter.report_pipeline import build_report_pipeline


def run(coro):
    return asyncio.run(coro)


class TestReportPipeline:
    """Integration tests for the composed report pipeline."""

    def test_state_tracks_all_steps(self, tmp_path):
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        (comp_dir / "auth.py").write_text("class Auth:\n    def call(self, p): ...\n")

        pipeline = build_report_pipeline()
        run(pipeline.run(Payload({"directory": str(comp_dir)})))
        executed = pipeline.state.executed
        assert "scan_components" in executed
        assert "scan_tests" in executed
        assert "map_coverage" in executed
        assert "report_gaps" in executed
        assert "detect_orphans" in executed
        assert "git_history" in executed
        assert "assemble_report" in executed

    def test_full_report_on_healthy_project(self, tmp_path):
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        (comp_dir / "auth.py").write_text("class Auth:\n    def call(self, p): ...\n")
        (comp_dir / "pipeline.py").write_text(
            "from .auth import Auth\ndef build_auth(): ...\n"
        )

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_auth.py").write_text(
            "from src.auth import Auth\n\n"
            "class TestAuth:\n"
            "    def test_call(self): Auth().call(None)\n"
        )

        pipeline = build_report_pipeline()
        result = run(pipeline.run(Payload({
            "directory": str(comp_dir),
            "tests_dir": str(tests_dir),
        })))

        report = result.get("report")
        assert report is not None
        assert report["summary"]["total_components"] >= 1
        assert isinstance(report["components"], list)
        assert isinstance(report["orphaned_tests"], list)
        assert isinstance(report["stale_files"], list)
        assert "health_score" in report["summary"]

    def test_report_on_empty_directory(self, tmp_path):
        pipeline = build_report_pipeline()
        result = run(pipeline.run(Payload({"directory": str(tmp_path)})))
        report = result.get("report")
        assert report["components"] == []
        assert report["summary"]["health_score"] == "A"

    def test_report_detects_orphans(self, tmp_path):
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        (comp_dir / "used.py").write_text("class Used:\n    def call(self, p): ...\n")
        (comp_dir / "unused.py").write_text("class Unused:\n    def call(self, p): ...\n")
        (comp_dir / "pipeline.py").write_text("from .used import Used\ndef build(): ...\n")

        pipeline = build_report_pipeline()
        result = run(pipeline.run(Payload({"directory": str(comp_dir)})))
        report = result.get("report")

        orphaned_names = [o["name"] for o in report["orphaned_components"]]
        assert "Unused" in orphaned_names

    def test_report_on_own_linter_package(self):
        """Dogfooding: run report on our own linter package."""
        pipeline = build_report_pipeline()
        result = run(pipeline.run(Payload({
            "directory": "codeupipe/linter",
            "tests_dir": "tests",
        })))
        report = result.get("report")
        assert report["summary"]["total_components"] > 0
        assert report["summary"]["health_score"] is not None

    def test_report_includes_generated_at(self, tmp_path):
        pipeline = build_report_pipeline()
        result = run(pipeline.run(Payload({"directory": str(tmp_path)})))
        report = result.get("report")
        assert "generated_at" in report

    def test_json_serializable(self, tmp_path):
        """Report should be JSON-serializable for web/CI consumption."""
        import json
        pipeline = build_report_pipeline()
        result = run(pipeline.run(Payload({"directory": str(tmp_path)})))
        report = result.get("report")
        # Should not raise
        json_str = json.dumps(report)
        assert isinstance(json_str, str)

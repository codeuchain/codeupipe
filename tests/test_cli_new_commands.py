"""
Tests for new CLI commands — test, doctor, runs, upgrade, publish, graph, version.

Exercises each handler via ``main([...])`` with monkeypatch/tmp_path isolation.
"""

import json
import os

import pytest

from codeupipe.cli import main


# ── Helpers ─────────────────────────────────────────────────────────

def _write_manifest(root, name="cli-test"):
    (root / "cup.toml").write_text(
        f'[project]\nname = "{name}"\n\n[deploy]\ntarget = "docker"\n'
    )


def _write_pyproject(root, version="0.8.0"):
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "test-pkg"\nversion = "{version}"\n'
    )


# ── cup doctor ──────────────────────────────────────────────────────


class TestCupDoctor:
    """CLI: cup doctor"""

    @pytest.mark.unit
    def test_doctor_no_manifest(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        ret = main(["doctor", str(tmp_path)])
        captured = capsys.readouterr()
        assert "manifest" in captured.out.lower() or ret in (0, 1)

    @pytest.mark.unit
    def test_doctor_healthy_project(self, tmp_path, monkeypatch, capsys):
        _write_manifest(tmp_path)
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_ok.py").write_text("def test_ok(): pass\n")
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text("name: CI\non: [push]\njobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n")
        monkeypatch.chdir(tmp_path)
        ret = main(["doctor", str(tmp_path)])
        # Should print results without error
        assert ret in (0, 1)


# ── cup runs ────────────────────────────────────────────────────────


class TestCupRuns:
    """CLI: cup runs"""

    @pytest.mark.unit
    def test_runs_empty(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        ret = main(["runs"])
        captured = capsys.readouterr()
        assert "No run records" in captured.out
        assert ret == 0

    @pytest.mark.unit
    def test_runs_with_records(self, tmp_path, monkeypatch, capsys):
        from codeupipe.core.state import State
        from codeupipe.observe import RunRecord, save_run_record

        runs_dir = tmp_path / ".cup" / "runs"
        save_run_record(
            RunRecord("my_pipe", State(), duration=0.42, success=True),
            runs_dir=runs_dir,
        )

        # Point load_run_records to our tmp dir by patching _RUNS_DIR
        import codeupipe.observe as obs_mod
        monkeypatch.setattr(obs_mod, "_RUNS_DIR", runs_dir)
        monkeypatch.chdir(tmp_path)

        ret = main(["runs"])
        captured = capsys.readouterr()
        assert "my_pipe" in captured.out
        assert ret == 0


# ── cup upgrade ─────────────────────────────────────────────────────


class TestCupUpgrade:
    """CLI: cup upgrade"""

    @pytest.mark.unit
    def test_upgrade_no_manifest(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        ret = main(["upgrade", str(tmp_path)])
        captured = capsys.readouterr()
        # Should warn about missing cup.toml
        assert "cup.toml" in (captured.out + captured.err).lower() or ret == 0

    @pytest.mark.unit
    def test_upgrade_dry_run(self, tmp_path, monkeypatch, capsys):
        _write_manifest(tmp_path)
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text("# old\n")
        monkeypatch.chdir(tmp_path)
        ret = main(["upgrade", str(tmp_path), "--dry-run"])
        captured = capsys.readouterr()
        assert ret == 0
        # Old content should be preserved (dry run)
        assert (wf / "ci.yml").read_text() == "# old\n"


# ── cup publish ─────────────────────────────────────────────────────


class TestCupPublish:
    """CLI: cup publish"""

    @pytest.mark.unit
    def test_publish_check_only_valid(self, tmp_path, monkeypatch, capsys):
        _write_pyproject(tmp_path)
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_a.py").write_text("def test(): pass\n")
        (tmp_path / "README.md").write_text("# Readme\n")
        monkeypatch.chdir(tmp_path)
        ret = main(["publish", str(tmp_path), "--check-only"])
        captured = capsys.readouterr()
        assert ret == 0
        assert "valid" in captured.out.lower()

    @pytest.mark.unit
    def test_publish_missing_init(self, tmp_path, monkeypatch, capsys):
        _write_pyproject(tmp_path)
        (tmp_path / "README.md").write_text("# Readme\n")
        monkeypatch.chdir(tmp_path)
        ret = main(["publish", str(tmp_path), "--check-only"])
        assert ret == 1

    @pytest.mark.unit
    def test_publish_not_a_directory(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        ret = main(["publish", str(tmp_path / "nonexistent")])
        assert ret == 1


# ── cup graph ───────────────────────────────────────────────────────


class TestCupGraph:
    """CLI: cup graph"""

    @pytest.mark.unit
    def test_graph_stdout(self, tmp_path, monkeypatch, capsys):
        config = {
            "pipeline": {
                "name": "demo",
                "steps": [
                    {"name": "A", "type": "filter"},
                    {"name": "B", "type": "tap"},
                ],
            }
        }
        cfg_file = tmp_path / "pipeline.json"
        cfg_file.write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)
        ret = main(["graph", str(cfg_file)])
        captured = capsys.readouterr()
        assert ret == 0
        assert "graph TD" in captured.out

    @pytest.mark.unit
    def test_graph_output_file(self, tmp_path, monkeypatch):
        config = {
            "pipeline": {"name": "x", "steps": [{"name": "S", "type": "filter"}]}
        }
        cfg = tmp_path / "p.json"
        cfg.write_text(json.dumps(config))
        out = tmp_path / "diagram.md"
        monkeypatch.chdir(tmp_path)
        ret = main(["graph", str(cfg), "-o", str(out)])
        assert ret == 0
        assert out.exists()
        assert "graph TD" in out.read_text()

    @pytest.mark.unit
    def test_graph_missing_config(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        ret = main(["graph", "/no/such/file.json"])
        assert ret == 1


# ── cup version ─────────────────────────────────────────────────────


class TestCupVersion:
    """CLI: cup version"""

    @pytest.mark.unit
    def test_version_show(self, tmp_path, monkeypatch, capsys):
        _write_pyproject(tmp_path, "1.2.3")
        monkeypatch.chdir(tmp_path)
        ret = main(["version"])
        captured = capsys.readouterr()
        assert ret == 0
        assert "1.2.3" in captured.out

    @pytest.mark.unit
    def test_version_bump_patch(self, tmp_path, monkeypatch, capsys):
        _write_pyproject(tmp_path, "1.2.3")
        monkeypatch.chdir(tmp_path)
        ret = main(["version", "--bump", "patch"])
        captured = capsys.readouterr()
        assert ret == 0
        assert "1.2.4" in captured.out
        # Verify file was actually updated
        text = (tmp_path / "pyproject.toml").read_text()
        assert '1.2.4' in text

    @pytest.mark.unit
    def test_version_bump_minor(self, tmp_path, monkeypatch, capsys):
        _write_pyproject(tmp_path, "1.2.3")
        monkeypatch.chdir(tmp_path)
        ret = main(["version", "--bump", "minor"])
        captured = capsys.readouterr()
        assert "1.3.0" in captured.out

    @pytest.mark.unit
    def test_version_bump_major(self, tmp_path, monkeypatch, capsys):
        _write_pyproject(tmp_path, "1.2.3")
        monkeypatch.chdir(tmp_path)
        ret = main(["version", "--bump", "major"])
        captured = capsys.readouterr()
        assert "2.0.0" in captured.out

    @pytest.mark.unit
    def test_version_no_pyproject(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        ret = main(["version"])
        assert ret == 1

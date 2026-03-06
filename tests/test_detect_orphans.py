"""Tests for DetectOrphans filter — RED phase first."""

import pytest

from codeupipe import Payload
from codeupipe.linter.detect_orphans import DetectOrphans


def _comp(name, stem, kind="filter", file_path=None):
    return {
        "file": file_path or f"src/{stem}.py",
        "stem": stem,
        "name": name,
        "kind": kind,
        "methods": ["call"] if kind == "filter" else [],
    }


class TestDetectOrphans:
    """Unit tests for DetectOrphans filter."""

    def test_component_imported_by_pipeline_not_orphaned(self, tmp_path):
        """A filter imported in a pipeline file is not orphaned."""
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        (comp_dir / "auth.py").write_text("class Auth:\n    def call(self, p): ...\n")
        (comp_dir / "pipeline.py").write_text("from .auth import Auth\n\ndef build(): ...\n")

        comps = [_comp("Auth", "auth", file_path=str(comp_dir / "auth.py"))]
        payload = Payload({"components": comps, "directory": str(comp_dir)})
        result = DetectOrphans().call(payload)

        assert result.get("orphaned_components") == []

    def test_component_never_imported_is_orphaned(self, tmp_path):
        """A filter that no other file imports is orphaned."""
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        (comp_dir / "auth.py").write_text("class Auth:\n    def call(self, p): ...\n")
        (comp_dir / "other.py").write_text("class Other:\n    def call(self, p): ...\n")

        comps = [
            _comp("Auth", "auth", file_path=str(comp_dir / "auth.py")),
            _comp("Other", "other", file_path=str(comp_dir / "other.py")),
        ]
        payload = Payload({"components": comps, "directory": str(comp_dir)})
        result = DetectOrphans().call(payload)

        orphaned_names = [o["name"] for o in result.get("orphaned_components")]
        assert "Auth" in orphaned_names
        assert "Other" in orphaned_names

    def test_builder_imported_not_orphaned(self, tmp_path):
        """A build_* function imported elsewhere is not orphaned."""
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        (comp_dir / "pipeline.py").write_text(
            "def build_auth_pipeline(): ...\n"
        )
        (comp_dir / "main.py").write_text("from .pipeline import build_auth_pipeline\n")

        comps = [_comp("build_auth_pipeline", "pipeline", kind="builder",
                        file_path=str(comp_dir / "pipeline.py"))]
        payload = Payload({"components": comps, "directory": str(comp_dir)})
        result = DetectOrphans().call(payload)

        assert result.get("orphaned_components") == []

    def test_orphaned_tests_detected(self, tmp_path):
        """A test file with no matching component is an orphaned test."""
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        (comp_dir / "auth.py").write_text("class Auth:\n    def call(self, p): ...\n")

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_auth.py").write_text("def test_a(): ...\n")
        (tests_dir / "test_deleted_thing.py").write_text("def test_old(): ...\n")

        comps = [_comp("Auth", "auth", file_path=str(comp_dir / "auth.py"))]
        payload = Payload({
            "components": comps,
            "directory": str(comp_dir),
            "tests_dir": str(tests_dir),
        })
        result = DetectOrphans().call(payload)

        orphaned_tests = result.get("orphaned_tests")
        assert len(orphaned_tests) == 1
        assert "test_deleted_thing.py" in orphaned_tests[0]["file"]

    def test_no_orphaned_tests_when_all_match(self, tmp_path):
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        (comp_dir / "auth.py").write_text("class Auth:\n    def call(self, p): ...\n")

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_auth.py").write_text("def test_a(): ...\n")

        comps = [_comp("Auth", "auth", file_path=str(comp_dir / "auth.py"))]
        payload = Payload({
            "components": comps,
            "directory": str(comp_dir),
            "tests_dir": str(tests_dir),
        })
        result = DetectOrphans().call(payload)

        assert result.get("orphaned_tests") == []

    def test_records_who_imports_component(self, tmp_path):
        """Each component should have an 'imported_by' list."""
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        (comp_dir / "auth.py").write_text("class Auth:\n    def call(self, p): ...\n")
        (comp_dir / "pipeline.py").write_text("from .auth import Auth\n")
        (comp_dir / "main.py").write_text("from .auth import Auth\n")

        comps = [_comp("Auth", "auth", file_path=str(comp_dir / "auth.py"))]
        payload = Payload({"components": comps, "directory": str(comp_dir)})
        result = DetectOrphans().call(payload)

        import_map = result.get("import_map")
        assert "Auth" in import_map
        importers = import_map["Auth"]
        assert len(importers) == 2

    def test_empty_components(self, tmp_path):
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        payload = Payload({
            "components": [],
            "directory": str(comp_dir),
            "tests_dir": str(tests_dir),
        })
        result = DetectOrphans().call(payload)

        assert result.get("orphaned_components") == []
        assert result.get("orphaned_tests") == []
        assert result.get("import_map") == {}

    def test_ignores_init_py_imports(self, tmp_path):
        """__init__.py re-exports shouldn't count as 'real' usage."""
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        (comp_dir / "auth.py").write_text("class Auth:\n    def call(self, p): ...\n")
        (comp_dir / "__init__.py").write_text("from .auth import Auth\n")

        comps = [_comp("Auth", "auth", file_path=str(comp_dir / "auth.py"))]
        payload = Payload({"components": comps, "directory": str(comp_dir)})
        result = DetectOrphans().call(payload)

        orphaned_names = [o["name"] for o in result.get("orphaned_components")]
        assert "Auth" in orphaned_names

    def test_syntax_error_files_skipped(self, tmp_path):
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        (comp_dir / "auth.py").write_text("class Auth:\n    def call(self, p): ...\n")
        (comp_dir / "broken.py").write_text("def broken(\n")

        comps = [_comp("Auth", "auth", file_path=str(comp_dir / "auth.py"))]
        payload = Payload({"components": comps, "directory": str(comp_dir)})
        result = DetectOrphans().call(payload)

        # Should not crash — broken file just gets skipped
        assert isinstance(result.get("orphaned_components"), list)

    def test_orphan_entry_shape(self, tmp_path):
        """Orphaned component entries have expected keys."""
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        (comp_dir / "auth.py").write_text("class Auth:\n    def call(self, p): ...\n")

        comps = [_comp("Auth", "auth", file_path=str(comp_dir / "auth.py"))]
        payload = Payload({"components": comps, "directory": str(comp_dir)})
        result = DetectOrphans().call(payload)

        orphan = result.get("orphaned_components")[0]
        assert orphan["name"] == "Auth"
        assert orphan["kind"] == "filter"
        assert "file" in orphan

    def test_conftest_not_orphaned_test(self, tmp_path):
        """conftest.py and __init__.py in tests dir are not orphan tests."""
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "conftest.py").write_text("import pytest\n")
        (tests_dir / "__init__.py").write_text("")

        payload = Payload({
            "components": [],
            "directory": str(comp_dir),
            "tests_dir": str(tests_dir),
        })
        result = DetectOrphans().call(payload)
        assert result.get("orphaned_tests") == []

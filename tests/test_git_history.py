"""Tests for GitHistory filter — RED phase first."""

import os
import subprocess

import pytest

from codeupipe import Payload
from codeupipe.linter.git_history import GitHistory


def _comp(name, stem, kind="filter", file_path=None):
    return {
        "file": file_path or f"src/{stem}.py",
        "stem": stem,
        "name": name,
        "kind": kind,
        "methods": ["call"] if kind == "filter" else [],
    }


class TestGitHistory:
    """Unit tests for GitHistory filter."""

    def test_returns_git_data_for_tracked_file(self, tmp_path):
        """Components in a real git repo get last_modified, author, commit_count."""
        # Create a real git repo
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path), capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=str(tmp_path), capture_output=True,
        )
        f = tmp_path / "auth.py"
        f.write_text("class Auth:\n    def call(self, p): ...\n")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path), capture_output=True,
        )

        comps = [_comp("Auth", "auth", file_path=str(f))]
        payload = Payload({"components": comps, "directory": str(tmp_path)})
        result = GitHistory().call(payload)

        git_info = result.get("git_info")
        assert "auth.py" in git_info or str(f) in git_info
        entry = list(git_info.values())[0]
        assert "last_modified" in entry
        assert "last_author" in entry
        assert "commit_count" in entry
        assert entry["commit_count"] >= 1
        assert entry["last_author"] == "Test User"

    def test_untracked_file_gets_none_info(self, tmp_path):
        """Files not in git get null/default git info."""
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=str(tmp_path), capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=str(tmp_path), capture_output=True,
        )
        # Create file but don't commit
        f = tmp_path / "new.py"
        f.write_text("class New:\n    def call(self, p): ...\n")

        comps = [_comp("New", "new", file_path=str(f))]
        payload = Payload({"components": comps, "directory": str(tmp_path)})
        result = GitHistory().call(payload)

        entry = list(result.get("git_info").values())[0]
        assert entry["commit_count"] == 0
        assert entry["last_modified"] is None

    def test_non_git_repo_graceful(self, tmp_path):
        """If directory is not a git repo, git_info is empty."""
        f = tmp_path / "auth.py"
        f.write_text("class Auth:\n    def call(self, p): ...\n")

        comps = [_comp("Auth", "auth", file_path=str(f))]
        payload = Payload({"components": comps, "directory": str(tmp_path)})
        result = GitHistory().call(payload)

        assert result.get("git_info") == {}

    def test_days_since_change_computed(self, tmp_path):
        """Each file entry should have days_since_change >= 0."""
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=str(tmp_path), capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=str(tmp_path), capture_output=True,
        )
        f = tmp_path / "auth.py"
        f.write_text("class Auth:\n    def call(self, p): ...\n")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path), capture_output=True,
        )

        comps = [_comp("Auth", "auth", file_path=str(f))]
        payload = Payload({"components": comps, "directory": str(tmp_path)})
        result = GitHistory().call(payload)

        entry = list(result.get("git_info").values())[0]
        assert "days_since_change" in entry
        assert entry["days_since_change"] >= 0

    def test_empty_components(self, tmp_path):
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        payload = Payload({"components": [], "directory": str(tmp_path)})
        result = GitHistory().call(payload)
        assert result.get("git_info") == {}

    def test_multiple_files(self, tmp_path):
        """Multiple component files each get their own git info."""
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=str(tmp_path), capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=str(tmp_path), capture_output=True,
        )
        f1 = tmp_path / "a.py"
        f1.write_text("class A:\n    def call(self, p): ...\n")
        f2 = tmp_path / "b.py"
        f2.write_text("class B:\n    def call(self, p): ...\n")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path), capture_output=True,
        )

        comps = [
            _comp("A", "a", file_path=str(f1)),
            _comp("B", "b", file_path=str(f2)),
        ]
        payload = Payload({"components": comps, "directory": str(tmp_path)})
        result = GitHistory().call(payload)

        git_info = result.get("git_info")
        assert len(git_info) == 2

    def test_test_files_included_when_present(self, tmp_path):
        """test_map file entries also get git history."""
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=str(tmp_path), capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"],
            cwd=str(tmp_path), capture_output=True,
        )
        comp_dir = tmp_path / "src"
        comp_dir.mkdir()
        f = comp_dir / "auth.py"
        f.write_text("class Auth:\n    def call(self, p): ...\n")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        tf = tests_dir / "test_auth.py"
        tf.write_text("def test_a(): ...\n")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path), capture_output=True,
        )

        comps = [_comp("Auth", "auth", file_path=str(f))]
        test_map = [{"test_file": str(tf), "stem": "auth", "test_methods": ["test_a"],
                      "imports": set(), "referenced_methods": set()}]
        payload = Payload({
            "components": comps,
            "test_map": test_map,
            "directory": str(tmp_path),
        })
        result = GitHistory().call(payload)

        git_info = result.get("git_info")
        # Should have git info for both the component file and the test file
        assert len(git_info) >= 2

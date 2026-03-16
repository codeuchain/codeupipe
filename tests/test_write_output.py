"""Tests for WriteOutput — write built HTML and copy static assets."""

import os

import pytest

from codeupipe import Payload
from codeupipe.deploy.obfuscate.write_output import WriteOutput


class TestWriteOutput:
    def test_writes_html_files(self, tmp_path):
        out_dir = str(tmp_path / "dist")
        html_list = [
            {"filename": "index.html", "content": "<p>Hello</p>"},
            {"filename": "about.html", "content": "<p>About</p>"},
        ]

        f = WriteOutput()
        result = f.call(Payload({
            "minified_html": html_list,
            "config": {"src_dir": "", "out_dir": out_dir, "static_copy": []},
        }))

        # Files written
        assert os.path.exists(os.path.join(out_dir, "index.html"))
        assert os.path.exists(os.path.join(out_dir, "about.html"))

        # Content matches
        with open(os.path.join(out_dir, "index.html")) as f_:
            assert f_.read() == "<p>Hello</p>"

        # Results reported
        results = result.get("build_results")
        assert len(results) == 2
        assert results[0]["filename"] == "index.html"
        assert results[0]["size"] > 0

    def test_copies_static_files(self, tmp_path):
        src_dir = str(tmp_path / "src")
        out_dir = str(tmp_path / "dist")
        os.makedirs(src_dir)

        # Create static assets in src
        with open(os.path.join(src_dir, "robots.txt"), "w") as f_:
            f_.write("User-agent: *")
        os.makedirs(os.path.join(src_dir, "assets"))
        with open(os.path.join(src_dir, "assets", "logo.png"), "w") as f_:
            f_.write("PNG data")

        f = WriteOutput()
        result = f.call(Payload({
            "minified_html": [],
            "config": {
                "src_dir": src_dir,
                "out_dir": out_dir,
                "static_copy": ["robots.txt", "assets"],
            },
        }))

        assert os.path.exists(os.path.join(out_dir, "robots.txt"))
        assert os.path.exists(os.path.join(out_dir, "assets", "logo.png"))
        assert "robots.txt" in result.get("static_copied")
        assert "assets" in result.get("static_copied")

    def test_missing_out_dir_raises(self):
        f = WriteOutput()
        with pytest.raises(ValueError, match="out_dir is required"):
            f.call(Payload({
                "minified_html": [],
                "config": {"src_dir": "", "out_dir": "", "static_copy": []},
            }))

    def test_creates_out_dir(self, tmp_path):
        out_dir = str(tmp_path / "nested" / "deep" / "dist")
        f = WriteOutput()
        f.call(Payload({
            "minified_html": [{"filename": "x.html", "content": "hi"}],
            "config": {"src_dir": "", "out_dir": out_dir, "static_copy": []},
        }))
        assert os.path.exists(os.path.join(out_dir, "x.html"))

    def test_skips_missing_static(self, tmp_path):
        src_dir = str(tmp_path / "src")
        out_dir = str(tmp_path / "dist")
        os.makedirs(src_dir)

        f = WriteOutput()
        result = f.call(Payload({
            "minified_html": [],
            "config": {
                "src_dir": src_dir,
                "out_dir": out_dir,
                "static_copy": ["nonexistent.txt"],
            },
        }))
        assert "nonexistent.txt" not in result.get("static_copied")

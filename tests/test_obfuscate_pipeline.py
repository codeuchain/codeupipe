"""Tests for build_obfuscate_pipeline — end-to-end pipeline integration."""

import asyncio
import os
from unittest.mock import patch

import pytest

from codeupipe import Payload
from codeupipe.deploy.obfuscate import (
    ObfuscateConfig,
    build_obfuscate_pipeline,
)


class TestObfuscatePipeline:
    def test_pipeline_builds(self):
        """Pipeline builder returns a valid Pipeline with 6 steps."""
        pipeline = build_obfuscate_pipeline()
        assert len(pipeline._steps) == 6

    @patch("codeupipe.deploy.obfuscate.transform_code._find_obfuscator")
    @patch("codeupipe.deploy.obfuscate.minify_content._find_minifier")
    def test_end_to_end_no_tools(self, mock_minifier, mock_obfuscator, tmp_path):
        """Full pipeline runs with fallback when no Node.js tools installed."""
        mock_obfuscator.return_value = ""
        mock_minifier.return_value = ""

        # Setup source
        src_dir = str(tmp_path / "src")
        out_dir = str(tmp_path / "dist")
        os.makedirs(src_dir)

        code = "function init() { console.log('hello world from the application startup sequence'); }"
        html = f"""<html>
<head><title>Test SPA</title></head>
<body>
  <h1>   Hello   World   </h1>
  <!-- This comment should be removed -->
  <script>{code}</script>
</body>
</html>"""
        (tmp_path / "src" / "index.html").write_text(html)

        # Static asset
        (tmp_path / "src" / "robots.txt").write_text("User-agent: *")

        config = ObfuscateConfig(
            src_dir=src_dir,
            out_dir=out_dir,
            static_copy=["robots.txt"],
        )

        pipeline = build_obfuscate_pipeline()
        result = asyncio.run(pipeline.run(Payload({"config": config.to_dict()})))

        # Output files exist
        assert os.path.exists(os.path.join(out_dir, "index.html"))
        assert os.path.exists(os.path.join(out_dir, "robots.txt"))

        # Build results reported
        build_results = result.get("build_results")
        assert len(build_results) == 1
        assert build_results[0]["filename"] == "index.html"

        # Stats available
        assert result.get("obfuscate_stats") is not None
        assert result.get("minify_stats") is not None

        # Output is smaller (fallback minifier strips comments/whitespace)
        output = open(os.path.join(out_dir, "index.html")).read()
        assert "<!-- This comment" not in output

    @patch("codeupipe.deploy.obfuscate.transform_code._find_obfuscator")
    @patch("codeupipe.deploy.obfuscate.minify_content._find_minifier")
    def test_no_scripts_still_works(self, mock_minifier, mock_obfuscator, tmp_path):
        """Pipeline handles HTML with no inline scripts."""
        mock_obfuscator.return_value = ""
        mock_minifier.return_value = ""

        src_dir = str(tmp_path / "src")
        out_dir = str(tmp_path / "dist")
        os.makedirs(src_dir)

        (tmp_path / "src" / "page.html").write_text("<p>Just text</p>")

        config = ObfuscateConfig(src_dir=src_dir, out_dir=out_dir)
        pipeline = build_obfuscate_pipeline()
        result = asyncio.run(pipeline.run(Payload({"config": config.to_dict()})))

        assert os.path.exists(os.path.join(out_dir, "page.html"))
        assert result.get("obfuscate_stats")["total"] == 0

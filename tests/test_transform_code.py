"""Tests for TransformCode — pluggable tool per file type (replaces ObfuscateScripts)."""

import pytest

from codeupipe import Payload
from codeupipe.testing import run_filter
from codeupipe.deploy.obfuscate.transform_code import TransformCode
# Backward-compat alias
from codeupipe.deploy.obfuscate.obfuscate_scripts import ObfuscateScripts


class TestTransformCode:
    """TransformCode supports pluggable tools for different file types."""

    def test_passthrough_when_no_tool(self):
        """With no tool installed and strict=False, code passes through.
        If a tool IS installed, code may be transformed — both are valid."""
        blocks = [{"filename": "f.html", "index": 0, "code": "var x = 1;"}]
        result = run_filter(TransformCode(strict=False), {
            "code_blocks": blocks,
            "config": {"js_opts": {}, "reserved_names": [], "reserved_strings": []},
        })
        out = result.get("transformed_blocks")
        assert len(out) == 1
        # Code is either original (no tool) or transformed (tool present)
        assert out[0]["transformed_code"] is not None
        assert len(out[0]["transformed_code"]) > 0

    def test_writes_backward_compat_keys(self):
        blocks = [{"filename": "f.html", "index": 0, "code": "var x = 1;"}]
        result = run_filter(TransformCode(strict=False), {
            "code_blocks": blocks,
            "script_blocks": blocks,
            "config": {"js_opts": {}, "reserved_names": [], "reserved_strings": []},
        })
        # New keys
        assert result.get("transformed_blocks") is not None
        assert result.get("transform_stats") is not None
        # Backward-compat keys
        assert result.get("obfuscated_blocks") is not None
        assert result.get("obfuscate_stats") is not None

    def test_stats_structure(self):
        blocks = [{"filename": "f.html", "index": 0, "code": "var x = 1;"}]
        result = run_filter(TransformCode(strict=False), {
            "code_blocks": blocks,
            "config": {"js_opts": {}, "reserved_names": [], "reserved_strings": []},
        })
        stats = result.get("transform_stats")
        assert "total" in stats
        assert "transformed" in stats or "obfuscated" in stats or "skipped" in stats

    def test_empty_blocks(self):
        result = run_filter(TransformCode(strict=False), {
            "code_blocks": [],
            "config": {"js_opts": {}},
        })
        assert result.get("transformed_blocks") == []


class TestObfuscateScriptsAlias:
    """Old name still importable and functional."""

    def test_alias_importable(self):
        assert ObfuscateScripts is not None

    def test_alias_produces_obfuscated_blocks(self):
        blocks = [{"filename": "f.html", "index": 0, "code": "var x = 1;"}]
        result = run_filter(ObfuscateScripts(strict=False), {
            "script_blocks": blocks,
            "config": {"js_opts": {}, "reserved_names": [], "reserved_strings": []},
        })
        assert result.get("obfuscated_blocks") is not None

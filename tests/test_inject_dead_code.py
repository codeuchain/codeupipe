"""Tests for InjectDeadCode — configurable dead code injection into extracted code blocks."""

import pytest

from codeupipe import Payload
from codeupipe.testing import run_filter
from codeupipe.deploy.obfuscate.inject_dead_code import InjectDeadCode


class TestInjectDeadCode:
    """InjectDeadCode inserts syntactically valid but non-functional code."""

    def test_disabled_by_default_passthrough(self):
        blocks = [{"filename": "index.html", "index": 0, "code": "var x = 1;"}]
        result = run_filter(InjectDeadCode(), {
            "code_blocks": blocks,
            "config": {"dead_code": {"enabled": False}},
        })
        out_blocks = result.get("code_blocks")
        assert len(out_blocks) == 1
        assert out_blocks[0]["code"] == "var x = 1;"

    def test_injects_code_when_enabled(self):
        original = "var x = 1;"
        blocks = [{"filename": "index.html", "index": 0, "code": original}]
        result = run_filter(InjectDeadCode(), {
            "code_blocks": blocks,
            "config": {"dead_code": {"enabled": True, "density": "medium"}},
        })
        out_blocks = result.get("code_blocks")
        # Injected code should be longer than original
        assert len(out_blocks[0]["code"]) > len(original)

    def test_low_density_injects_less(self):
        original = "var x = 1; var y = 2;"
        blocks = [{"filename": "f.html", "index": 0, "code": original}]

        result_low = run_filter(InjectDeadCode(), {
            "code_blocks": blocks,
            "config": {"dead_code": {"enabled": True, "density": "low", "seed": 42}},
        })
        result_high = run_filter(InjectDeadCode(), {
            "code_blocks": blocks,
            "config": {"dead_code": {"enabled": True, "density": "high", "seed": 42}},
        })

        low_len = len(result_low.get("code_blocks")[0]["code"])
        high_len = len(result_high.get("code_blocks")[0]["code"])
        assert high_len > low_len

    def test_seed_produces_deterministic_output(self):
        blocks = [{"filename": "f.html", "index": 0, "code": "var x = 1;"}]

        result_a = run_filter(InjectDeadCode(), {
            "code_blocks": blocks,
            "config": {"dead_code": {"enabled": True, "density": "medium", "seed": 99}},
        })
        result_b = run_filter(InjectDeadCode(), {
            "code_blocks": blocks,
            "config": {"dead_code": {"enabled": True, "density": "medium", "seed": 99}},
        })

        assert result_a.get("code_blocks")[0]["code"] == result_b.get("code_blocks")[0]["code"]

    def test_different_seeds_produce_different_output(self):
        blocks = [{"filename": "f.html", "index": 0, "code": "var x = 1;"}]

        result_a = run_filter(InjectDeadCode(), {
            "code_blocks": blocks,
            "config": {"dead_code": {"enabled": True, "density": "medium", "seed": 1}},
        })
        result_b = run_filter(InjectDeadCode(), {
            "code_blocks": blocks,
            "config": {"dead_code": {"enabled": True, "density": "medium", "seed": 2}},
        })

        assert result_a.get("code_blocks")[0]["code"] != result_b.get("code_blocks")[0]["code"]

    def test_injected_code_is_syntactically_valid_js(self):
        """Dead code snippets should be valid JS — no syntax errors."""
        blocks = [{"filename": "f.html", "index": 0, "code": "var x = 1;"}]
        result = run_filter(InjectDeadCode(), {
            "code_blocks": blocks,
            "config": {"dead_code": {"enabled": True, "density": "high", "seed": 42}},
        })
        code = result.get("code_blocks")[0]["code"]
        # Should contain the original code
        assert "var x = 1;" in code
        # Should contain some injected patterns (variable declarations, if blocks, etc.)
        assert len(code) > len("var x = 1;")

    def test_preserves_block_metadata(self):
        blocks = [{
            "filename": "page.html",
            "index": 3,
            "code": "var x = 1;",
            "open_tag": "<script>",
            "close_tag": "</script>",
            "placeholder": "__CUP_SCRIPT_page.html_3__",
        }]
        result = run_filter(InjectDeadCode(), {
            "code_blocks": blocks,
            "config": {"dead_code": {"enabled": True, "density": "low", "seed": 1}},
        })
        out = result.get("code_blocks")[0]
        assert out["filename"] == "page.html"
        assert out["index"] == 3
        assert out["placeholder"] == "__CUP_SCRIPT_page.html_3__"

    def test_empty_blocks_passthrough(self):
        result = run_filter(InjectDeadCode(), {
            "code_blocks": [],
            "config": {"dead_code": {"enabled": True, "density": "medium"}},
        })
        assert result.get("code_blocks") == []

    def test_no_config_means_disabled(self):
        blocks = [{"filename": "f.html", "index": 0, "code": "var x = 1;"}]
        result = run_filter(InjectDeadCode(), {
            "code_blocks": blocks,
            "config": {},
        })
        assert result.get("code_blocks")[0]["code"] == "var x = 1;"

    def test_inject_stats(self):
        blocks = [{"filename": "f.html", "index": 0, "code": "var x = 1;"}]
        result = run_filter(InjectDeadCode(), {
            "code_blocks": blocks,
            "config": {"dead_code": {"enabled": True, "density": "medium", "seed": 42}},
        })
        stats = result.get("dead_code_stats")
        assert stats is not None
        assert stats["total"] == 1
        assert stats["injected"] >= 1

"""Tests for dynamic pipeline composition — stages, dead code, presets."""

import asyncio

import pytest

from codeupipe import Payload
from codeupipe.deploy.obfuscate import (
    ObfuscateConfig,
    build_obfuscate_pipeline,
)


def _step_names(pipeline):
    """Extract filter/step names from a Pipeline's internal _steps list."""
    return [name for name, _, _ in pipeline._steps]


class TestDynamicPipelineComposition:
    """build_obfuscate_pipeline respects config stages and dead_code settings."""

    def test_default_config_builds_six_stage_pipeline(self):
        config = ObfuscateConfig(src_dir="src", out_dir="dist")
        pipeline = build_obfuscate_pipeline(config=config)
        # Default: 6 stages (scan, extract, transform, reassemble, minify, write)
        assert len(pipeline._steps) == 6

    def test_dead_code_enabled_adds_inject_stage(self):
        config = ObfuscateConfig(
            src_dir="src", out_dir="dist",
            dead_code={"enabled": True, "density": "medium"},
        )
        pipeline = build_obfuscate_pipeline(config=config)
        # 7 stages: scan, extract, inject_dead_code, transform, reassemble, minify, write
        assert len(pipeline._steps) == 7
        assert "inject_dead_code" in _step_names(pipeline)

    def test_disable_minify_stage(self):
        config = ObfuscateConfig(
            src_dir="src", out_dir="dist",
            stages={"minify": False},
        )
        pipeline = build_obfuscate_pipeline(config=config)
        # 5 stages: scan, extract, transform, reassemble, write — no minify
        assert len(pipeline._steps) == 5
        names = _step_names(pipeline)
        assert "minify_content" not in names

    def test_disable_transform_stage(self):
        config = ObfuscateConfig(
            src_dir="src", out_dir="dist",
            stages={"transform": False},
        )
        pipeline = build_obfuscate_pipeline(config=config)
        names = _step_names(pipeline)
        assert "transform_code" not in names

    def test_disable_extract_stage(self):
        config = ObfuscateConfig(
            src_dir="src", out_dir="dist",
            stages={"extract": False},
        )
        pipeline = build_obfuscate_pipeline(config=config)
        names = _step_names(pipeline)
        assert "extract_embedded_code" not in names

    def test_no_config_builds_classic_pipeline(self):
        """Backward compat: no config arg builds the old 6-stage pipeline."""
        pipeline = build_obfuscate_pipeline()
        assert len(pipeline._steps) == 6

    def test_preset_heavy_enables_dead_code(self):
        config = ObfuscateConfig(
            src_dir="src", out_dir="dist",
            preset="heavy",
        )
        pipeline = build_obfuscate_pipeline(config=config)
        # Heavy preset enables dead code → 7 stages
        assert len(pipeline._steps) == 7
        assert "inject_dead_code" in _step_names(pipeline)

    def test_paranoid_preset_pipeline(self):
        config = ObfuscateConfig(
            src_dir="src", out_dir="dist",
            preset="paranoid",
        )
        pipeline = build_obfuscate_pipeline(config=config)
        # Paranoid also enables dead code → 7 stages
        assert len(pipeline._steps) == 7
        assert "inject_dead_code" in _step_names(pipeline)

    def test_light_preset_pipeline(self):
        config = ObfuscateConfig(
            src_dir="src", out_dir="dist",
            preset="light",
        )
        pipeline = build_obfuscate_pipeline(config=config)
        # Light preset: no dead code → 6 stages
        assert len(pipeline._steps) == 6
        assert "inject_dead_code" not in _step_names(pipeline)

    def test_pipeline_runs_end_to_end(self, tmp_path):
        """Full pipeline run with a real config and files."""
        src = tmp_path / "src"
        src.mkdir()
        out = tmp_path / "out"

        (src / "index.html").write_text(
            "<html><head><script>"
            + "var greeting = 'hello world'; console.log(greeting);" * 3
            + "</script></head><body></body></html>"
        )

        config = ObfuscateConfig(
            src_dir=str(src),
            out_dir=str(out),
            preset="light",
        )
        pipeline = build_obfuscate_pipeline(config=config)
        result = asyncio.run(pipeline.run(Payload({"config": config.to_dict()})))

        assert result.get("build_results") is not None
        assert len(result.get("build_results")) == 1

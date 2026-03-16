"""Tests for ObfuscateConfig v2 — presets, file_types, stages, dead_code, config file loading."""

import json
import os

import pytest

from codeupipe.deploy.obfuscate.obfuscate_config import (
    ObfuscateConfig,
    PRESETS,
    DEFAULT_FILE_TYPES,
    DEFAULT_STAGES,
    DEFAULT_JS_OBFUSCATOR_OPTS,
)


class TestPresets:
    """Preset profiles pre-populate config with curated defaults."""

    def test_light_preset(self):
        cfg = ObfuscateConfig(src_dir="src", out_dir="dist", preset="light")
        assert cfg.js_opts["dead-code-injection"] is False
        assert cfg.js_opts["control-flow-flattening"] is False
        assert cfg.js_opts["string-array"] is False

    def test_medium_preset_is_current_default(self):
        cfg = ObfuscateConfig(src_dir="src", out_dir="dist", preset="medium")
        default = ObfuscateConfig(src_dir="src", out_dir="dist")
        assert cfg.js_opts == default.js_opts

    def test_heavy_preset(self):
        cfg = ObfuscateConfig(src_dir="src", out_dir="dist", preset="heavy")
        assert cfg.js_opts["dead-code-injection"] is True
        assert cfg.js_opts["control-flow-flattening"] is True
        assert cfg.js_opts["control-flow-flattening-threshold"] >= 0.5
        assert cfg.dead_code["enabled"] is True

    def test_paranoid_preset(self):
        cfg = ObfuscateConfig(src_dir="src", out_dir="dist", preset="paranoid")
        assert cfg.js_opts["dead-code-injection"] is True
        assert cfg.js_opts["self-defending"] is True
        assert cfg.js_opts["control-flow-flattening-threshold"] >= 0.7
        assert cfg.dead_code["enabled"] is True
        assert cfg.dead_code["density"] == "high"

    def test_unknown_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown preset"):
            ObfuscateConfig(src_dir="src", out_dir="dist", preset="invalid")

    def test_preset_keys_match_constant(self):
        assert set(PRESETS.keys()) == {"light", "medium", "heavy", "paranoid"}

    def test_explicit_opts_override_preset(self):
        cfg = ObfuscateConfig(
            src_dir="src", out_dir="dist",
            preset="paranoid",
            js_opts={"self-defending": False},
        )
        # User's explicit override wins
        assert cfg.js_opts["self-defending"] is False
        # Other paranoid settings still applied
        assert cfg.js_opts["dead-code-injection"] is True


class TestFileTypes:
    """Configurable file type handlers."""

    def test_default_file_types(self):
        cfg = ObfuscateConfig(src_dir="src", out_dir="dist")
        assert len(cfg.file_types) >= 1
        html_type = cfg.file_types[0]
        assert ".html" in html_type["extensions"]

    def test_custom_file_types(self):
        custom = [
            {
                "extensions": [".html", ".htm"],
                "extract_patterns": ["<script>"],
                "tool": "javascript-obfuscator",
                "minifier": "html-minifier-terser",
            },
            {
                "extensions": [".php"],
                "extract_patterns": ["<\\?php"],
                "tool": None,
                "minifier": None,
            },
        ]
        cfg = ObfuscateConfig(src_dir="src", out_dir="dist", file_types=custom)
        assert len(cfg.file_types) == 2
        assert ".php" in cfg.file_types[1]["extensions"]

    def test_file_types_in_to_dict(self):
        cfg = ObfuscateConfig(src_dir="src", out_dir="dist")
        d = cfg.to_dict()
        assert "file_types" in d
        assert isinstance(d["file_types"], list)

    def test_default_file_types_constant(self):
        assert isinstance(DEFAULT_FILE_TYPES, list)
        assert len(DEFAULT_FILE_TYPES) >= 1


class TestStages:
    """Per-stage enable/disable."""

    def test_default_stages_all_enabled(self):
        cfg = ObfuscateConfig(src_dir="src", out_dir="dist")
        for stage_name, enabled in cfg.stages.items():
            assert enabled is True, f"Stage {stage_name} should be enabled by default"

    def test_disable_minify(self):
        cfg = ObfuscateConfig(
            src_dir="src", out_dir="dist",
            stages={"minify": False},
        )
        assert cfg.stages["minify"] is False
        # Other stages still enabled
        assert cfg.stages["scan"] is True
        assert cfg.stages["extract"] is True

    def test_disable_obfuscate(self):
        cfg = ObfuscateConfig(
            src_dir="src", out_dir="dist",
            stages={"transform": False},
        )
        assert cfg.stages["transform"] is False

    def test_stages_in_to_dict(self):
        cfg = ObfuscateConfig(
            src_dir="src", out_dir="dist",
            stages={"minify": False},
        )
        d = cfg.to_dict()
        assert d["stages"]["minify"] is False

    def test_default_stages_constant(self):
        assert isinstance(DEFAULT_STAGES, dict)
        assert "scan" in DEFAULT_STAGES
        assert "extract" in DEFAULT_STAGES
        assert "transform" in DEFAULT_STAGES
        assert "reassemble" in DEFAULT_STAGES
        assert "minify" in DEFAULT_STAGES
        assert "write" in DEFAULT_STAGES


class TestDeadCodeConfig:
    """Dead code injection configuration."""

    def test_dead_code_disabled_by_default(self):
        cfg = ObfuscateConfig(src_dir="src", out_dir="dist")
        assert cfg.dead_code["enabled"] is False

    def test_dead_code_explicit_enable(self):
        cfg = ObfuscateConfig(
            src_dir="src", out_dir="dist",
            dead_code={"enabled": True, "density": "medium"},
        )
        assert cfg.dead_code["enabled"] is True
        assert cfg.dead_code["density"] == "medium"

    def test_dead_code_density_levels(self):
        for level in ("low", "medium", "high"):
            cfg = ObfuscateConfig(
                src_dir="src", out_dir="dist",
                dead_code={"enabled": True, "density": level},
            )
            assert cfg.dead_code["density"] == level

    def test_dead_code_seed_reproducibility(self):
        cfg = ObfuscateConfig(
            src_dir="src", out_dir="dist",
            dead_code={"enabled": True, "density": "low", "seed": 42},
        )
        assert cfg.dead_code["seed"] == 42

    def test_dead_code_in_to_dict(self):
        cfg = ObfuscateConfig(
            src_dir="src", out_dir="dist",
            dead_code={"enabled": True, "density": "high"},
        )
        d = cfg.to_dict()
        assert d["dead_code"]["enabled"] is True


class TestConfigFileLoading:
    """Load config from TOML or JSON file."""

    def test_from_json_file(self, tmp_path):
        cfg_data = {
            "src_dir": str(tmp_path / "src"),
            "out_dir": str(tmp_path / "out"),
            "preset": "heavy",
            "stages": {"minify": False},
        }
        cfg_file = tmp_path / "obfuscate.json"
        cfg_file.write_text(json.dumps(cfg_data))

        cfg = ObfuscateConfig.from_file(str(cfg_file))
        assert cfg.src_dir == str(tmp_path / "src")
        assert cfg.stages["minify"] is False

    def test_from_toml_file(self, tmp_path):
        toml_content = """\
src_dir = "{src}"
out_dir = "{out}"
preset = "light"

[stages]
minify = false
""".format(src=str(tmp_path / "src"), out=str(tmp_path / "out"))
        cfg_file = tmp_path / "obfuscate.toml"
        cfg_file.write_text(toml_content)

        cfg = ObfuscateConfig.from_file(str(cfg_file))
        assert cfg.preset == "light"
        assert cfg.stages["minify"] is False

    def test_from_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            ObfuscateConfig.from_file("/nonexistent/config.json")

    def test_from_file_unknown_extension_raises(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("foo: bar")
        with pytest.raises(ValueError, match="Unsupported config format"):
            ObfuscateConfig.from_file(str(f))


class TestBackwardCompatibility:
    """Existing constructor signatures still work unchanged."""

    def test_original_constructor_still_works(self):
        cfg = ObfuscateConfig(
            src_dir="src/", out_dir="dist/",
            html_files=["index.html"],
            static_copy=["robots.txt"],
            js_opts={"compact": False},
            html_opts={"remove-comments": False},
            reserved_names=["^google$"],
            reserved_strings=["^https://"],
            min_script_length=100,
        )
        assert cfg.src_dir == "src/"
        assert cfg.html_files == ["index.html"]
        assert cfg.js_opts["compact"] is False

    def test_no_preset_means_medium(self):
        cfg = ObfuscateConfig(src_dir="src", out_dir="dist")
        medium = ObfuscateConfig(src_dir="src", out_dir="dist", preset="medium")
        assert cfg.js_opts == medium.js_opts

    def test_to_dict_includes_all_new_fields(self):
        cfg = ObfuscateConfig(src_dir="s", out_dir="o")
        d = cfg.to_dict()
        assert "file_types" in d
        assert "stages" in d
        assert "dead_code" in d
        assert "preset" in d
        # Original fields still present
        assert "js_opts" in d
        assert "html_opts" in d
        assert "min_script_length" in d

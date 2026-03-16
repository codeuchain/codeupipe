"""Tests for ObfuscateConfig — configuration object for SPA obfuscation pipeline."""

from codeupipe.deploy.obfuscate.obfuscate_config import (
    ObfuscateConfig,
    DEFAULT_JS_OBFUSCATOR_OPTS,
    DEFAULT_HTML_MINIFIER_OPTS,
    DEFAULT_RESERVED_NAMES,
    DEFAULT_RESERVED_STRINGS,
)


class TestObfuscateConfig:
    def test_defaults(self):
        cfg = ObfuscateConfig(src_dir="src/", out_dir="dist/")
        assert cfg.src_dir == "src/"
        assert cfg.out_dir == "dist/"
        assert cfg.html_files is None  # auto-detect
        assert cfg.static_copy == []
        assert cfg.min_script_length == 50
        assert cfg.js_opts == DEFAULT_JS_OBFUSCATOR_OPTS
        assert cfg.html_opts == DEFAULT_HTML_MINIFIER_OPTS
        assert cfg.reserved_names == DEFAULT_RESERVED_NAMES
        assert cfg.reserved_strings == DEFAULT_RESERVED_STRINGS

    def test_custom_overrides(self):
        cfg = ObfuscateConfig(
            src_dir="src/",
            out_dir="build/",
            html_files=["index.html"],
            static_copy=["robots.txt"],
            js_opts={"compact": False, "custom-flag": True},
            min_script_length=100,
        )
        assert cfg.html_files == ["index.html"]
        assert cfg.static_copy == ["robots.txt"]
        assert cfg.min_script_length == 100
        # Custom opts merge with defaults
        assert cfg.js_opts["compact"] is False
        assert cfg.js_opts["custom-flag"] is True
        # Unmodified defaults preserved
        assert cfg.js_opts["string-array"] is True

    def test_to_dict(self):
        cfg = ObfuscateConfig(src_dir="s", out_dir="o")
        d = cfg.to_dict()
        assert d["src_dir"] == "s"
        assert d["out_dir"] == "o"
        assert "js_opts" in d
        assert "html_opts" in d
        assert "min_script_length" in d

    def test_repr(self):
        cfg = ObfuscateConfig(src_dir="src/", out_dir="dist/")
        r = repr(cfg)
        assert "ObfuscateConfig" in r
        assert "src/" in r
        assert "dist/" in r

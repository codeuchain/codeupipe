"""
Source protection build configuration — tool options, presets, file types, and staging.

Provides sensible defaults inspired by the ZTDC prototype build pipeline.
Users can override any option by passing a custom config dict, choosing a preset,
specifying file types, toggling pipeline stages, and configuring dead code injection.

Config can also be loaded from a JSON or TOML file via ``ObfuscateConfig.from_file()``.
"""

import json
import os
from typing import Any, Dict, List, Optional


# ── JS Obfuscator defaults ──────────────────────────────
# Maps to javascript-obfuscator CLI flags.
# "medium" protection — control flow flattening, string encoding,
# hex identifiers.  Keeps output functional and reasonably sized.

DEFAULT_JS_OBFUSCATOR_OPTS: Dict[str, Any] = {
    "compact": True,
    "control-flow-flattening": True,
    "control-flow-flattening-threshold": 0.3,
    "dead-code-injection": False,
    "identifier-names-generator": "hexadecimal",
    "rename-globals": False,
    "rotate-string-array": True,
    "self-defending": False,
    "string-array": True,
    "string-array-encoding": ["base64"],
    "string-array-threshold": 0.6,
    "string-array-wrappers-count": 1,
    "transform-object-keys": False,
    "unicode-escape-sequence": False,
    "numbers-to-expressions": True,
    "simplify": True,
    "split-strings": False,
    "target": "browser",
}

# Names to preserve so CDN callbacks / DOM APIs still work
DEFAULT_RESERVED_NAMES: List[str] = [
    "^google$",
    "^gapi$",
    "^msal$",
    "^GIS$",
    "^onGoogleLibraryLoad$",
]

DEFAULT_RESERVED_STRINGS: List[str] = [
    "^https://",
    "^wss://",
]


# ── HTML Minifier defaults ──────────────────────────────
# Maps to html-minifier-terser CLI flags.

DEFAULT_HTML_MINIFIER_OPTS: Dict[str, Any] = {
    "collapse-whitespace": True,
    "conservative-collapse": False,
    "remove-comments": True,
    "remove-redundant-attributes": True,
    "remove-empty-attributes": True,
    "remove-optional-tags": False,
    "minify-css": True,
    "minify-js": False,  # we handle JS ourselves via obfuscator
    "collapse-boolean-attributes": True,
    "sort-attributes": True,
    "sort-class-name": True,
    "decode-entities": True,
    "process-conditional-comments": True,
    "trim-custom-fragments": True,
}


# ── Default file types ──────────────────────────────────

DEFAULT_FILE_TYPES: List[Dict[str, Any]] = [
    {
        "extensions": [".html", ".htm"],
        "extract_patterns": [
            {"tag": "script", "exclude_attr": "src"},
        ],
        "tool": "javascript-obfuscator",
        "tool_opts": None,
        "minifier": "html-minifier-terser",
        "minifier_opts": None,
    },
]


# ── Default stages ───────────────────────────────────────

DEFAULT_STAGES: Dict[str, bool] = {
    "scan": True,
    "extract": True,
    "transform": True,
    "reassemble": True,
    "minify": True,
    "write": True,
}


# ── Default dead code config ────────────────────────────

DEFAULT_DEAD_CODE: Dict[str, Any] = {
    "enabled": False,
    "density": "medium",
    "seed": None,
}


# ── Presets ──────────────────────────────────────────────
# Each preset provides overrides applied ON TOP of medium (the base).

PRESETS: Dict[str, Dict[str, Any]] = {
    "light": {
        "js_opts": {
            "control-flow-flattening": False,
            "dead-code-injection": False,
            "string-array": False,
            "rotate-string-array": False,
            "numbers-to-expressions": False,
        },
        "dead_code": {"enabled": False, "density": "low", "seed": None},
        "min_script_length": 100,
    },
    "medium": {
        # Medium IS the default — no overrides needed
        "js_opts": {},
        "dead_code": {"enabled": False, "density": "medium", "seed": None},
        "min_script_length": 50,
    },
    "heavy": {
        "js_opts": {
            "control-flow-flattening": True,
            "control-flow-flattening-threshold": 0.5,
            "dead-code-injection": True,
            "string-array": True,
            "string-array-encoding": ["rc4"],
            "string-array-threshold": 0.8,
            "string-array-wrappers-count": 2,
            "transform-object-keys": True,
            "split-strings": True,
        },
        "dead_code": {"enabled": True, "density": "medium", "seed": None},
        "min_script_length": 30,
    },
    "paranoid": {
        "js_opts": {
            "control-flow-flattening": True,
            "control-flow-flattening-threshold": 0.75,
            "dead-code-injection": True,
            "self-defending": True,
            "string-array": True,
            "string-array-encoding": ["rc4"],
            "string-array-threshold": 1.0,
            "string-array-wrappers-count": 5,
            "transform-object-keys": True,
            "split-strings": True,
            "rename-globals": True,
            "unicode-escape-sequence": True,
        },
        "dead_code": {"enabled": True, "density": "high", "seed": None},
        "min_script_length": 10,
    },
}


class ObfuscateConfig:
    """Configuration for the source protection pipeline.

    Supports preset profiles, configurable file types, per-stage toggling,
    dead code injection, and config file loading — while remaining fully
    backward-compatible with the original constructor.

    Args:
        src_dir: Source directory containing source files.
        out_dir: Output directory for built artifacts.
        preset: Protection level preset (light/medium/heavy/paranoid).
        html_files: Explicit filenames to process (default: auto-detect).
        static_copy: Files/dirs to copy as-is (e.g., agents.txt, .nojekyll).
        js_opts: Override javascript-obfuscator options (merged with preset).
        html_opts: Override html-minifier-terser options.
        reserved_names: JS identifier patterns to preserve.
        reserved_strings: String literal patterns to preserve.
        min_script_length: Minimum inline script length to obfuscate (chars).
        file_types: List of file type configs with extensions, patterns, tools.
        stages: Dict mapping stage names to enabled (True/False).
        dead_code: Dead code injection config (enabled, density, seed).
    """

    def __init__(
        self,
        src_dir: str,
        out_dir: str,
        *,
        preset: Optional[str] = None,
        html_files: Optional[List[str]] = None,
        static_copy: Optional[List[str]] = None,
        js_opts: Optional[Dict[str, Any]] = None,
        html_opts: Optional[Dict[str, Any]] = None,
        reserved_names: Optional[List[str]] = None,
        reserved_strings: Optional[List[str]] = None,
        min_script_length: Optional[int] = None,
        file_types: Optional[List[Dict[str, Any]]] = None,
        stages: Optional[Dict[str, bool]] = None,
        dead_code: Optional[Dict[str, Any]] = None,
    ):
        self.src_dir = src_dir
        self.out_dir = out_dir
        self.html_files = html_files
        self.static_copy = static_copy or []

        # ── Resolve preset ───────────────────────────────
        self.preset = preset
        if preset is not None and preset not in PRESETS:
            raise ValueError(
                f"Unknown preset: {preset!r}. "
                f"Available: {', '.join(sorted(PRESETS.keys()))}"
            )

        preset_data = PRESETS.get(preset or "medium", PRESETS["medium"])
        preset_js = preset_data.get("js_opts", {})
        preset_dead = preset_data.get("dead_code", dict(DEFAULT_DEAD_CODE))
        preset_min_len = preset_data.get("min_script_length", 50)

        # Merge: base defaults ← preset overrides ← user overrides
        self.js_opts = {**DEFAULT_JS_OBFUSCATOR_OPTS, **preset_js, **(js_opts or {})}
        self.html_opts = {**DEFAULT_HTML_MINIFIER_OPTS, **(html_opts or {})}
        self.reserved_names = reserved_names or DEFAULT_RESERVED_NAMES
        self.reserved_strings = reserved_strings or DEFAULT_RESERVED_STRINGS
        self.min_script_length = min_script_length if min_script_length is not None else preset_min_len

        # ── File types ───────────────────────────────────
        self.file_types = file_types if file_types is not None else list(DEFAULT_FILE_TYPES)

        # ── Stages ───────────────────────────────────────
        self.stages = dict(DEFAULT_STAGES)
        if stages:
            self.stages.update(stages)

        # ── Dead code ────────────────────────────────────
        self.dead_code = {**preset_dead}
        if dead_code:
            self.dead_code.update(dead_code)

    @classmethod
    def from_file(cls, path: str) -> "ObfuscateConfig":
        """Load config from a JSON or TOML file.

        Args:
            path: Path to config file (.json or .toml).

        Returns:
            ObfuscateConfig instance.

        Raises:
            FileNotFoundError: If file does not exist.
            ValueError: If file extension is not .json or .toml.
        """
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Config file not found: {path!r}")

        ext = os.path.splitext(path)[1].lower()
        if ext == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        elif ext == ".toml":
            data = _parse_toml(path)
        else:
            raise ValueError(
                f"Unsupported config format: {ext!r}. Use .json or .toml."
            )

        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize config for Payload transport."""
        return {
            "src_dir": self.src_dir,
            "out_dir": self.out_dir,
            "preset": self.preset,
            "html_files": self.html_files,
            "static_copy": self.static_copy,
            "js_opts": self.js_opts,
            "html_opts": self.html_opts,
            "reserved_names": self.reserved_names,
            "reserved_strings": self.reserved_strings,
            "min_script_length": self.min_script_length,
            "file_types": self.file_types,
            "stages": self.stages,
            "dead_code": self.dead_code,
        }

    def __repr__(self) -> str:
        preset_str = f", preset={self.preset!r}" if self.preset else ""
        return (
            f"ObfuscateConfig(src_dir={self.src_dir!r}, "
            f"out_dir={self.out_dir!r}, "
            f"html_files={self.html_files!r}{preset_str})"
        )


def _parse_toml(path: str) -> Dict[str, Any]:
    """Minimal TOML parser — stdlib only (no tomllib in 3.9).

    Handles flat key=value pairs and [section] tables.  Sufficient for
    config files; does NOT support the full TOML spec (nested tables,
    arrays of tables, multiline strings, etc.).
    """
    data: Dict[str, Any] = {}
    current_section: Optional[str] = None

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Section header: [section]
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip()
                if current_section not in data:
                    data[current_section] = {}
                continue

            if "=" not in line:
                continue

            key, raw_value = line.split("=", 1)
            key = key.strip()
            raw_value = raw_value.strip()

            value = _parse_toml_value(raw_value)

            if current_section:
                data[current_section][key] = value
            else:
                data[key] = value

    return data


def _parse_toml_value(raw: str) -> Any:
    """Parse a single TOML value — strings, bools, ints, floats."""
    # Quoted string
    if (raw.startswith('"') and raw.endswith('"')) or \
       (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    # Boolean
    lower = raw.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    # Integer
    try:
        return int(raw)
    except ValueError:
        pass
    # Float
    try:
        return float(raw)
    except ValueError:
        pass
    # Fallback: string
    return raw

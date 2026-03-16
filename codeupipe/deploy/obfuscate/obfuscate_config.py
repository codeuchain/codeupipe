"""
SPA obfuscation build configuration — tool options for JS obfuscation and HTML minification.

Provides sensible defaults inspired by the ZTDC prototype build pipeline.
Users can override any option by passing a custom config dict.
"""

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


class ObfuscateConfig:
    """Configuration for the SPA obfuscation pipeline.

    Args:
        src_dir: Source directory containing readable HTML/JS.
        out_dir: Output directory for built artifacts.
        html_files: HTML filenames to process (default: auto-detect *.html).
        static_copy: Files/dirs to copy as-is (e.g., agents.txt, .nojekyll).
        js_opts: Override javascript-obfuscator options.
        html_opts: Override html-minifier-terser options.
        reserved_names: JS identifier patterns to preserve.
        reserved_strings: String literal patterns to preserve.
        min_script_length: Minimum inline script length to obfuscate (chars).
    """

    def __init__(
        self,
        src_dir: str,
        out_dir: str,
        *,
        html_files: Optional[List[str]] = None,
        static_copy: Optional[List[str]] = None,
        js_opts: Optional[Dict[str, Any]] = None,
        html_opts: Optional[Dict[str, Any]] = None,
        reserved_names: Optional[List[str]] = None,
        reserved_strings: Optional[List[str]] = None,
        min_script_length: int = 50,
    ):
        self.src_dir = src_dir
        self.out_dir = out_dir
        self.html_files = html_files
        self.static_copy = static_copy or []
        self.js_opts = {**DEFAULT_JS_OBFUSCATOR_OPTS, **(js_opts or {})}
        self.html_opts = {**DEFAULT_HTML_MINIFIER_OPTS, **(html_opts or {})}
        self.reserved_names = reserved_names or DEFAULT_RESERVED_NAMES
        self.reserved_strings = reserved_strings or DEFAULT_RESERVED_STRINGS
        self.min_script_length = min_script_length

    def to_dict(self) -> Dict[str, Any]:
        """Serialize config for Payload transport."""
        return {
            "src_dir": self.src_dir,
            "out_dir": self.out_dir,
            "html_files": self.html_files,
            "static_copy": self.static_copy,
            "js_opts": self.js_opts,
            "html_opts": self.html_opts,
            "reserved_names": self.reserved_names,
            "reserved_strings": self.reserved_strings,
            "min_script_length": self.min_script_length,
        }

    def __repr__(self) -> str:
        return (
            f"ObfuscateConfig(src_dir={self.src_dir!r}, "
            f"out_dir={self.out_dir!r}, "
            f"html_files={self.html_files!r})"
        )

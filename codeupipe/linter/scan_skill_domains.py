"""
scan_skill_domains: Discover agent-documentable skill domains in a project.

Walks the project directory, reads ``__init__.py`` exports, and identifies
skill domains suitable for agent-facing documentation. Supports both
auto-discovery and explicit configuration via ``[agent-docs]`` in cup.toml.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class ScanSkillDomains:
    """Discover skill domains for agent documentation.

    Reads ``directory`` from the payload.  If ``agent_docs_config`` is
    present with explicit domain definitions, uses those.  Otherwise
    auto-discovers domains by walking top-level packages.

    Sets ``skill_domains`` on the payload — a list of domain dicts:

    .. code-block:: python

        [
            {
                "name": "core",
                "summary": "Payload, Filter, Pipeline, ...",
                "modules": ["codeupipe/core", "codeupipe/runtime.py"],
                "exports": ["Payload", "Filter", "Pipeline", ...],
                "export_count": 9,
            },
            ...
        ]
    """

    def call(self, payload):
        directory = payload.get("directory", ".")
        config = payload.get("agent_docs_config", {})
        project_name = config.get("project_name", "")

        if config.get("domains"):
            domains = self._from_config(config["domains"], directory)
        else:
            domains = self._auto_discover(directory, project_name)

        return payload.insert("skill_domains", domains)

    # ── Config-driven ────────────────────────────────────────────────

    def _from_config(
        self, domain_defs: List[Dict[str, Any]], directory: str,
    ) -> List[Dict[str, Any]]:
        """Build domain list from explicit config definitions."""
        domains = []
        root = Path(directory)
        for d in domain_defs:
            exports = []
            for mod_path in d.get("modules", []):
                full = root / mod_path
                exports.extend(self._read_exports(full))
            domains.append({
                "name": d["name"],
                "summary": d.get("summary", ""),
                "modules": d.get("modules", []),
                "exports": exports,
                "export_count": len(exports),
            })
        return domains

    # ── Auto-discovery ───────────────────────────────────────────────

    def _auto_discover(
        self, directory: str, project_name: str,
    ) -> List[Dict[str, Any]]:
        """Walk the project and discover skill domains heuristically."""
        root = Path(directory)

        # Find the main package directory
        pkg_dir = self._find_package_dir(root, project_name)
        if pkg_dir is None:
            return []

        domains = []
        seen_names = set()

        # Each subdirectory with __init__.py = candidate domain
        for child in sorted(pkg_dir.iterdir()):
            if not child.is_dir():
                continue
            init = child / "__init__.py"
            if not init.exists():
                continue

            name = child.name
            if name.startswith("_") or name == "__pycache__":
                continue

            exports = self._read_exports(child)
            domains.append({
                "name": name,
                "summary": self._extract_module_docstring(init),
                "modules": [str(child.relative_to(root))],
                "exports": exports,
                "export_count": len(exports),
            })
            seen_names.add(name)

        # Top-level .py files as potential domains (testing.py, runtime.py)
        for py_file in sorted(pkg_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            name = py_file.stem
            if name in seen_names or name == "__init__":
                continue

            exports = self._read_exports(py_file)
            if exports:
                domains.append({
                    "name": name,
                    "summary": self._extract_module_docstring(py_file),
                    "modules": [str(py_file.relative_to(root))],
                    "exports": exports,
                    "export_count": len(exports),
                })

        return domains

    # ── Helpers ──────────────────────────────────────────────────────

    def _find_package_dir(
        self, root: Path, project_name: str,
    ) -> Optional[Path]:
        """Find the main package directory."""
        if project_name:
            candidate = root / project_name
            if candidate.is_dir() and (candidate / "__init__.py").exists():
                return candidate

        # Fallback: look for the first package with __init__.py
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / "__init__.py").exists():
                if not child.name.startswith((".", "_")):
                    return child
        return None

    def _read_exports(self, path: Path) -> List[str]:
        """Read __all__ from a module or package __init__.py."""
        if path.is_dir():
            path = path / "__init__.py"
        if not path.exists():
            return []

        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            return []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        return self._extract_list_strings(node.value)
        return []

    @staticmethod
    def _extract_list_strings(node: ast.expr) -> List[str]:
        """Extract string values from an AST list/tuple literal."""
        if isinstance(node, (ast.List, ast.Tuple)):
            result = []
            for elt in node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    result.append(elt.value)
            return result
        return []

    @staticmethod
    def _extract_module_docstring(path: Path) -> str:
        """Extract the first line of a module's docstring."""
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            return ""

        docstring = ast.get_docstring(tree)
        if docstring:
            first_line = docstring.strip().split("\n")[0]
            # Strip common prefixes
            for prefix in ("codeupipe.", "``", "cup "):
                if first_line.startswith(prefix):
                    first_line = first_line[len(prefix):]
            return first_line.strip().rstrip(".")
        return ""

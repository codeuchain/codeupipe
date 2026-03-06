"""
ScanComponents: Discover all CUP components and their public methods.
"""

import ast
from pathlib import Path
from typing import Optional

from codeupipe import Payload

from .scan_directory import classify_class


def _extract_public_methods(node: ast.ClassDef) -> list:
    """Extract public method names from a class AST node."""
    return [
        n.name
        for n in ast.iter_child_nodes(node)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not n.name.startswith("_")
    ]


def _extract_public_functions(tree: ast.Module) -> list:
    """Extract top-level public function names from a module."""
    return [
        n.name
        for n in ast.iter_child_nodes(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not n.name.startswith("_")
    ]


class ScanComponents:
    """
    Filter (sync): Parse component directory and catalog each
    component class with its public methods.

    Input keys:
        - directory (str): path to the component directory

    Output keys (added):
        - components (list[dict]): each with keys:
            - file (str): relative filepath
            - stem (str): filename without .py
            - name (str): class or function name
            - kind (str): component type (filter, tap, hook, stream-filter, builder)
            - methods (list[str]): public method names
    """

    def call(self, payload: Payload) -> Payload:
        directory = payload.get("directory")
        dir_path = Path(directory)

        if not dir_path.is_dir():
            raise FileNotFoundError(f"Directory not found: {directory}")

        components = []

        for py_file in sorted(dir_path.glob("*.py")):
            if py_file.name == "__init__.py":
                continue

            try:
                source = py_file.read_text()
                tree = ast.parse(source, filename=str(py_file))
            except (SyntaxError, OSError):
                continue

            rel = str(py_file)
            stem = py_file.stem

            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                    ctype = classify_class(node)
                    if ctype is not None:
                        methods = _extract_public_methods(node)
                        components.append({
                            "file": rel,
                            "stem": stem,
                            "name": node.name,
                            "kind": ctype,
                            "methods": methods,
                        })
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("_") and node.name.startswith("build_"):
                        components.append({
                            "file": rel,
                            "stem": stem,
                            "name": node.name,
                            "kind": "builder",
                            "methods": [],
                        })

        return payload.insert("components", components)

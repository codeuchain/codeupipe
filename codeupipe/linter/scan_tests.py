"""
ScanTests: Discover test files and extract tested symbols.
"""

import ast
import re
from pathlib import Path

from codeupipe import Payload


def _extract_imports(tree: ast.Module) -> set:
    """Extract all imported names from a module AST."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in (node.names or []):
                names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in (node.names or []):
                names.add(alias.name.split(".")[-1])
    return names


def _extract_test_methods(tree: ast.Module) -> list:
    """Extract test method names from test classes and top-level test functions."""
    methods = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name.startswith("test_"):
                        methods.append(child.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                methods.append(node.name)
    return methods


def _extract_tested_methods(tree: ast.Module) -> set:
    """Extract method names referenced in test bodies via attribute access.

    Looks for patterns like `obj.call(`, `obj.observe(`, `filter.call(` etc.
    """
    tested = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            tested.add(node.attr)
    return tested


class ScanTests:
    """
    Filter (sync): Parse test files and map which component symbols are tested.

    Input keys:
        - components (list[dict]): from ScanComponents
        - tests_dir (str, optional): path to tests directory (default: "tests")

    Output keys (added):
        - test_map (list[dict]): each with keys:
            - test_file (str): path to the test file
            - stem (str): component stem the test covers
            - imports (set[str]): imported symbol names
            - test_methods (list[str]): test_* method names
            - referenced_methods (set[str]): methods called in test bodies
    """

    def call(self, payload: Payload) -> Payload:
        components = payload.get("components", [])
        tests_dir = Path(payload.get("tests_dir", "tests"))

        test_map = []

        # Build a set of stems we know about
        known_stems = {c["stem"] for c in components}

        # Scan test files that correspond to known component stems
        if tests_dir.is_dir():
            for test_file in sorted(tests_dir.glob("test_*.py")):
                # test_validate_email.py → validate_email
                stem = test_file.stem[5:]  # strip "test_"
                if stem not in known_stems:
                    continue

                try:
                    source = test_file.read_text()
                    tree = ast.parse(source, filename=str(test_file))
                except (SyntaxError, OSError):
                    continue

                imports = _extract_imports(tree)
                test_methods = _extract_test_methods(tree)
                referenced = _extract_tested_methods(tree)

                test_map.append({
                    "test_file": str(test_file),
                    "stem": stem,
                    "imports": imports,
                    "test_methods": test_methods,
                    "referenced_methods": referenced,
                })

        return payload.insert("test_map", test_map)

"""
ScanDirectory: Discover and AST-analyze all .py files in a directory.
"""

import ast
import re
from pathlib import Path
from typing import Optional

from codeupipe import Payload


_SNAKE_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")


def classify_class(node: ast.ClassDef) -> Optional[str]:
    """Classify an AST class node as a CUP component type or None."""
    methods = {
        n.name
        for n in ast.iter_child_nodes(node)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    for base in node.bases:
        base_name = getattr(base, "id", None) or getattr(
            getattr(base, "attr", None), "__str__", lambda: ""
        )()
        if base_name == "Hook":
            return "hook"

    if "stream" in methods:
        return "stream-filter"
    if "call" in methods:
        return "filter"
    if "observe" in methods:
        return "tap"

    return None


def analyze_file(filepath: Path) -> dict:
    """Analyze a single Python file and return component info.

    Returns dict with:
        'path': str filepath
        'stem': filename without .py
        'classes': list of (name, component_type, methods)
        'functions': list of function names
        'error': parse error string or None
    """
    try:
        source = filepath.read_text()
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError as e:
        return {
            "path": str(filepath),
            "stem": filepath.stem,
            "classes": [],
            "functions": [],
            "error": str(e),
        }
    except OSError as e:
        return {
            "path": str(filepath),
            "stem": filepath.stem,
            "classes": [],
            "functions": [],
            "error": str(e),
        }

    classes = []
    functions = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            methods = {
                n.name
                for n in ast.iter_child_nodes(node)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            ctype = classify_class(node)
            classes.append((node.name, ctype, methods))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                functions.append(node.name)

    return {
        "path": str(filepath),
        "stem": filepath.stem,
        "classes": classes,
        "functions": functions,
        "error": None,
    }


class ScanDirectory:
    """
    Filter (sync): Read a directory and AST-analyze every .py file.

    Input keys:
        - directory (str): path to the directory to scan

    Output keys (added):
        - files (list[dict]): analysis of each .py file
        - issues (list): initialized empty issue list
    """

    def call(self, payload: Payload) -> Payload:
        directory = payload.get("directory")
        dir_path = Path(directory)

        if not dir_path.is_dir():
            raise FileNotFoundError(f"Directory not found: {directory}")

        files = []
        for py_file in sorted(dir_path.glob("*.py")):
            if py_file.name == "__init__.py":
                continue
            files.append(analyze_file(py_file))

        payload = payload.insert("files", files)
        payload = payload.insert("issues", [])
        return payload

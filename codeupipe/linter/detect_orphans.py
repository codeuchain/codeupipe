"""
DetectOrphans: Find unreferenced components and stale test files.
"""

import ast
from pathlib import Path

from codeupipe import Payload


def _extract_imported_names(tree: ast.Module) -> set:
    """Extract all names imported from relative or absolute imports."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in (node.names or []):
                names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in (node.names or []):
                names.add(alias.name.split(".")[-1])
    return names


class DetectOrphans:
    """
    Filter (sync): Detect orphaned components and orphaned test files.

    Orphaned component = never imported by any other .py file in the directory
    (excluding __init__.py re-exports and test files).

    Orphaned test = test_*.py file whose stem doesn't match any component.

    Input keys:
        - components (list[dict]): from ScanComponents
        - directory (str): component directory path
        - tests_dir (str, optional): test directory path

    Output keys (added):
        - orphaned_components (list[dict]): components never imported
        - orphaned_tests (list[dict]): test files with no matching component
        - import_map (dict[str, list[str]]): component_name → list of importing files
    """

    def call(self, payload: Payload) -> Payload:
        components = payload.get("components", [])
        directory = payload.get("directory", "")
        tests_dir_str = payload.get("tests_dir", "tests")

        dir_path = Path(directory)
        component_names = {c["name"] for c in components}
        component_stems = {c["stem"] for c in components}

        # Build import map: which files import each component name
        import_map = {name: [] for name in component_names}

        if dir_path.is_dir():
            for py_file in sorted(dir_path.glob("*.py")):
                # Skip __init__.py (re-exports don't count as real usage)
                if py_file.name == "__init__.py":
                    continue
                # Skip test files in the component directory
                if py_file.name.startswith("test_"):
                    continue

                try:
                    source = py_file.read_text()
                    tree = ast.parse(source, filename=str(py_file))
                except (SyntaxError, OSError):
                    continue

                imported = _extract_imported_names(tree)
                for name in component_names:
                    if name in imported:
                        # Don't count self-imports (file that defines the component)
                        comp = next((c for c in components if c["name"] == name), None)
                        if comp and Path(comp["file"]).name == py_file.name:
                            continue
                        import_map[name].append(py_file.name)

        # Orphaned components: never imported by anyone
        orphaned_components = []
        for comp in components:
            importers = import_map.get(comp["name"], [])
            if not importers:
                orphaned_components.append({
                    "name": comp["name"],
                    "kind": comp["kind"],
                    "file": comp["file"],
                })

        # Orphaned tests: test_*.py files whose stem doesn't match any component
        orphaned_tests = []
        tests_dir = Path(tests_dir_str)
        if tests_dir.is_dir():
            for test_file in sorted(tests_dir.glob("test_*.py")):
                stem = test_file.stem[5:]  # strip "test_"
                if stem not in component_stems:
                    orphaned_tests.append({
                        "file": str(test_file),
                        "stem": stem,
                    })

        payload = payload.insert("orphaned_components", orphaned_components)
        payload = payload.insert("orphaned_tests", orphaned_tests)
        payload = payload.insert("import_map", import_map)
        return payload

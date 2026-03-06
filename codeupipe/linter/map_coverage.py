"""
MapCoverage: Cross-reference components against tests to build coverage map.
"""

from codeupipe import Payload


class MapCoverage:
    """
    Filter (sync): Join components and test_map to produce per-component coverage.

    Input keys:
        - components (list[dict]): from ScanComponents
        - test_map (list[dict]): from ScanTests

    Output keys (added):
        - coverage (list[dict]): each with keys:
            - name (str): component class/function name
            - kind (str): component type
            - file (str): source file path
            - has_test_file (bool): whether a test file exists
            - test_count (int): number of test_* methods
            - methods (list[str]): public method names
            - tested_methods (list[str]): methods referenced in tests
            - untested_methods (list[str]): methods not referenced in tests
            - coverage_pct (float): percentage of methods covered (0-100)
    """

    def call(self, payload: Payload) -> Payload:
        components = payload.get("components", [])
        test_map = payload.get("test_map", [])

        # Index test_map by stem for fast lookup
        test_index = {}
        for entry in test_map:
            stem = entry["stem"]
            if stem not in test_index:
                test_index[stem] = {
                    "test_methods": [],
                    "referenced_methods": set(),
                    "imports": set(),
                }
            test_index[stem]["test_methods"].extend(entry["test_methods"])
            test_index[stem]["referenced_methods"] |= entry["referenced_methods"]
            test_index[stem]["imports"] |= entry["imports"]

        coverage = []

        for comp in components:
            stem = comp["stem"]
            name = comp["name"]
            kind = comp["kind"]
            methods = comp["methods"]
            test_info = test_index.get(stem)

            has_test = test_info is not None
            test_count = len(test_info["test_methods"]) if test_info else 0
            referenced = test_info["referenced_methods"] if test_info else set()

            # For builders (functions), check if the name itself is imported
            if kind == "builder":
                tested = [name] if (test_info and name in test_info["imports"]) else []
                untested = [] if tested else [name]
                total = 1
            else:
                tested = [m for m in methods if m in referenced]
                untested = [m for m in methods if m not in referenced]
                total = len(methods)

            pct = (len(tested) / total * 100) if total > 0 else 100.0

            coverage.append({
                "name": name,
                "kind": kind,
                "file": comp["file"],
                "has_test_file": has_test,
                "test_count": test_count,
                "methods": methods if kind != "builder" else [name],
                "tested_methods": tested,
                "untested_methods": untested,
                "coverage_pct": round(pct, 1),
            })

        return payload.insert("coverage", coverage)

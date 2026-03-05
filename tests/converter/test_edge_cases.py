"""
Edge case tests for the converter — covering tricky inputs,
boundary conditions, and real-world code patterns.
"""

import json
import pytest
from pathlib import Path
from codeupipe import Payload, Pipeline, Valve, Hook

from codeupipe.converter.config import load_config, PATTERN_DEFAULTS
from codeupipe.converter.filters.parse_config import ParseConfigFilter
from codeupipe.converter.filters.analyze import AnalyzePipelineFilter
from codeupipe.converter.filters.classify import ClassifyStepsFilter, _match_role
from codeupipe.converter.filters.classify_files import ClassifyFilesFilter, _match_dir_to_role
from codeupipe.converter.filters.generate_export import GenerateExportFilter
from codeupipe.converter.filters.generate_import import (
    GenerateImportFilter, _extract_functions, _indent_body, _generate_filter_class,
    _generate_tap_class, _generate_pipeline,
)
from codeupipe.converter.filters.scan_project import ScanProjectFilter
from codeupipe.converter.taps.conversion_log import ConversionLogTap


# ══════════════════════════════════════════════
# Config Edge Cases
# ══════════════════════════════════════════════

class TestConfigEdgeCases:
    def test_malformed_json_raises(self, tmp_path):
        bad_file = tmp_path / ".cup.json"
        bad_file.write_text("{not valid json!!!")

        with pytest.raises(json.JSONDecodeError):
            load_config(config_path=str(bad_file))

    def test_nonexistent_config_path_returns_default(self):
        config = load_config(config_path="/tmp/does_not_exist_abc123.cup.json")
        assert config["pattern"] == "flat"

    def test_non_json_extension_ignored(self, tmp_path):
        yaml_file = tmp_path / ".cup.yaml"
        yaml_file.write_text("pattern: mvc")
        config = load_config(config_path=str(yaml_file))
        assert config["pattern"] == "flat"

    def test_empty_roles_in_config(self, tmp_path):
        config_file = tmp_path / ".cup.json"
        config_file.write_text(json.dumps({"pattern": "mvc", "roles": {}}))
        config = load_config(config_path=str(config_file))
        assert config["roles"] == {}

    def test_partial_role_override(self, tmp_path):
        config_file = tmp_path / ".cup.json"
        config_file.write_text(json.dumps({
            "pattern": "mvc",
            "roles": {"model": ["my_model_*"]},
        }))
        config = load_config(config_path=str(config_file))
        # Should use overridden roles, not merge with defaults
        assert config["roles"] == {"model": ["my_model_*"]}

    def test_custom_output_base(self, tmp_path):
        config_file = tmp_path / ".cup.json"
        config_file.write_text(json.dumps({
            "pattern": "mvc",
            "output": {"base": "lib/"},
        }))
        config = load_config(config_path=str(config_file))
        assert config["output"]["base"] == "lib/"
        # Pattern defaults for directories should still be present
        assert "models/" in config["output"].values()

    def test_extra_unknown_keys_ignored(self, tmp_path):
        config_file = tmp_path / ".cup.json"
        config_file.write_text(json.dumps({
            "pattern": "flat",
            "author": "test",
            "debug": True,
        }))
        config = load_config(config_path=str(config_file))
        assert config["pattern"] == "flat"

    def test_config_path_takes_precedence_over_pattern(self, tmp_path):
        config_file = tmp_path / ".cup.json"
        config_file.write_text(json.dumps({"pattern": "clean"}))
        config = load_config(config_path=str(config_file), pattern="mvc")
        assert config["pattern"] == "clean"

    def test_all_patterns_have_non_empty_roles(self):
        for name, defaults in PATTERN_DEFAULTS.items():
            for role, patterns in defaults["roles"].items():
                assert len(patterns) > 0, f"{name}.{role} has empty patterns"

    def test_all_patterns_have_matching_output_dirs(self):
        for name, defaults in PATTERN_DEFAULTS.items():
            for role in defaults["roles"]:
                assert role in defaults["output"], f"{name} role '{role}' has no output dir"


# ══════════════════════════════════════════════
# ParseConfigFilter Edge Cases
# ══════════════════════════════════════════════

class TestParseConfigEdgeCases:
    def test_both_config_path_and_pattern_prefers_file(self, tmp_path):
        config_file = tmp_path / ".cup.json"
        config_file.write_text(json.dumps({"pattern": "hexagonal"}))
        f = ParseConfigFilter()
        result = f.call(Payload({"config_path": str(config_file), "pattern": "mvc"}))
        assert result.get("config")["pattern"] == "hexagonal"

    def test_none_values_fall_through(self):
        f = ParseConfigFilter()
        result = f.call(Payload({"config_path": None, "pattern": None}))
        assert result.get("config")["pattern"] == "flat"


# ══════════════════════════════════════════════
# AnalyzePipelineFilter Edge Cases
# ══════════════════════════════════════════════

class TestAnalyzeEdgeCases:
    def test_empty_pipeline(self):
        p = Pipeline()
        f = AnalyzePipelineFilter()
        result = f.call(Payload({"pipeline": p}))
        assert result.get("steps") == []
        assert result.get("hooks") == []

    def test_only_taps_no_filters(self):
        class LogTap:
            def observe(self, payload):
                pass

        class MetricsTap:
            def observe(self, payload):
                pass

        p = Pipeline()
        p.add_tap(LogTap(), name="log")
        p.add_tap(MetricsTap(), name="metrics")

        f = AnalyzePipelineFilter()
        result = f.call(Payload({"pipeline": p}))
        steps = result.get("steps")
        assert len(steps) == 2
        assert all(s["type"] == "tap" for s in steps)

    def test_only_hooks_no_steps(self):
        class AuditHook(Hook):
            pass

        p = Pipeline()
        p.use_hook(AuditHook())

        f = AnalyzePipelineFilter()
        result = f.call(Payload({"pipeline": p}))
        assert result.get("steps") == []
        assert len(result.get("hooks")) == 1

    def test_dynamic_filter_no_source(self):
        """Dynamically created filter class — inspect.getsource fails."""
        DynFilter = type("DynFilter", (), {"call": lambda self, p: p})
        p = Pipeline()
        p.add_filter(DynFilter(), name="dynamic")

        f = AnalyzePipelineFilter()
        result = f.call(Payload({"pipeline": p}))
        steps = result.get("steps")
        assert steps[0]["name"] == "dynamic"
        assert steps[0]["source"] is None

    def test_multiple_hooks(self):
        class HookA(Hook):
            pass

        class HookB(Hook):
            pass

        p = Pipeline()
        p.use_hook(HookA())
        p.use_hook(HookB())

        f = AnalyzePipelineFilter()
        result = f.call(Payload({"pipeline": p}))
        hooks = result.get("hooks")
        assert len(hooks) == 2
        names = {h["class_name"] for h in hooks}
        assert names == {"HookA", "HookB"}

    def test_multiple_valves(self):
        class FilterA:
            def call(self, payload):
                return payload

        class FilterB:
            def call(self, payload):
                return payload

        p = Pipeline()
        p.add_filter(Valve("gate_a", FilterA(), lambda p: True), name="gate_a")
        p.add_filter(Valve("gate_b", FilterB(), lambda p: False), name="gate_b")

        f = AnalyzePipelineFilter()
        result = f.call(Payload({"pipeline": p}))
        steps = result.get("steps")
        valves = [s for s in steps if s["is_valve"]]
        assert len(valves) == 2

    def test_large_pipeline_many_steps(self):
        """Pipeline with 20 filters — tests scalability."""
        p = Pipeline()
        for i in range(20):
            cls = type(f"Step{i}", (), {"call": lambda self, payload: payload})
            p.add_filter(cls(), name=f"step_{i}")

        f = AnalyzePipelineFilter()
        result = f.call(Payload({"pipeline": p}))
        assert len(result.get("steps")) == 20


# ══════════════════════════════════════════════
# ClassifySteps Edge Cases
# ══════════════════════════════════════════════

class TestClassifyEdgeCases:
    def test_overlapping_role_patterns_first_wins(self):
        """When a name matches multiple roles, the first role in dict order wins."""
        # Python 3.7+ dicts are ordered
        roles = {
            "model": ["fetch_*"],
            "controller": ["fetch_*"],
        }
        result = _match_role("fetch_user", "filter", roles)
        assert result == "model"

    def test_all_uncategorized(self):
        roles = {"model": ["db_*"]}
        steps = [
            {"name": "alpha", "type": "filter", "class_name": "Alpha"},
            {"name": "beta", "type": "filter", "class_name": "Beta"},
        ]
        f = ClassifyStepsFilter()
        result = f.call(Payload({
            "steps": steps, "hooks": [], "config": {"roles": roles},
        }))
        classified = result.get("classified")
        assert "uncategorized" in classified
        assert len(classified["uncategorized"]) == 2

    def test_empty_steps_list(self):
        f = ClassifyStepsFilter()
        result = f.call(Payload({
            "steps": [], "hooks": [], "config": {"roles": {"model": ["*"]}},
        }))
        assert result.get("classified") == {}

    def test_step_name_with_numbers(self):
        roles = {"model": ["fetch_*"]}
        assert _match_role("fetch_v2", "filter", roles) == "model"
        assert _match_role("fetch_123", "filter", roles) == "model"

    def test_step_name_case_sensitivity(self):
        """fnmatch is case-sensitive on most platforms."""
        roles = {"model": ["fetch_*"]}
        # Capital letters shouldn't match lowercase glob
        assert _match_role("Fetch_User", "filter", roles) == "uncategorized"
        # Same case should match
        assert _match_role("fetch_User", "filter", roles) == "model"

    def test_type_token_exact_match_only(self):
        """_tap should match type 'tap' but not name containing 'tap'."""
        roles = {"middleware": ["_tap"]}
        # Type token match
        assert _match_role("anything", "tap", roles) == "middleware"
        # Name glob: _tap matches names starting with _ and containing tap
        # Actually _tap as a glob pattern would match the literal string "_tap"
        assert _match_role("_tap_something", "filter", roles) == "uncategorized"

    def test_wildcard_star_catches_all(self):
        roles = {"everything": ["*"]}
        assert _match_role("anything_goes", "filter", roles) == "everything"
        assert _match_role("x", "tap", roles) == "everything"

    def test_mixed_globs_and_type_tokens(self):
        roles = {
            "model": ["fetch_*", "save_*"],
            "middleware": ["_tap", "_valve", "log_*"],
        }
        # Glob match
        assert _match_role("log_request", "filter", roles) == "middleware"
        # Type token match
        assert _match_role("my_audit", "tap", roles) == "middleware"
        # Uncategorized
        assert _match_role("process_data", "filter", roles) == "uncategorized"


# ══════════════════════════════════════════════
# ClassifyFiles Edge Cases
# ══════════════════════════════════════════════

class TestClassifyFilesEdgeCases:
    def test_root_level_files(self):
        """Files at project root (dir='') should be uncategorized."""
        dir_map = {"models": "model"}
        assert _match_dir_to_role("", dir_map) == "uncategorized"

    def test_deeply_nested_files(self):
        dir_map = {"models": "model"}
        # Should still match — starts with "models"
        assert _match_dir_to_role("models/v2/legacy", dir_map) == "model"

    def test_partial_dir_name_no_false_match(self):
        """'models_backup' should NOT match 'models'."""
        dir_map = {"models": "model"}
        assert _match_dir_to_role("models_backup", dir_map) == "uncategorized"

    def test_no_false_match_on_substring(self):
        """'model' should NOT match 'models' (exact match required)."""
        dir_map = {"models": "model"}
        assert _match_dir_to_role("model", dir_map) == "uncategorized"

    def test_empty_source_files(self):
        f = ClassifyFilesFilter()
        config = load_config(pattern="mvc")
        result = f.call(Payload({"source_files": [], "config": config}))
        assert result.get("classified_files") == {}

    def test_same_filename_different_dirs(self):
        config = load_config(pattern="mvc")
        source_files = [
            {"name": "utils", "dir": "models", "content": "pass"},
            {"name": "utils", "dir": "views", "content": "pass"},
        ]
        f = ClassifyFilesFilter()
        result = f.call(Payload({"source_files": source_files, "config": config}))
        classified = result.get("classified_files")
        assert len(classified.get("model", [])) == 1
        assert len(classified.get("view", [])) == 1

    def test_trailing_slashes_normalized(self):
        dir_map = {"models/": "model"}  # note the slash in key
        # After normalization (rstrip /), key becomes "models"
        assert _match_dir_to_role("models", dir_map) == "model"


# ══════════════════════════════════════════════
# GenerateExport Edge Cases
# ══════════════════════════════════════════════

class TestGenerateExportEdgeCases:
    def test_empty_pipeline_generates_empty_orchestrator(self):
        f = GenerateExportFilter()
        result = f.call(Payload({
            "classified": {},
            "config": load_config(pattern="flat"),
            "steps": [],
            "hooks": [],
        }))
        files = result.get("files")
        assert len(files) == 1  # just orchestrator
        orch = files[0]
        assert "pipeline.py" in orch["path"]
        assert "def run_pipeline" in orch["content"]
        compile(orch["content"], "pipeline.py", "exec")

    def test_step_name_with_numbers_generates_valid_python(self):
        classified = {
            "step": [{"name": "step_1", "type": "filter", "class_name": "Step1", "source": None}],
        }
        f = GenerateExportFilter()
        result = f.call(Payload({
            "classified": classified,
            "config": load_config(pattern="flat"),
            "steps": [{"name": "step_1", "type": "filter"}],
            "hooks": [],
        }))
        for file in result.get("files"):
            compile(file["content"], file["path"], "exec")

    def test_multiple_valves_each_get_predicate(self):
        classified = {
            "middleware": [
                {"name": "gate_a", "type": "valve", "class_name": "Valve", "source": None},
                {"name": "gate_b", "type": "valve", "class_name": "Valve", "source": None},
            ],
        }
        steps = [
            {"name": "gate_a", "type": "valve"},
            {"name": "gate_b", "type": "valve"},
        ]
        f = GenerateExportFilter()
        result = f.call(Payload({
            "classified": classified,
            "config": load_config(pattern="mvc"),
            "steps": steps,
            "hooks": [],
        }))
        files = result.get("files")
        gate_a = next(f for f in files if "gate_a.py" in f["path"])
        gate_b = next(f for f in files if "gate_b.py" in f["path"])
        assert "def gate_a_predicate" in gate_a["content"]
        assert "def gate_b_predicate" in gate_b["content"]

        # All valid Python
        for file in files:
            compile(file["content"], file["path"], "exec")

    def test_hook_generates_class_not_function(self):
        classified = {
            "middleware": [{"class_name": "TimingHook", "type": "hook", "source": None}],
        }
        f = GenerateExportFilter()
        result = f.call(Payload({
            "classified": classified,
            "config": load_config(pattern="mvc"),
            "steps": [],
            "hooks": [{"class_name": "TimingHook", "type": "hook"}],
        }))
        files = result.get("files")
        hook_file = next(f for f in files if "TimingHook" in f["path"])
        assert "class TimingHookHook:" in hook_file["content"]
        assert "def before(" in hook_file["content"]
        assert "def after(" in hook_file["content"]
        assert "def on_error(" in hook_file["content"]
        compile(hook_file["content"], hook_file["path"], "exec")

    def test_nested_output_dir_generates_correct_imports(self):
        """Hexagonal adapters/inbound/ should produce dotted module imports."""
        classified = {
            "adapter_inbound": [
                {"name": "parse_request", "type": "filter", "class_name": "ParseRequest", "source": None}
            ],
        }
        config = load_config(pattern="hexagonal")
        steps = [{"name": "parse_request", "type": "filter"}]

        f = GenerateExportFilter()
        result = f.call(Payload({
            "classified": classified,
            "config": config,
            "steps": steps,
            "hooks": [],
        }))
        files = result.get("files")
        orch = next(f for f in files if "pipeline.py" in f["path"])
        # Import should use dot notation for nested dirs
        assert "adapters.inbound.parse_request" in orch["content"]

    def test_source_with_triple_quotes_embedded(self):
        """Source containing triple-quoted docstrings shouldn't break export."""
        source = '''class FetchUser:
    """Fetch a user from the database.

    Returns the user dict.
    """
    def call(self, payload):
        return payload'''

        classified = {
            "model": [{
                "name": "fetch_user",
                "type": "filter",
                "class_name": "FetchUser",
                "source": source,
            }],
        }
        f = GenerateExportFilter()
        result = f.call(Payload({
            "classified": classified,
            "config": load_config(pattern="mvc"),
            "steps": [{"name": "fetch_user", "type": "filter"}],
            "hooks": [],
        }))
        for file in result.get("files"):
            # Source is embedded as comments, so it's safe
            compile(file["content"], file["path"], "exec")

    def test_orchestrator_preserves_step_order(self):
        """Step order in orchestrator must match pipeline order, not role grouping."""
        classified = {
            "controller": [
                {"name": "validate_input", "type": "filter", "class_name": "V", "source": None},
            ],
            "model": [
                {"name": "fetch_data", "type": "filter", "class_name": "F", "source": None},
            ],
        }
        # Original order: fetch first, then validate
        steps = [
            {"name": "fetch_data", "type": "filter"},
            {"name": "validate_input", "type": "filter"},
        ]
        f = GenerateExportFilter()
        result = f.call(Payload({
            "classified": classified,
            "config": load_config(pattern="mvc"),
            "steps": steps,
            "hooks": [],
        }))
        orch = next(f for f in result.get("files") if "pipeline.py" in f["path"])
        content = orch["content"]
        # fetch_data should appear before validate_input in the orchestrator body
        assert content.index("fetch_data(data)") < content.index("validate_input(data)")


# ══════════════════════════════════════════════
# GenerateImport Edge Cases
# ══════════════════════════════════════════════

class TestGenerateImportEdgeCases:
    def test_extract_functions_empty_source(self):
        assert _extract_functions("") == []

    def test_extract_functions_no_functions(self):
        source = '''
import os

MY_CONSTANT = 42

class NotAFunction:
    pass
'''
        assert _extract_functions(source) == []

    def test_extract_functions_only_pass_body(self):
        source = "def noop(data: dict) -> dict:\n    pass\n"
        fns = _extract_functions(source)
        assert len(fns) == 1
        assert fns[0][0] == "noop"
        assert "pass" in fns[0][2]

    def test_extract_functions_decorated(self):
        """Decorated functions — the regex should still find the def line."""
        source = '''
@some_decorator
def fetch_user(data: dict) -> dict:
    return data
'''
        fns = _extract_functions(source)
        assert len(fns) == 1
        assert fns[0][0] == "fetch_user"

    def test_extract_functions_default_args(self):
        source = 'def process(data: dict = None, verbose: bool = False) -> dict:\n    return data or {}\n'
        fns = _extract_functions(source)
        assert len(fns) == 1
        assert fns[0][0] == "process"

    def test_extract_functions_complex_return_type(self):
        source = 'def fetch(data: dict) -> dict:\n    data["x"] = 1\n    return data\n'
        fns = _extract_functions(source)
        assert len(fns) == 1
        assert fns[0][3] is True  # returns_value

    def test_extract_functions_returns_none_explicitly(self):
        source = "def log_it(data: dict) -> None:\n    print(data)\n    return None\n"
        fns = _extract_functions(source)
        assert len(fns) == 1
        assert fns[0][3] is False  # doesn't return dict

    def test_extract_functions_no_return_statement(self):
        source = "def side_effect(data: dict) -> None:\n    print(data)\n"
        fns = _extract_functions(source)
        assert len(fns) == 1
        assert fns[0][3] is False

    def test_extract_functions_nested_def_treated_as_separate(self):
        """Nested function defs — only top-level should ideally be extracted.
        Current regex matches all top-of-line defs. Inner defs are indented,
        so the regex (anchored with ^) should skip them."""
        source = '''def outer(data: dict) -> dict:
    def inner():
        pass
    return data
'''
        fns = _extract_functions(source)
        # Only outer should be extracted (inner is indented)
        assert len(fns) == 1
        assert fns[0][0] == "outer"

    def test_extract_functions_multiple_with_blank_lines(self):
        source = '''def alpha(data: dict) -> dict:
    data["a"] = 1
    return data


def beta(data: dict) -> dict:
    data["b"] = 2
    return data
'''
        fns = _extract_functions(source)
        assert len(fns) == 2

    def test_indent_body_empty_string(self):
        result = _indent_body("")
        assert result == ""

    def test_indent_body_single_line(self):
        result = _indent_body("    return data")
        assert result == "        return data"

    def test_indent_body_preserves_nested_indent(self):
        body = "    if x:\n        do_something()\n    return data"
        result = _indent_body(body)
        lines = result.split("\n")
        assert lines[0] == "        if x:"
        assert lines[1] == "            do_something()"
        assert lines[2] == "        return data"

    def test_indent_body_mixed_indent_levels(self):
        body = "    try:\n        result = process()\n    except Exception:\n        result = None\n    return result"
        result = _indent_body(body)
        lines = result.split("\n")
        assert lines[0] == "        try:"
        assert lines[1] == "            result = process()"
        assert lines[2] == "        except Exception:"
        assert lines[3] == "            result = None"
        assert lines[4] == "        return result"

    def test_indent_body_with_blank_lines(self):
        body = "    x = 1\n\n    y = 2"
        result = _indent_body(body)
        lines = result.split("\n")
        assert lines[0] == "        x = 1"
        assert lines[1] == ""
        assert lines[2] == "        y = 2"

    def test_generate_filter_class_valid_python(self):
        code = _generate_filter_class("process_data", "    data['result'] = 42\n    return data")
        compile(code, "test.py", "exec")
        assert "class ProcessDataFilter:" in code
        assert "def call(self, payload)" in code

    def test_generate_tap_class_valid_python(self):
        code = _generate_tap_class("log_event", "    print(data)")
        compile(code, "test.py", "exec")
        assert "class LogEventTap:" in code
        assert "def observe(self, payload)" in code

    def test_generate_pipeline_empty_steps(self):
        code = _generate_pipeline([])
        compile(code, "test.py", "exec")
        assert "def build_pipeline" in code

    def test_generate_pipeline_mixed_types(self):
        steps = [
            {"name": "fetch_user", "type": "filter"},
            {"name": "log_request", "type": "tap"},
            {"name": "save_user", "type": "filter"},
        ]
        code = _generate_pipeline(steps)
        compile(code, "test.py", "exec")
        assert "FetchUserFilter" in code
        assert "LogRequestTap" in code
        assert "SaveUserFilter" in code
        assert "add_filter" in code
        assert "add_tap" in code

    def test_full_import_with_files_containing_no_functions(self):
        """Files with only classes/constants should be skipped gracefully."""
        classified_files = {
            "model": [
                {"name": "constants", "content": "MAX_RETRIES = 3\nTIMEOUT = 30\n"},
                {"name": "fetch_user", "content": 'def fetch_user(data: dict) -> dict:\n    data["user"] = "alice"\n    return data\n'},
            ],
        }
        f = GenerateImportFilter()
        result = f.call(Payload({
            "classified_files": classified_files,
            "config": load_config(pattern="mvc"),
        }))
        cup_files = result.get("cup_files")
        # Only fetch_user should produce a CUP file
        assert len(cup_files) == 1
        assert "FetchUserFilter" in cup_files[0]["content"]

    def test_import_function_with_complex_body(self):
        """Function with try/except, for loops, nested if."""
        source = '''def process_order(data: dict) -> dict:
    try:
        items = data.get("items", [])
        total = 0.0
        for item in items:
            if item.get("discount"):
                total += item["price"] * 0.9
            else:
                total += item["price"]
        data["total"] = total
    except Exception as e:
        data["error"] = str(e)
    return data
'''
        classified_files = {
            "model": [{"name": "process_order", "content": source}],
        }
        f = GenerateImportFilter()
        result = f.call(Payload({
            "classified_files": classified_files,
            "config": load_config(pattern="mvc"),
        }))
        cup_files = result.get("cup_files")
        assert len(cup_files) == 1
        # Must be valid Python
        compile(cup_files[0]["content"], "test.py", "exec")
        assert "ProcessOrderFilter" in cup_files[0]["content"]

    def test_import_function_returning_non_dict(self):
        """Function returning a boolean — treated as tap (no dict return)."""
        source = "def is_valid(data: dict) -> bool:\n    return len(data) > 0\n"
        classified_files = {
            "model": [{"name": "is_valid", "content": source}],
        }
        f = GenerateImportFilter()
        result = f.call(Payload({
            "classified_files": classified_files,
            "config": load_config(pattern="mvc"),
        }))
        steps = result.get("cup_steps")
        # Not returning dict → treated as non-returning → filter (returns_value is False)
        assert len(steps) == 1


# ══════════════════════════════════════════════
# ScanProject Edge Cases
# ══════════════════════════════════════════════

class TestScanProjectEdgeCases:
    def test_hidden_directories_skipped(self, tmp_path):
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "secret.py").write_text("x = 1\n")
        (tmp_path / "visible").mkdir()
        (tmp_path / "visible" / "public.py").write_text("y = 2\n")

        f = ScanProjectFilter()
        result = f.call(Payload({"project_path": str(tmp_path)}))
        names = [sf["name"] for sf in result.get("source_files")]
        assert "public" in names
        assert "secret" not in names

    def test_pycache_skipped(self, tmp_path):
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "module.cpython-39.pyc").write_text("")
        (tmp_path / "real.py").write_text("pass\n")

        f = ScanProjectFilter()
        result = f.call(Payload({"project_path": str(tmp_path)}))
        names = [sf["name"] for sf in result.get("source_files")]
        assert "real" in names
        assert len(names) == 1

    def test_root_level_files_have_empty_dir(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')\n")

        f = ScanProjectFilter()
        result = f.call(Payload({"project_path": str(tmp_path)}))
        source_files = result.get("source_files")
        assert len(source_files) == 1
        assert source_files[0]["dir"] == ""
        assert source_files[0]["name"] == "main"

    def test_empty_directory(self, tmp_path):
        f = ScanProjectFilter()
        result = f.call(Payload({"project_path": str(tmp_path)}))
        assert result.get("source_files") == []

    def test_deeply_nested_structure(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        (deep / "deep_file.py").write_text("x = 1\n")

        f = ScanProjectFilter()
        result = f.call(Payload({"project_path": str(tmp_path)}))
        source_files = result.get("source_files")
        assert len(source_files) == 1
        assert source_files[0]["name"] == "deep_file"
        assert "a/b/c/d" in source_files[0]["dir"]

    def test_file_with_unicode_content(self, tmp_path):
        (tmp_path / "unicode.py").write_text("# 日本語コメント\nx = '你好'\n", encoding="utf-8")

        f = ScanProjectFilter()
        result = f.call(Payload({"project_path": str(tmp_path)}))
        source_files = result.get("source_files")
        assert len(source_files) == 1
        assert "日本語" in source_files[0]["content"]

    def test_files_sorted_deterministically(self, tmp_path):
        for name in ["z_last", "a_first", "m_middle"]:
            (tmp_path / f"{name}.py").write_text(f"# {name}\n")

        f = ScanProjectFilter()
        result = f.call(Payload({"project_path": str(tmp_path)}))
        names = [sf["name"] for sf in result.get("source_files")]
        assert names == sorted(names)


# ══════════════════════════════════════════════
# ConversionLogTap Edge Cases
# ══════════════════════════════════════════════

class TestConversionLogEdgeCases:
    def test_empty_payload_no_entries(self):
        tap = ConversionLogTap()
        tap.observe(Payload({}))
        assert tap.entries == []

    def test_multiple_observations_accumulate(self):
        tap = ConversionLogTap()
        tap.observe(Payload({"config": {"pattern": "mvc"}}))
        tap.observe(Payload({"config": {"pattern": "mvc"}, "steps": [1, 2]}))
        tap.observe(Payload({"config": {"pattern": "mvc"}, "classified": {"model": []}}))
        assert len(tap.entries) == 3

    def test_config_without_pattern_key(self):
        tap = ConversionLogTap()
        tap.observe(Payload({"config": {}}))
        assert any("?" in e for e in tap.entries)

    def test_files_count_logged(self):
        tap = ConversionLogTap()
        tap.observe(Payload({"files": [{"path": "a.py"}, {"path": "b.py"}]}))
        assert any("2" in e for e in tap.entries)

    def test_cup_files_count_logged(self):
        tap = ConversionLogTap()
        tap.observe(Payload({"cup_files": [{"path": "x.py"}]}))
        assert any("1" in e for e in tap.entries)

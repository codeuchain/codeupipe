"""
Integration edge-case tests — full pipelines with tricky inputs.
"""

import pytest
from codeupipe import Payload, Pipeline, Valve, Hook

from codeupipe.converter.pipelines.export_pipeline import build_export_pipeline
from codeupipe.converter.pipelines.import_pipeline import build_import_pipeline
from codeupipe.converter.taps.conversion_log import ConversionLogTap


# ══════════════════════════════════════════════
# Export Pipeline — Edge Cases
# ══════════════════════════════════════════════

class TestExportEdgeCaseIntegration:

    @pytest.mark.asyncio(loop_scope="function")
    async def test_export_empty_pipeline(self):
        """Empty pipeline → should still produce an orchestrator, no step files."""
        p = Pipeline()
        export = build_export_pipeline()
        result = await export.run(Payload({"pipeline": p, "pattern": "mvc"}))

        files = result.get("files")
        assert len(files) == 1  # just orchestrator
        assert "pipeline.py" in files[0]["path"]
        compile(files[0]["content"], "pipeline.py", "exec")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_export_pipeline_only_taps(self):
        """Pipeline with only taps → all should land in middleware."""
        class LogTap:
            def observe(self, payload):
                pass

        class MetricsTap:
            def observe(self, payload):
                pass

        p = Pipeline()
        p.add_tap(LogTap(), name="log_request")
        p.add_tap(MetricsTap(), name="track_metrics")

        export = build_export_pipeline()
        result = await export.run(Payload({"pipeline": p, "pattern": "mvc"}))

        files = result.get("files")
        paths = [f["path"] for f in files]
        # Taps match _tap token → middleware
        assert any("middleware/" in path and "log_request" in path for path in paths)
        assert any("middleware/" in path and "track_metrics" in path for path in paths)

        for f in files:
            compile(f["content"], f["path"], "exec")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_export_pipeline_many_valves(self):
        """Pipeline with 5 valves — each must get its own predicate."""
        p = Pipeline()
        for i in range(5):
            inner = type(f"Inner{i}", (), {"call": lambda self, payload: payload})()
            p.add_filter(
                Valve(f"gate_{i}", inner, lambda p: True),
                name=f"gate_{i}",
            )

        export = build_export_pipeline()
        result = await export.run(Payload({"pipeline": p, "pattern": "mvc"}))

        files = result.get("files")
        valve_files = [f for f in files if "gate_" in f["path"]]
        assert len(valve_files) == 5

        for f in valve_files:
            name = f["path"].split("/")[-1].replace(".py", "")
            assert f"def {name}_predicate" in f["content"]
            compile(f["content"], f["path"], "exec")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_export_pipeline_with_hooks_only(self):
        """Pipeline with hooks but no steps — hooks still classified."""
        class AuditHook(Hook):
            pass

        class MetricsHook(Hook):
            pass

        p = Pipeline()
        p.use_hook(AuditHook())
        p.use_hook(MetricsHook())

        export = build_export_pipeline()
        result = await export.run(Payload({"pipeline": p, "pattern": "mvc"}))

        files = result.get("files")
        # Hooks + orchestrator
        hook_files = [f for f in files if "Hook" in f["path"]]
        assert len(hook_files) == 2

        for f in files:
            compile(f["content"], f["path"], "exec")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_export_with_dynamic_filters(self):
        """Dynamically created filter classes — no source available."""
        DynA = type("DynA", (), {"call": lambda self, p: p})
        DynB = type("DynB", (), {"call": lambda self, p: p})

        p = Pipeline()
        p.add_filter(DynA(), name="fetch_data")
        p.add_filter(DynB(), name="save_result")

        export = build_export_pipeline()
        result = await export.run(Payload({"pipeline": p, "pattern": "mvc"}))

        files = result.get("files")
        for f in files:
            compile(f["content"], f["path"], "exec")
            # No "Original CUP source" comments when source is None
            if "fetch_data.py" in f["path"]:
                assert "Original CUP source" not in f["content"]

    @pytest.mark.asyncio(loop_scope="function")
    async def test_export_all_uncategorized(self):
        """Steps that match no role patterns → all in 'uncategorized' dir."""
        class Alpha:
            def call(self, payload):
                return payload

        p = Pipeline()
        p.add_filter(Alpha(), name="xyz_alpha")

        # Use config with narrow roles that won't match
        export = build_export_pipeline()
        result = await export.run(Payload({
            "pipeline": p,
            "pattern": "hexagonal",
        }))

        files = result.get("files")
        paths = [f["path"] for f in files]
        # xyz_alpha doesn't match any hexagonal pattern → uncategorized
        assert any("uncategorized/" in p for p in paths)

        for f in files:
            compile(f["content"], f["path"], "exec")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_export_log_tap_captures_final_state(self):
        """Log tap runs after all filters — sees the final payload with all keys."""
        class FetchUser:
            def call(self, payload):
                return payload

        p = Pipeline()
        p.add_filter(FetchUser(), name="fetch_user")

        log_tap = ConversionLogTap()
        export = build_export_pipeline(log_tap=log_tap)
        await export.run(Payload({"pipeline": p, "pattern": "mvc"}))

        # Tap runs once after all filters, sees final payload
        # classified + files keys are both present → logs both
        assert len(log_tap.entries) >= 2
        assert any("roles" in e.lower() for e in log_tap.entries)
        assert any("export" in e.lower() or "Generated" in e for e in log_tap.entries)

    @pytest.mark.asyncio(loop_scope="function")
    async def test_export_hexagonal_nested_dir_structure(self):
        """Hexagonal pattern has nested dirs (adapters/inbound/). Verify correct paths."""
        class ParseRequest:
            def call(self, payload):
                return payload

        class SaveOrder:
            def call(self, payload):
                return payload

        p = Pipeline()
        p.add_filter(ParseRequest(), name="parse_request")
        p.add_filter(SaveOrder(), name="save_order")

        export = build_export_pipeline()
        result = await export.run(Payload({"pipeline": p, "pattern": "hexagonal"}))

        files = result.get("files")
        paths = [f["path"] for f in files]
        assert any("adapters/inbound/" in p for p in paths)
        assert any("adapters/outbound/" in p for p in paths)

        for f in files:
            compile(f["content"], f["path"], "exec")


# ══════════════════════════════════════════════
# Import Pipeline — Edge Cases
# ══════════════════════════════════════════════

class TestImportEdgeCaseIntegration:

    @pytest.mark.asyncio(loop_scope="function")
    async def test_import_empty_project(self, tmp_path):
        """Empty project dir → no files, no cup_files."""
        (tmp_path / "models").mkdir()  # empty dir

        imp = build_import_pipeline()
        result = await imp.run(Payload({
            "project_path": str(tmp_path),
            "pattern": "mvc",
        }))

        assert result.get("cup_files") == []
        assert "build_pipeline" in result.get("cup_pipeline", "")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_import_files_with_no_functions(self, tmp_path):
        """Project with only constants/classes — no extractable functions."""
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "constants.py").write_text(
            "MAX_RETRIES = 3\nTIMEOUT = 30\n"
        )

        imp = build_import_pipeline()
        result = await imp.run(Payload({
            "project_path": str(tmp_path),
            "pattern": "mvc",
        }))

        assert result.get("cup_files") == []

    @pytest.mark.asyncio(loop_scope="function")
    async def test_import_mixed_function_and_nonfunc_files(self, tmp_path):
        """Mix of functional and non-functional files."""
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "config.py").write_text("DB_URL = 'postgres://...'\n")
        (tmp_path / "models" / "fetch_user.py").write_text(
            'def fetch_user(data: dict) -> dict:\n    data["user"] = "alice"\n    return data\n'
        )

        imp = build_import_pipeline()
        result = await imp.run(Payload({
            "project_path": str(tmp_path),
            "pattern": "mvc",
        }))

        cup_files = result.get("cup_files")
        assert len(cup_files) == 1
        assert "FetchUserFilter" in cup_files[0]["content"]

    @pytest.mark.asyncio(loop_scope="function")
    async def test_import_deeply_nested_project(self, tmp_path):
        """Files in nested directories should still be found and classified."""
        deep = tmp_path / "adapters" / "inbound"
        deep.mkdir(parents=True)
        (deep / "parse_request.py").write_text(
            'def parse_request(data: dict) -> dict:\n    data["parsed"] = True\n    return data\n'
        )

        imp = build_import_pipeline()
        result = await imp.run(Payload({
            "project_path": str(tmp_path),
            "pattern": "hexagonal",
        }))

        cup_files = result.get("cup_files")
        assert len(cup_files) >= 1
        assert any("ParseRequestFilter" in f["content"] for f in cup_files)

    @pytest.mark.asyncio(loop_scope="function")
    async def test_import_files_at_root_uncategorized(self, tmp_path):
        """Files at project root → uncategorized role."""
        (tmp_path / "main.py").write_text(
            'def main(data: dict) -> dict:\n    data["started"] = True\n    return data\n'
        )

        imp = build_import_pipeline()
        result = await imp.run(Payload({
            "project_path": str(tmp_path),
            "pattern": "mvc",
        }))

        # Should still generate CUP code even for uncategorized
        cup_files = result.get("cup_files")
        assert len(cup_files) == 1

    @pytest.mark.asyncio(loop_scope="function")
    async def test_import_generates_valid_python_for_all(self, tmp_path):
        """Comprehensive import with multiple dirs — all generated code must compile."""
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "fetch_user.py").write_text(
            'def fetch_user(data: dict) -> dict:\n    data["user"] = "alice"\n    return data\n'
        )
        (tmp_path / "views").mkdir()
        (tmp_path / "views" / "format_response.py").write_text(
            'def format_response(data: dict) -> dict:\n    data["out"] = str(data)\n    return data\n'
        )
        (tmp_path / "controllers").mkdir()
        (tmp_path / "controllers" / "validate_input.py").write_text(
            'def validate_input(data: dict) -> dict:\n    if not data.get("name"):\n        raise ValueError("Missing")\n    return data\n'
        )
        (tmp_path / "middleware").mkdir()
        (tmp_path / "middleware" / "log_it.py").write_text(
            'def log_it(data: dict) -> None:\n    print(data)\n'
        )

        imp = build_import_pipeline()
        result = await imp.run(Payload({
            "project_path": str(tmp_path),
            "pattern": "mvc",
        }))

        for f in result.get("cup_files", []):
            try:
                compile(f["content"], f["path"], "exec")
            except SyntaxError as e:
                pytest.fail(f"Invalid Python in {f['path']}: {e}\n\nContent:\n{f['content']}")

        pipeline_code = result.get("cup_pipeline", "")
        try:
            compile(pipeline_code, "pipeline.py", "exec")
        except SyntaxError as e:
            pytest.fail(f"Invalid pipeline code: {e}\n\nContent:\n{pipeline_code}")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_import_complex_function_bodies(self, tmp_path):
        """Functions with try/except, for loops, nested if — body must survive."""
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "process.py").write_text('''def process_order(data: dict) -> dict:
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
''')

        imp = build_import_pipeline()
        result = await imp.run(Payload({
            "project_path": str(tmp_path),
            "pattern": "mvc",
        }))

        cup_files = result.get("cup_files")
        assert len(cup_files) >= 1

        for f in cup_files:
            compile(f["content"], f["path"], "exec")
            # Verify body survived
            assert "try:" in f["content"]
            assert "except" in f["content"]
            assert "for item" in f["content"]

    @pytest.mark.asyncio(loop_scope="function")
    async def test_import_state_tracked_through_all_filters(self, tmp_path):
        """State should record all 4 filters as executed."""
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "fetch.py").write_text(
            'def fetch(data: dict) -> dict:\n    return data\n'
        )

        imp = build_import_pipeline()
        await imp.run(Payload({
            "project_path": str(tmp_path),
            "pattern": "mvc",
        }))

        assert "parse_config" in imp.state.executed
        assert "scan_project" in imp.state.executed
        assert "classify_files" in imp.state.executed
        assert "generate_import" in imp.state.executed
        assert not imp.state.has_errors

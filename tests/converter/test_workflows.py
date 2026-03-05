"""
Real-world workflow E2E tests — realistic business pipelines
through full export → disk → import round-trips.

These simulate what a real developer's pipeline would look like
and verify the converter handles production-like code patterns.
"""

import pytest
from pathlib import Path
from codeupipe import Payload, Pipeline, Valve, Hook
from codeupipe.converter.pipelines.export_pipeline import build_export_pipeline
from codeupipe.converter.pipelines.import_pipeline import build_import_pipeline
from codeupipe.converter.taps.conversion_log import ConversionLogTap


def _write_files(base_path, files):
    """Write generated files to disk with __init__.py in each directory."""
    for f in files:
        filepath = base_path / f["path"]
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(f["content"], encoding="utf-8")
        init = filepath.parent / "__init__.py"
        if not init.exists():
            init.write_text("")


# ══════════════════════════════════════════════
# ETL Pipeline — Extract, Transform, Load
# ══════════════════════════════════════════════

class FetchRawData:
    """Simulates pulling data from an external API."""
    def call(self, payload):
        return payload.insert("raw_records", [{"id": i, "value": i * 10} for i in range(5)])


class ValidateRecords:
    """Rejects records with missing fields."""
    def call(self, payload):
        raw = payload.get("raw_records", [])
        valid = [r for r in raw if "id" in r and "value" in r]
        return payload.insert("valid_records", valid).insert("dropped_count", len(raw) - len(valid))


class TransformRecords:
    """Normalize values to 0-1 range."""
    def call(self, payload):
        records = payload.get("valid_records", [])
        max_val = max((r["value"] for r in records), default=1)
        transformed = [{"id": r["id"], "normalized": r["value"] / max_val} for r in records]
        return payload.insert("transformed", transformed)


class EnrichWithMetadata:
    """Add timestamps and source tags."""
    def call(self, payload):
        records = payload.get("transformed", [])
        enriched = [{**r, "source": "api_v2", "batch": "2024-01-15"} for r in records]
        return payload.insert("enriched", enriched)


class LoadToDatabase:
    """Simulates writing to a database."""
    def call(self, payload):
        records = payload.get("enriched", [])
        return payload.insert("loaded_count", len(records)).insert("load_status", "success")


class ETLAuditTap:
    """Logs ETL progress."""
    def observe(self, payload):
        pass


class ETLTimingHook(Hook):
    """Tracks ETL step timing."""
    pass


class TestETLPipeline:
    """Full ETL pipeline: fetch → validate → transform → enrich → load."""

    def _build_etl_pipeline(self):
        p = Pipeline()
        p.add_filter(FetchRawData(), name="fetch_raw_data")
        p.add_filter(ValidateRecords(), name="validate_records")
        p.add_filter(TransformRecords(), name="calc_normalized")  # named calc_* for MVC controller
        p.add_filter(EnrichWithMetadata(), name="process_enrichment")
        p.add_filter(LoadToDatabase(), name="save_to_database")
        p.add_tap(ETLAuditTap(), name="etl_audit_tap")
        p.use_hook(ETLTimingHook())
        return p

    @pytest.mark.asyncio(loop_scope="function")
    async def test_etl_export_mvc(self, tmp_path):
        """ETL pipeline exported to MVC structure."""
        pipeline = self._build_etl_pipeline()
        export = build_export_pipeline()
        result = await export.run(Payload({"pipeline": pipeline, "pattern": "mvc"}))

        files = result.get("files")
        _write_files(tmp_path, files)

        # Verify MVC classification:
        # fetch_raw_data → model (fetch_*)
        # validate_records → controller (validate_*)
        # calc_normalized → controller (calc_*)
        # process_enrichment → controller (process_*)
        # save_to_database → model (save_*)
        # etl_audit_tap → middleware (_tap)
        paths = [f["path"] for f in files]
        assert any("models/" in p and "fetch_raw_data" in p for p in paths)
        assert any("models/" in p and "save_to_database" in p for p in paths)
        assert any("controllers/" in p and "validate_records" in p for p in paths)
        assert any("controllers/" in p and "calc_normalized" in p for p in paths)
        assert any("middleware/" in p and "etl_audit_tap" in p for p in paths)

        # All valid Python
        for f in files:
            compile(f["content"], f["path"], "exec")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_etl_export_clean(self, tmp_path):
        """ETL pipeline exported to Clean Architecture."""
        pipeline = self._build_etl_pipeline()
        export = build_export_pipeline()
        result = await export.run(Payload({"pipeline": pipeline, "pattern": "clean"}))

        files = result.get("files")
        paths = [f["path"] for f in files]

        # Clean arch: calc_*, process_*, validate_* → use_case
        # fetch_*, save_* → interface_adapter
        assert any("use_cases/" in p for p in paths)
        assert any("interface_adapters/" in p for p in paths)

        for f in files:
            compile(f["content"], f["path"], "exec")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_etl_round_trip_mvc(self, tmp_path):
        """Full ETL round-trip: CUP → MVC → CUP."""
        pipeline = self._build_etl_pipeline()

        # Export
        export = build_export_pipeline()
        export_result = await export.run(Payload({"pipeline": pipeline, "pattern": "mvc"}))
        files = export_result.get("files")
        export_dir = tmp_path / "exported"
        _write_files(export_dir, files)

        # Import back
        src_dir = export_dir / "src"
        imp = build_import_pipeline()
        import_result = await imp.run(Payload({"project_path": str(src_dir), "pattern": "mvc"}))

        cup_files = import_result.get("cup_files", [])
        cup_steps = import_result.get("cup_steps", [])
        pipeline_code = import_result.get("cup_pipeline", "")

        assert len(cup_files) > 0
        assert "build_pipeline" in pipeline_code

        # All generated CUP code must be valid Python
        for f in cup_files:
            compile(f["content"], f["path"], "exec")
        compile(pipeline_code, "pipeline.py", "exec")

        # Original ETL step names should survive
        step_names = {s["name"] for s in cup_steps}
        assert "fetch_raw_data" in step_names
        assert "save_to_database" in step_names


# ══════════════════════════════════════════════
# Auth Pipeline — Authentication & Authorization
# ══════════════════════════════════════════════

class ParseAuthToken:
    """Extract and decode the auth token from headers."""
    def call(self, payload):
        token = payload.get("auth_header", "").replace("Bearer ", "")
        return payload.insert("token", token)


class ValidateToken:
    """Verify the token is valid and not expired."""
    def call(self, payload):
        token = payload.get("token", "")
        is_valid = len(token) > 10  # simplified check
        return payload.insert("token_valid", is_valid)


class FetchUserFromToken:
    """Look up the user associated with the token."""
    def call(self, payload):
        return payload.insert("auth_user", {"id": 42, "role": "admin", "name": "Alice"})


class AuthorizeRole:
    """Check if user has required role."""
    def call(self, payload):
        user = payload.get("auth_user", {})
        required = payload.get("required_role", "user")
        if user.get("role") != required:
            raise PermissionError(f"User role '{user.get('role')}' != required '{required}'")
        return payload.insert("authorized", True)


class RateLimitCheck:
    """Enforce rate limiting."""
    def call(self, payload):
        return payload.insert("rate_limited", False)


class AuthAuditTap:
    """Log auth attempts for security audit."""
    def observe(self, payload):
        pass


class TestAuthPipeline:
    """Full auth pipeline: parse → validate → fetch user → authorize → audit."""

    def _build_auth_pipeline(self):
        p = Pipeline()
        p.add_filter(ParseAuthToken(), name="parse_auth_token")
        p.add_filter(ValidateToken(), name="validate_token")
        p.add_filter(FetchUserFromToken(), name="fetch_user_from_token")
        p.add_filter(
            Valve("authorize_role", AuthorizeRole(), lambda p: p.get("token_valid", False)),
            name="authorize_role",
        )
        p.add_filter(
            Valve("rate_limit", RateLimitCheck(), lambda p: p.get("authorized", False)),
            name="rate_limit",
        )
        p.add_tap(AuthAuditTap(), name="auth_audit_tap")
        return p

    @pytest.mark.asyncio(loop_scope="function")
    async def test_auth_export_mvc(self, tmp_path):
        """Auth pipeline → MVC. Valves go to middleware."""
        pipeline = self._build_auth_pipeline()
        export = build_export_pipeline()
        result = await export.run(Payload({"pipeline": pipeline, "pattern": "mvc"}))

        files = result.get("files")
        paths = [f["path"] for f in files]

        # parse_auth_token doesn't match any MVC glob → uncategorized
        # validate_token → controller (validate_*)
        # fetch_user_from_token → model (fetch_*)
        # authorize_role → controller (authorize_*) — name glob wins over _valve type token
        # rate_limit → middleware (_valve) — no name glob match, falls to type token
        # auth_audit_tap → middleware (_tap)
        assert any("controllers/" in p and "validate_token" in p for p in paths)
        assert any("models/" in p and "fetch_user_from_token" in p for p in paths)
        assert any("controllers/" in p and "authorize_role" in p for p in paths)
        assert any("middleware/" in p and "rate_limit" in p for p in paths)
        assert any("middleware/" in p and "auth_audit_tap" in p for p in paths)

        for f in files:
            compile(f["content"], f["path"], "exec")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_auth_valves_have_predicates(self, tmp_path):
        """Each valve in the auth pipeline gets its own predicate function."""
        pipeline = self._build_auth_pipeline()
        export = build_export_pipeline()
        result = await export.run(Payload({"pipeline": pipeline, "pattern": "mvc"}))

        files = result.get("files")
        auth_valve = next(f for f in files if "authorize_role.py" in f["path"])
        rate_valve = next(f for f in files if "rate_limit.py" in f["path"])

        assert "def authorize_role_predicate" in auth_valve["content"]
        assert "def rate_limit_predicate" in rate_valve["content"]

    @pytest.mark.asyncio(loop_scope="function")
    async def test_auth_orchestrator_valve_ordering(self):
        """Valves must appear as if-statements in the correct pipeline order."""
        pipeline = self._build_auth_pipeline()
        export = build_export_pipeline()
        result = await export.run(Payload({"pipeline": pipeline, "pattern": "mvc"}))

        files = result.get("files")
        orch = next(f for f in files if "pipeline.py" in f["path"])
        content = orch["content"]

        # authorize_role should appear before rate_limit
        assert content.index("authorize_role") < content.index("rate_limit")
        # Both should be in if statements
        assert "if authorize_role_predicate" in content
        assert "if rate_limit_predicate" in content

    @pytest.mark.asyncio(loop_scope="function")
    async def test_auth_round_trip(self, tmp_path):
        """Full auth round-trip: CUP → MVC → CUP."""
        pipeline = self._build_auth_pipeline()

        export = build_export_pipeline()
        export_result = await export.run(Payload({"pipeline": pipeline, "pattern": "mvc"}))
        files = export_result.get("files")
        export_dir = tmp_path / "exported"
        _write_files(export_dir, files)

        src_dir = export_dir / "src"
        imp = build_import_pipeline()
        import_result = await imp.run(Payload({"project_path": str(src_dir), "pattern": "mvc"}))

        cup_files = import_result.get("cup_files", [])
        assert len(cup_files) > 0

        for f in cup_files:
            compile(f["content"], f["path"], "exec")

        step_names = {s["name"] for s in import_result.get("cup_steps", [])}
        assert "validate_token" in step_names
        assert "fetch_user_from_token" in step_names


# ══════════════════════════════════════════════
# Data Validation Pipeline — Complex Function Bodies
# ══════════════════════════════════════════════

class TestDataValidationPipeline:
    """Pipeline with realistic complex function bodies that must survive round-trip."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_complex_bodies_survive_export_import(self, tmp_path):
        """Write complex standard Python, import to CUP, verify bodies compile."""
        # Create a project with complex real-world functions
        (tmp_path / "controllers").mkdir()
        (tmp_path / "controllers" / "validate_payload.py").write_text('''def validate_payload(data: dict) -> dict:
    errors = []
    required = ["name", "email", "age"]
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    if "email" in data:
        if "@" not in data["email"]:
            errors.append("Invalid email format")
    if "age" in data:
        try:
            age = int(data["age"])
            if age < 0 or age > 150:
                errors.append("Age out of range")
        except (ValueError, TypeError):
            errors.append("Age must be a number")
    data["validation_errors"] = errors
    data["is_valid"] = len(errors) == 0
    return data
''')

        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "fetch_user_profile.py").write_text('''def fetch_user_profile(data: dict) -> dict:
    user_id = data.get("user_id")
    if user_id is None:
        raise ValueError("user_id is required")
    profiles = {
        1: {"name": "Alice", "tier": "premium"},
        2: {"name": "Bob", "tier": "basic"},
        3: {"name": "Charlie", "tier": "enterprise"},
    }
    profile = profiles.get(user_id)
    if profile is None:
        data["error"] = f"User {user_id} not found"
    else:
        data["profile"] = profile
    return data
''')

        (tmp_path / "models" / "save_audit_log.py").write_text('''def save_audit_log(data: dict) -> dict:
    log_entry = {
        "action": data.get("action", "unknown"),
        "user": data.get("profile", {}).get("name", "anonymous"),
        "success": data.get("is_valid", False),
        "errors": data.get("validation_errors", []),
    }
    data["audit_log"] = log_entry
    return data
''')

        (tmp_path / "middleware").mkdir()
        (tmp_path / "middleware" / "log_request.py").write_text('''def log_request(data: dict) -> None:
    action = data.get("action", "?")
    user = data.get("profile", {}).get("name", "anon")
    print(f"[AUDIT] {user} performed {action}")
''')

        # Import this realistic project
        imp = build_import_pipeline()
        result = await imp.run(Payload({"project_path": str(tmp_path), "pattern": "mvc"}))

        cup_files = result.get("cup_files", [])
        assert len(cup_files) >= 4

        # Every generated file MUST be valid Python
        for f in cup_files:
            try:
                compile(f["content"], f["path"], "exec")
            except SyntaxError as e:
                pytest.fail(f"INVALID Python in {f['path']}:\n{e}\n\nContent:\n{f['content']}")

        pipeline_code = result.get("cup_pipeline", "")
        compile(pipeline_code, "pipeline.py", "exec")

        # Verify structural integrity
        all_content = "\n".join(f["content"] for f in cup_files)
        assert "ValidatePayloadFilter" in all_content
        assert "FetchUserProfileFilter" in all_content
        assert "SaveAuditLogFilter" in all_content
        assert "LogRequestTap" in all_content

    @pytest.mark.asyncio(loop_scope="function")
    async def test_nested_control_flow_preserved(self, tmp_path):
        """For loops with nested if/else must maintain correct indentation in CUP."""
        (tmp_path / "controllers").mkdir()
        (tmp_path / "controllers" / "process_batch.py").write_text('''def process_batch(data: dict) -> dict:
    records = data.get("records", [])
    results = []
    for i, record in enumerate(records):
        if record.get("type") == "skip":
            continue
        elif record.get("type") == "stop":
            break
        else:
            results.append({
                "index": i,
                "processed": True,
                "value": record.get("value", 0) * 2,
            })
    data["results"] = results
    data["processed_count"] = len(results)
    return data
''')

        imp = build_import_pipeline()
        result = await imp.run(Payload({"project_path": str(tmp_path), "pattern": "mvc"}))

        cup_files = result.get("cup_files", [])
        assert len(cup_files) == 1

        content = cup_files[0]["content"]
        compile(content, "test.py", "exec")

        # Verify control flow keywords survived
        assert "for i, record" in content
        assert "continue" in content
        assert "break" in content
        assert "elif" in content


# ══════════════════════════════════════════════
# Custom Config — Non-Standard Roles
# ══════════════════════════════════════════════

class TestCustomConfigWorkflow:
    """Using custom config files with non-default roles."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_custom_config_export(self, tmp_path):
        """Export with custom role definitions from a .cup.json file."""
        import json

        # Write custom config
        config_file = tmp_path / ".cup.json"
        config_data = {
            "pattern": "mvc",
            "roles": {
                "data_layer": ["fetch_*", "load_*", "query_*"],
                "logic_layer": ["calc_*", "process_*", "transform_*"],
                "presentation": ["format_*", "render_*", "display_*"],
                "infra": ["_tap", "_hook", "_valve", "log_*"],
            },
            "output": {
                "base": "app/",
                "data_layer": "data/",
                "logic_layer": "logic/",
                "presentation": "ui/",
                "infra": "infra/",
            },
        }
        config_file.write_text(json.dumps(config_data))

        # Build pipeline
        class FetchOrders:
            def call(self, payload):
                return payload

        class CalcDiscount:
            def call(self, payload):
                return payload

        class FormatInvoice:
            def call(self, payload):
                return payload

        class LogAudit:
            def observe(self, payload):
                pass

        p = Pipeline()
        p.add_filter(FetchOrders(), name="fetch_orders")
        p.add_filter(CalcDiscount(), name="calc_discount")
        p.add_filter(FormatInvoice(), name="format_invoice")
        p.add_tap(LogAudit(), name="log_audit")

        export = build_export_pipeline()
        result = await export.run(Payload({
            "pipeline": p,
            "config_path": str(config_file),
        }))

        files = result.get("files")
        paths = [f["path"] for f in files]

        # Verify custom output dirs with custom base
        assert any("app/data/" in p and "fetch_orders" in p for p in paths)
        assert any("app/logic/" in p and "calc_discount" in p for p in paths)
        assert any("app/ui/" in p and "format_invoice" in p for p in paths)
        assert any("app/infra/" in p and "log_audit" in p for p in paths)

        for f in files:
            compile(f["content"], f["path"], "exec")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_custom_config_round_trip(self, tmp_path):
        """Custom config export → write to disk → import back."""
        import json

        config_data = {
            "pattern": "mvc",
            "roles": {
                "queries": ["fetch_*", "find_*"],
                "commands": ["save_*", "delete_*", "update_*"],
                "handlers": ["validate_*", "process_*"],
            },
            "output": {
                "base": "src/",
                "queries": "queries/",
                "commands": "commands/",
                "handlers": "handlers/",
            },
        }
        config_file = tmp_path / ".cup.json"
        config_file.write_text(json.dumps(config_data))

        # Build pipeline
        class FetchOrders:
            def call(self, payload):
                return payload

        class SaveOrder:
            def call(self, payload):
                return payload

        class ValidateInput:
            def call(self, payload):
                return payload

        p = Pipeline()
        p.add_filter(FetchOrders(), name="fetch_orders")
        p.add_filter(ValidateInput(), name="validate_input")
        p.add_filter(SaveOrder(), name="save_order")

        # Export
        export = build_export_pipeline()
        export_result = await export.run(Payload({
            "pipeline": p,
            "config_path": str(config_file),
        }))
        files = export_result.get("files")
        export_dir = tmp_path / "exported"
        _write_files(export_dir, files)

        # Import (use the custom config for import too, pointing at exported src/)
        src_dir = export_dir / "src"

        # Write a config for the import direction
        import_config = tmp_path / "import.cup.json"
        import_config.write_text(json.dumps(config_data))

        imp = build_import_pipeline()
        import_result = await imp.run(Payload({
            "project_path": str(src_dir),
            "config_path": str(import_config),
        }))

        cup_files = import_result.get("cup_files", [])
        assert len(cup_files) > 0

        step_names = {s["name"] for s in import_result.get("cup_steps", [])}
        assert "fetch_orders" in step_names
        assert "save_order" in step_names
        assert "validate_input" in step_names

        for f in cup_files:
            compile(f["content"], f["path"], "exec")


# ══════════════════════════════════════════════
# Large Pipeline — Scalability
# ══════════════════════════════════════════════

class TestLargePipeline:
    """Pipeline with many steps — tests converter scalability."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_20_step_pipeline_export_import(self, tmp_path):
        """20-step pipeline round-trip still works."""
        p = Pipeline()
        for i in range(10):
            cls = type(f"Fetch{i}", (), {"call": lambda self, payload: payload})
            p.add_filter(cls(), name=f"fetch_item_{i}")
        for i in range(5):
            cls = type(f"Validate{i}", (), {"call": lambda self, payload: payload})
            p.add_filter(cls(), name=f"validate_field_{i}")
        for i in range(5):
            cls = type(f"Save{i}", (), {"call": lambda self, payload: payload})
            p.add_filter(cls(), name=f"save_result_{i}")

        export = build_export_pipeline()
        result = await export.run(Payload({"pipeline": p, "pattern": "mvc"}))

        files = result.get("files")
        # 20 step files + 1 orchestrator
        assert len(files) == 21

        # Write and import back
        export_dir = tmp_path / "exported"
        _write_files(export_dir, files)

        src_dir = export_dir / "src"
        imp = build_import_pipeline()
        import_result = await imp.run(Payload({"project_path": str(src_dir), "pattern": "mvc"}))

        cup_steps = import_result.get("cup_steps", [])
        # Should recover most steps (some may be in orchestrator)
        assert len(cup_steps) >= 15

        for f in import_result.get("cup_files", []):
            compile(f["content"], f["path"], "exec")


# ══════════════════════════════════════════════
# All Patterns × Same Pipeline — Cross-Pattern Consistency
# ══════════════════════════════════════════════

class TestAllPatternsConsistency:
    """The same pipeline exported through every pattern should always produce valid code."""

    def _build_standard_pipeline(self):
        class FetchData:
            def call(self, payload):
                return payload

        class ValidateData:
            def call(self, payload):
                return payload

        class ProcessData:
            def call(self, payload):
                return payload

        class FormatOutput:
            def call(self, payload):
                return payload

        class SaveResult:
            def call(self, payload):
                return payload

        class AuditTap:
            def observe(self, payload):
                pass

        p = Pipeline()
        p.add_filter(FetchData(), name="fetch_data")
        p.add_filter(ValidateData(), name="validate_data")
        p.add_filter(ProcessData(), name="process_data")
        p.add_filter(FormatOutput(), name="format_output")
        p.add_filter(SaveResult(), name="save_result")
        p.add_tap(AuditTap(), name="audit_tap")
        return p

    @pytest.mark.asyncio(loop_scope="function")
    async def test_mvc_valid_python(self, tmp_path):
        export = build_export_pipeline()
        result = await export.run(Payload({"pipeline": self._build_standard_pipeline(), "pattern": "mvc"}))
        for f in result.get("files"):
            compile(f["content"], f["path"], "exec")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_clean_valid_python(self, tmp_path):
        export = build_export_pipeline()
        result = await export.run(Payload({"pipeline": self._build_standard_pipeline(), "pattern": "clean"}))
        for f in result.get("files"):
            compile(f["content"], f["path"], "exec")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_hexagonal_valid_python(self, tmp_path):
        export = build_export_pipeline()
        result = await export.run(Payload({"pipeline": self._build_standard_pipeline(), "pattern": "hexagonal"}))
        for f in result.get("files"):
            compile(f["content"], f["path"], "exec")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_flat_valid_python(self, tmp_path):
        export = build_export_pipeline()
        result = await export.run(Payload({"pipeline": self._build_standard_pipeline(), "pattern": "flat"}))
        for f in result.get("files"):
            compile(f["content"], f["path"], "exec")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_all_patterns_same_step_count(self):
        """Every pattern should export the same number of step files."""
        pipeline = self._build_standard_pipeline()
        step_counts = {}

        for pattern in ["mvc", "clean", "hexagonal", "flat"]:
            export = build_export_pipeline()
            result = await export.run(Payload({"pipeline": pipeline, "pattern": pattern}))
            files = result.get("files")
            # Subtract 1 for orchestrator
            step_counts[pattern] = len(files) - 1

        # All patterns should produce the same number of step files
        counts = list(step_counts.values())
        assert all(c == counts[0] for c in counts), f"Inconsistent counts: {step_counts}"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_all_patterns_round_trip(self, tmp_path):
        """Every pattern should survive a full round-trip."""
        for pattern in ["mvc", "clean", "hexagonal", "flat"]:
            pipeline = self._build_standard_pipeline()

            export = build_export_pipeline()
            export_result = await export.run(Payload({"pipeline": pipeline, "pattern": pattern}))

            files = export_result.get("files")
            export_dir = tmp_path / f"export_{pattern}"
            _write_files(export_dir, files)

            src_dir = export_dir / "src"
            imp = build_import_pipeline()
            import_result = await imp.run(Payload({"project_path": str(src_dir), "pattern": pattern}))

            cup_files = import_result.get("cup_files", [])
            assert len(cup_files) > 0, f"{pattern}: no CUP files generated"

            for f in cup_files:
                try:
                    compile(f["content"], f["path"], "exec")
                except SyntaxError as e:
                    pytest.fail(f"{pattern} round-trip produced invalid Python: {e}")

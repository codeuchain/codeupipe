"""Tests for from_config support of Ring 3 features.

Verifies that parallel groups, nested pipelines, retry, and circuit breaker
can all be expressed in JSON/TOML config and assembled via Pipeline.from_config().
"""

import asyncio
import json

import pytest

from codeupipe import Payload, Pipeline
from codeupipe.core.pipeline import CircuitOpenError
from codeupipe.registry import Registry


# ── Helpers ──────────────────────────────────────────────────

class AddTenFilter:
    def call(self, payload: Payload) -> Payload:
        return payload.insert("value", payload.get("value", 0) + 10)


class MultiplyFilter:
    def call(self, payload: Payload) -> Payload:
        return payload.insert("value", payload.get("value", 0) * 2)


class SetKeyFilter:
    """Sets a specific key — useful for parallel fan-out verification."""
    def __init__(self, key: str = "tag", value: str = "done"):
        self.key = key
        self.value = value

    async def call(self, payload: Payload) -> Payload:
        await asyncio.sleep(0.01)  # simulate IO
        return payload.insert(self.key, self.value)


class FailOnceFilter:
    """Fails N times then succeeds."""
    def __init__(self):
        self.fail_count = 1
        self.attempts = 0

    def call(self, payload: Payload) -> Payload:
        self.attempts += 1
        if self.attempts <= self.fail_count:
            raise RuntimeError(f"Transient failure #{self.attempts}")
        return payload.insert("recovered", True)


class AlwaysFailFilter:
    def call(self, payload: Payload) -> Payload:
        raise RuntimeError("permanent failure")


# ═══════════════════════════════════════════════════════════════
# Parallel steps in config
# ═══════════════════════════════════════════════════════════════

class TestConfigParallel:
    """from_config supports type='parallel' with a filters array."""

    @pytest.mark.asyncio
    async def test_parallel_step_from_json(self, tmp_path):
        """A parallel step fans out filters and merges results."""
        reg = Registry()
        reg.register("FetchA", lambda: SetKeyFilter(key="a", value="1"))
        reg.register("FetchB", lambda: SetKeyFilter(key="b", value="2"))

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "fan-out",
                "steps": [
                    {
                        "name": "parallel-fetch",
                        "type": "parallel",
                        "filters": [
                            {"name": "FetchA"},
                            {"name": "FetchB"},
                        ],
                    },
                ],
            }
        }))

        pipe = Pipeline.from_config(str(config_file), registry=reg)
        result = await pipe.run(Payload({"existing": "kept"}))

        assert result.get("a") == "1"
        assert result.get("b") == "2"
        assert result.get("existing") == "kept"

    @pytest.mark.asyncio
    async def test_parallel_mixed_with_sequential_from_json(self, tmp_path):
        """Parallel step between sequential filters."""
        reg = Registry()
        reg.register(AddTenFilter)
        reg.register(MultiplyFilter)
        reg.register("TagA", lambda: SetKeyFilter(key="tag_a", value="done"))
        reg.register("TagB", lambda: SetKeyFilter(key="tag_b", value="done"))

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "mixed",
                "steps": [
                    {"name": "AddTenFilter", "type": "filter"},
                    {
                        "name": "fan-out",
                        "type": "parallel",
                        "filters": [
                            {"name": "TagA"},
                            {"name": "TagB"},
                        ],
                    },
                    {"name": "MultiplyFilter", "type": "filter"},
                ],
            }
        }))

        pipe = Pipeline.from_config(str(config_file), registry=reg)
        result = await pipe.run(Payload({"value": 5}))

        assert result.get("value") == 30  # (5+10)*2
        assert result.get("tag_a") == "done"
        assert result.get("tag_b") == "done"

    @pytest.mark.asyncio
    async def test_parallel_state_tracked_from_config(self, tmp_path):
        """Parallel group name appears in state.executed."""
        reg = Registry()
        reg.register("TagX", lambda: SetKeyFilter(key="x", value="ok"))

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "tracked",
                "steps": [
                    {
                        "name": "pg",
                        "type": "parallel",
                        "filters": [{"name": "TagX"}],
                    },
                ],
            }
        }))

        pipe = Pipeline.from_config(str(config_file), registry=reg)
        await pipe.run(Payload({}))
        assert "pg" in pipe.state.executed

    @pytest.mark.asyncio
    async def test_parallel_with_filter_config_kwargs(self, tmp_path):
        """Parallel filters can pass config kwargs through the registry."""
        reg = Registry()
        reg.register("SetKey", lambda key="k", value="v": SetKeyFilter(key=key, value=value))

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "configured-parallel",
                "steps": [
                    {
                        "name": "p-group",
                        "type": "parallel",
                        "filters": [
                            {"name": "SetKey", "config": {"key": "alpha", "value": "100"}},
                            {"name": "SetKey", "config": {"key": "beta", "value": "200"}},
                        ],
                    },
                ],
            }
        }))

        pipe = Pipeline.from_config(str(config_file), registry=reg)
        result = await pipe.run(Payload({}))
        assert result.get("alpha") == "100"
        assert result.get("beta") == "200"


# ═══════════════════════════════════════════════════════════════
# Nested pipeline steps in config
# ═══════════════════════════════════════════════════════════════

class TestConfigNestedPipeline:
    """from_config supports type='pipeline' with nested steps."""

    @pytest.mark.asyncio
    async def test_nested_pipeline_from_json(self, tmp_path):
        """A pipeline step builds an inner pipeline from inline steps."""
        reg = Registry()
        reg.register(AddTenFilter)
        reg.register(MultiplyFilter)

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "outer",
                "steps": [
                    {
                        "name": "math-sub",
                        "type": "pipeline",
                        "steps": [
                            {"name": "AddTenFilter", "type": "filter"},
                            {"name": "MultiplyFilter", "type": "filter"},
                        ],
                    },
                ],
            }
        }))

        pipe = Pipeline.from_config(str(config_file), registry=reg)
        result = await pipe.run(Payload({"value": 5}))
        assert result.get("value") == 30  # (5+10)*2

    @pytest.mark.asyncio
    async def test_nested_pipeline_with_surrounding_steps(self, tmp_path):
        """Steps before and after the nested pipeline execute."""
        reg = Registry()
        reg.register(AddTenFilter)
        reg.register(MultiplyFilter)

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "sandwich",
                "steps": [
                    {"name": "AddTenFilter", "type": "filter"},
                    {
                        "name": "sub",
                        "type": "pipeline",
                        "steps": [
                            {"name": "MultiplyFilter", "type": "filter"},
                        ],
                    },
                    {"name": "AddTenFilter", "type": "filter"},
                ],
            }
        }))

        pipe = Pipeline.from_config(str(config_file), registry=reg)
        result = await pipe.run(Payload({"value": 5}))
        # 5 +10 = 15, *2 = 30, +10 = 40
        assert result.get("value") == 40

    @pytest.mark.asyncio
    async def test_deeply_nested_config(self, tmp_path):
        """Pipeline inside pipeline inside pipeline — 3 levels."""
        reg = Registry()
        reg.register(AddTenFilter)
        reg.register(MultiplyFilter)

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "deep",
                "steps": [
                    {
                        "name": "level-1",
                        "type": "pipeline",
                        "steps": [
                            {
                                "name": "level-2",
                                "type": "pipeline",
                                "steps": [
                                    {"name": "AddTenFilter", "type": "filter"},
                                ],
                            },
                            {"name": "MultiplyFilter", "type": "filter"},
                        ],
                    },
                ],
            }
        }))

        pipe = Pipeline.from_config(str(config_file), registry=reg)
        result = await pipe.run(Payload({"value": 5}))
        assert result.get("value") == 30  # (5+10)*2

    @pytest.mark.asyncio
    async def test_nested_pipeline_state_tracked(self, tmp_path):
        """Nested pipeline step appears in outer state."""
        reg = Registry()
        reg.register(AddTenFilter)

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "tracked",
                "steps": [
                    {
                        "name": "inner-pipe",
                        "type": "pipeline",
                        "steps": [
                            {"name": "AddTenFilter", "type": "filter"},
                        ],
                    },
                ],
            }
        }))

        pipe = Pipeline.from_config(str(config_file), registry=reg)
        await pipe.run(Payload({"value": 0}))
        assert "inner-pipe" in pipe.state.executed

    @pytest.mark.asyncio
    async def test_parallel_inside_nested_pipeline(self, tmp_path):
        """Parallel group nested inside a pipeline step."""
        reg = Registry()
        reg.register(AddTenFilter)
        reg.register("TagA", lambda: SetKeyFilter(key="a", value="1"))
        reg.register("TagB", lambda: SetKeyFilter(key="b", value="2"))

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "complex",
                "steps": [
                    {"name": "AddTenFilter", "type": "filter"},
                    {
                        "name": "inner",
                        "type": "pipeline",
                        "steps": [
                            {
                                "name": "fan-out",
                                "type": "parallel",
                                "filters": [
                                    {"name": "TagA"},
                                    {"name": "TagB"},
                                ],
                            },
                        ],
                    },
                ],
            }
        }))

        pipe = Pipeline.from_config(str(config_file), registry=reg)
        result = await pipe.run(Payload({"value": 5}))
        assert result.get("value") == 15  # 5+10
        assert result.get("a") == "1"
        assert result.get("b") == "2"


# ═══════════════════════════════════════════════════════════════
# Pipeline-level retry from config
# ═══════════════════════════════════════════════════════════════

class TestConfigRetry:
    """from_config supports pipeline.retry config for pipeline-level retry."""

    @pytest.mark.asyncio
    async def test_retry_from_json(self, tmp_path):
        """Pipeline assembled from config with retry wrapping."""
        fail_filter = FailOnceFilter()
        reg = Registry()
        reg.register("Flaky", lambda: fail_filter)

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "resilient",
                "retry": {"max_retries": 3},
                "steps": [
                    {"name": "Flaky", "type": "filter"},
                ],
            }
        }))

        result_pipe = Pipeline.from_config(str(config_file), registry=reg)
        result = await result_pipe.run(Payload({}))
        assert result.get("recovered") is True

    @pytest.mark.asyncio
    async def test_retry_exhausted_from_config(self, tmp_path):
        """Retry exhaustion still raises the error."""
        reg = Registry()
        reg.register(AlwaysFailFilter)

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "doomed",
                "retry": {"max_retries": 2},
                "steps": [
                    {"name": "AlwaysFailFilter", "type": "filter"},
                ],
            }
        }))

        result_pipe = Pipeline.from_config(str(config_file), registry=reg)
        with pytest.raises(RuntimeError, match="permanent failure"):
            await result_pipe.run(Payload({}))

    def test_retry_run_sync_from_config(self, tmp_path):
        """Retry wrapper from config works through run_sync."""
        fail_filter = FailOnceFilter()
        reg = Registry()
        reg.register("Flaky", lambda: fail_filter)

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "sync-retry",
                "retry": {"max_retries": 3},
                "steps": [
                    {"name": "Flaky", "type": "filter"},
                ],
            }
        }))

        result_pipe = Pipeline.from_config(str(config_file), registry=reg)
        result = result_pipe.run_sync(Payload({}))
        assert result.get("recovered") is True


# ═══════════════════════════════════════════════════════════════
# Pipeline-level circuit breaker from config
# ═══════════════════════════════════════════════════════════════

class TestConfigCircuitBreaker:
    """from_config supports pipeline.circuit_breaker config."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_from_json(self, tmp_path):
        """Pipeline with circuit breaker opens after threshold."""
        reg = Registry()
        reg.register(AlwaysFailFilter)

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "protected",
                "circuit_breaker": {"failure_threshold": 2},
                "steps": [
                    {"name": "AlwaysFailFilter", "type": "filter"},
                ],
            }
        }))

        breaker = Pipeline.from_config(str(config_file), registry=reg)

        # Trip the circuit
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await breaker.run(Payload({}))

        # Circuit is open
        with pytest.raises(CircuitOpenError):
            await breaker.run(Payload({}))

    def test_circuit_breaker_run_sync_from_config(self, tmp_path):
        """Circuit breaker from config works through run_sync."""
        reg = Registry()
        reg.register(AlwaysFailFilter)

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "sync-cb",
                "circuit_breaker": {"failure_threshold": 2},
                "steps": [
                    {"name": "AlwaysFailFilter", "type": "filter"},
                ],
            }
        }))

        breaker = Pipeline.from_config(str(config_file), registry=reg)

        for _ in range(2):
            with pytest.raises(RuntimeError):
                breaker.run_sync(Payload({}))

        with pytest.raises(CircuitOpenError):
            breaker.run_sync(Payload({}))

    @pytest.mark.asyncio
    async def test_retry_and_circuit_breaker_combined(self, tmp_path):
        """Both retry and circuit_breaker can be set together."""
        fail_filter = FailOnceFilter()
        reg = Registry()
        reg.register("Flaky", lambda: fail_filter)

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "double-wrapped",
                "retry": {"max_retries": 3},
                "circuit_breaker": {"failure_threshold": 10},
                "steps": [
                    {"name": "Flaky", "type": "filter"},
                ],
            }
        }))

        result_pipe = Pipeline.from_config(str(config_file), registry=reg)
        result = await result_pipe.run(Payload({}))
        assert result.get("recovered") is True


# ═══════════════════════════════════════════════════════════════
# Error handling for new config types
# ═══════════════════════════════════════════════════════════════

class TestConfigRing3Errors:
    """Error messaging for new step types in config."""

    def test_parallel_missing_filters_key(self, tmp_path):
        """Parallel step without 'filters' key raises clear error."""
        reg = Registry()

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "bad",
                "steps": [
                    {"name": "broken", "type": "parallel"},  # no filters key
                ],
            }
        }))

        with pytest.raises(ValueError, match="filters"):
            Pipeline.from_config(str(config_file), registry=reg)

    def test_pipeline_step_missing_steps_key(self, tmp_path):
        """Pipeline step without 'steps' key raises clear error."""
        reg = Registry()

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "bad",
                "steps": [
                    {"name": "broken", "type": "pipeline"},  # no steps key
                ],
            }
        }))

        with pytest.raises(ValueError, match="steps"):
            Pipeline.from_config(str(config_file), registry=reg)

    def test_parallel_unknown_filter_raises(self, tmp_path):
        """Unknown filter inside parallel group raises registry error."""
        reg = Registry()

        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps({
            "pipeline": {
                "name": "bad",
                "steps": [
                    {
                        "name": "pg",
                        "type": "parallel",
                        "filters": [{"name": "DoesNotExist"}],
                    },
                ],
            }
        }))

        with pytest.raises(KeyError, match="DoesNotExist"):
            Pipeline.from_config(str(config_file), registry=reg)

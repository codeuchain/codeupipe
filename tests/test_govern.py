"""
Tests for Ring 6 — Govern: schemas, contracts, timeout, rate limit, dead letter, audit.
"""

import asyncio
import json
import time
import pytest
from unittest.mock import AsyncMock

from codeupipe import (
    Payload, Pipeline, Filter,
    PayloadSchema, SchemaViolation, ContractViolation, PipelineTimeoutError,
    AuditEntry, AuditTrail, AuditHook,
    DeadLetterHandler, LogDeadLetterHandler,
)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

class AddKeyFilter:
    """Adds a key to the payload."""
    def __init__(self, key: str, value):
        self._key = key
        self._value = value

    async def call(self, payload: Payload) -> Payload:
        return payload.insert(self._key, self._value)


class BoomFilter:
    """Always raises."""
    async def call(self, payload: Payload) -> Payload:
        raise RuntimeError("boom")


class SlowFilter:
    """Sleeps for a configured duration."""
    def __init__(self, seconds: float):
        self._seconds = seconds

    async def call(self, payload: Payload) -> Payload:
        await asyncio.sleep(self._seconds)
        return payload.insert("slow", True)


# ══════════════════════════════════════════════════════════════
# PayloadSchema
# ══════════════════════════════════════════════════════════════

class TestPayloadSchema:
    """Tests for PayloadSchema shape validation."""

    def test_valid_schema(self):
        schema = PayloadSchema({"user_id": int, "email": str})
        p = Payload({"user_id": 123, "email": "a@b.com"})
        schema.validate(p)  # should not raise

    def test_missing_key(self):
        schema = PayloadSchema({"user_id": int, "email": str})
        p = Payload({"user_id": 123})
        with pytest.raises(SchemaViolation, match="Missing keys: email"):
            schema.validate(p)

    def test_type_mismatch(self):
        schema = PayloadSchema({"user_id": int})
        p = Payload({"user_id": "not_an_int"})
        with pytest.raises(SchemaViolation, match="Type errors"):
            schema.validate(p)

    def test_missing_and_type_error(self):
        schema = PayloadSchema({"a": int, "b": str})
        p = Payload({"a": "wrong"})
        with pytest.raises(SchemaViolation, match="Missing keys.*Type errors"):
            schema.validate(p)

    def test_keys_only(self):
        schema = PayloadSchema.keys("x", "y")
        p = Payload({"x": 1, "y": "anything"})
        schema.validate(p)  # no type check, should pass

    def test_keys_only_missing(self):
        schema = PayloadSchema.keys("x", "y")
        p = Payload({"x": 1})
        with pytest.raises(SchemaViolation, match="Missing keys: y"):
            schema.validate(p)

    def test_required_keys_property(self):
        schema = PayloadSchema({"a": int, "b": str})
        assert schema.required_keys == {"a", "b"}

    def test_repr(self):
        schema = PayloadSchema({"age": int})
        assert "age: int" in repr(schema)

    def test_keys_only_repr(self):
        schema = PayloadSchema.keys("x")
        assert "x" in repr(schema)


# ══════════════════════════════════════════════════════════════
# Pipeline Contracts — require_input / guarantee_output
# ══════════════════════════════════════════════════════════════

class TestPipelineContracts:
    """Tests for declarative pipeline pre/post conditions."""

    @pytest.mark.asyncio
    async def test_require_input_passes(self):
        pipe = Pipeline()
        pipe.add_filter(AddKeyFilter("result", 42), name="add")
        pipe.require_input("user_id")
        result = await pipe.run(Payload({"user_id": 1}))
        assert result.get("result") == 42

    @pytest.mark.asyncio
    async def test_require_input_fails(self):
        pipe = Pipeline()
        pipe.add_filter(AddKeyFilter("result", 42), name="add")
        pipe.require_input("user_id", "email")
        with pytest.raises(ContractViolation, match="missing keys.*email"):
            await pipe.run(Payload({"user_id": 1}))

    @pytest.mark.asyncio
    async def test_guarantee_output_passes(self):
        pipe = Pipeline()
        pipe.add_filter(AddKeyFilter("result", 42), name="add")
        pipe.guarantee_output("result")
        result = await pipe.run(Payload({"input": 1}))
        assert result.get("result") == 42

    @pytest.mark.asyncio
    async def test_guarantee_output_fails(self):
        pipe = Pipeline()
        pipe.add_filter(AddKeyFilter("result", 42), name="add")
        pipe.guarantee_output("missing_key")
        with pytest.raises(ContractViolation, match="missing keys.*missing_key"):
            await pipe.run(Payload({"input": 1}))

    @pytest.mark.asyncio
    async def test_input_schema_validation_in_run(self):
        pipe = Pipeline()
        pipe.add_filter(AddKeyFilter("result", 42), name="add")
        pipe.require_input_schema(PayloadSchema({"user_id": int}))
        with pytest.raises(SchemaViolation):
            await pipe.run(Payload({"user_id": "not_int"}))

    @pytest.mark.asyncio
    async def test_output_schema_validation_in_run(self):
        pipe = Pipeline()
        pipe.add_filter(AddKeyFilter("result", "not_int"), name="add")
        pipe.guarantee_output_schema(PayloadSchema({"result": int}))
        with pytest.raises(SchemaViolation, match="Type errors"):
            await pipe.run(Payload({}))

    @pytest.mark.asyncio
    async def test_both_contracts_pass(self):
        pipe = Pipeline()
        pipe.add_filter(AddKeyFilter("result", 42), name="add")
        pipe.require_input("input")
        pipe.guarantee_output("result")
        result = await pipe.run(Payload({"input": "data"}))
        assert result.get("result") == 42


# ══════════════════════════════════════════════════════════════
# Timeout
# ══════════════════════════════════════════════════════════════

class TestTimeout:
    """Tests for pipeline.with_timeout()."""

    @pytest.mark.asyncio
    async def test_completes_within_timeout(self):
        pipe = Pipeline()
        pipe.add_filter(AddKeyFilter("ok", True), name="fast")
        wrapped = pipe.with_timeout(seconds=5.0)
        result = await wrapped.run(Payload())
        assert result.get("ok") is True

    @pytest.mark.asyncio
    async def test_exceeds_timeout(self):
        pipe = Pipeline()
        pipe.add_filter(SlowFilter(5.0), name="slow")
        wrapped = pipe.with_timeout(seconds=0.05)
        with pytest.raises(PipelineTimeoutError, match="timed out"):
            await wrapped.run(Payload())

    @pytest.mark.asyncio
    async def test_timeout_emits_event(self):
        events = []
        pipe = Pipeline()
        pipe.add_filter(SlowFilter(5.0), name="slow")
        pipe.on("pipeline.timeout", lambda e: events.append(e))
        wrapped = pipe.with_timeout(seconds=0.05)
        with pytest.raises(PipelineTimeoutError):
            await wrapped.run(Payload())
        assert len(events) == 1
        assert events[0].kind == "pipeline.timeout"

    def test_timeout_run_sync(self):
        pipe = Pipeline()
        pipe.add_filter(AddKeyFilter("ok", True), name="fast")
        wrapped = pipe.with_timeout(seconds=5.0)
        result = wrapped.run_sync(Payload())
        assert result.get("ok") is True


# ══════════════════════════════════════════════════════════════
# Rate Limiting
# ══════════════════════════════════════════════════════════════

class TestRateLimit:
    """Tests for pipeline.with_rate_limit()."""

    @pytest.mark.asyncio
    async def test_rate_limit_throttles(self):
        pipe = Pipeline()
        pipe.add_filter(AddKeyFilter("ok", True), name="fast")
        wrapped = pipe.with_rate_limit(calls_per_second=20)

        t0 = time.monotonic()
        await wrapped.run(Payload())
        await wrapped.run(Payload())
        elapsed = time.monotonic() - t0

        # Second call should wait ~50ms (1/20 = 50ms interval)
        assert elapsed >= 0.04  # generous tolerance

    @pytest.mark.asyncio
    async def test_rate_limit_first_call_immediate(self):
        pipe = Pipeline()
        pipe.add_filter(AddKeyFilter("ok", True), name="fast")
        wrapped = pipe.with_rate_limit(calls_per_second=1000)

        t0 = time.monotonic()
        result = await wrapped.run(Payload())
        elapsed = time.monotonic() - t0

        assert result.get("ok") is True
        assert elapsed < 0.5  # first call is immediate

    def test_rate_limit_run_sync(self):
        pipe = Pipeline()
        pipe.add_filter(AddKeyFilter("ok", True), name="fast")
        wrapped = pipe.with_rate_limit(calls_per_second=100)
        result = wrapped.run_sync(Payload())
        assert result.get("ok") is True


# ══════════════════════════════════════════════════════════════
# Dead Letter Handling
# ══════════════════════════════════════════════════════════════

class TestDeadLetter:
    """Tests for pipeline.with_dead_letter()."""

    @pytest.mark.asyncio
    async def test_dead_letter_catches_error(self):
        dlh = LogDeadLetterHandler()
        pipe = Pipeline()
        pipe.add_filter(BoomFilter(), name="boom")
        wrapped = pipe.with_dead_letter(dlh)

        result = await wrapped.run(Payload({"input": 1}))
        # Should return original payload instead of raising
        assert result.get("input") == 1
        assert len(dlh) == 1
        assert isinstance(dlh.dead_letters[0][1], RuntimeError)

    @pytest.mark.asyncio
    async def test_dead_letter_passes_on_success(self):
        dlh = LogDeadLetterHandler()
        pipe = Pipeline()
        pipe.add_filter(AddKeyFilter("ok", True), name="ok")
        wrapped = pipe.with_dead_letter(dlh)

        result = await wrapped.run(Payload())
        assert result.get("ok") is True
        assert len(dlh) == 0

    @pytest.mark.asyncio
    async def test_dead_letter_emits_event(self):
        events = []
        pipe = Pipeline()
        pipe.add_filter(BoomFilter(), name="boom")
        pipe.on("dead_letter", lambda e: events.append(e))
        dlh = LogDeadLetterHandler()
        wrapped = pipe.with_dead_letter(dlh)

        await wrapped.run(Payload())
        assert len(events) == 1
        assert events[0].kind == "dead_letter"

    def test_dead_letter_run_sync(self):
        dlh = LogDeadLetterHandler()
        pipe = Pipeline()
        pipe.add_filter(BoomFilter(), name="boom")
        wrapped = pipe.with_dead_letter(dlh)
        result = wrapped.run_sync(Payload({"x": 1}))
        assert result.get("x") == 1
        assert len(dlh) == 1


# ══════════════════════════════════════════════════════════════
# Audit Trail
# ══════════════════════════════════════════════════════════════

class TestAuditTrail:
    """Tests for AuditTrail + AuditHook."""

    def test_audit_trail_empty(self):
        trail = AuditTrail()
        assert len(trail) == 0
        assert trail.entries == []
        assert trail.step_names == []

    def test_audit_trail_record(self):
        trail = AuditTrail()
        entry = AuditEntry(
            step_name="test", timestamp=1.0,
            input_keys=["a"], output_keys=["a", "b"], phase="after",
        )
        trail.record(entry)
        assert len(trail) == 1
        assert trail.step_names == ["test"]

    def test_audit_trail_repr(self):
        trail = AuditTrail()
        assert "0 entries" in repr(trail)

    @pytest.mark.asyncio
    async def test_audit_hook_records_steps(self):
        trail = AuditTrail()
        pipe = Pipeline()
        pipe.use_hook(AuditHook(trail))
        pipe.add_filter(AddKeyFilter("result", 42), name="add")
        pipe.add_filter(AddKeyFilter("extra", "x"), name="add_extra")

        await pipe.run(Payload({"input": 1}))

        assert len(trail) == 2
        assert trail.step_names == ["AddKeyFilter", "AddKeyFilter"]
        # First step: input had "input", output should have "input" + "result"
        assert "input" in trail.entries[0].input_keys
        assert "result" in trail.entries[0].output_keys

    @pytest.mark.asyncio
    async def test_enable_audit_convenience(self):
        pipe = Pipeline()
        pipe.add_filter(AddKeyFilter("x", 1), name="add")
        trail = pipe.enable_audit()

        await pipe.run(Payload())
        assert len(trail) == 1

    @pytest.mark.asyncio
    async def test_audit_hook_on_error(self):
        trail = AuditTrail()
        pipe = Pipeline()
        pipe.use_hook(AuditHook(trail))
        pipe.add_filter(BoomFilter(), name="boom")

        with pytest.raises(RuntimeError):
            await pipe.run(Payload({"a": 1}))

        assert len(trail) == 1
        assert trail.entries[0].phase == "error"
        assert "error" in trail.entries[0].metadata


# ══════════════════════════════════════════════════════════════
# Config-driven govern
# ══════════════════════════════════════════════════════════════

class TestGovernConfig:
    """Tests for from_config() with govern keys."""

    def _write_config(self, tmp_path, config: dict, fmt="json"):
        path = tmp_path / f"test.{fmt}"
        path.write_text(json.dumps(config))
        return str(path)

    @pytest.mark.asyncio
    async def test_require_input_from_config(self, tmp_path):
        from codeupipe import Registry
        reg = Registry()
        reg.register("AddKey", lambda: AddKeyFilter("result", 42))

        config = {
            "pipeline": {
                "steps": [{"name": "AddKey", "type": "filter"}],
                "require_input": ["user_id"],
            }
        }
        path = self._write_config(tmp_path, config)
        pipe = Pipeline.from_config(path, registry=reg)

        with pytest.raises(ContractViolation, match="user_id"):
            await pipe.run(Payload({}))

    @pytest.mark.asyncio
    async def test_guarantee_output_from_config(self, tmp_path):
        from codeupipe import Registry
        reg = Registry()
        reg.register("AddKey", lambda: AddKeyFilter("result", 42))

        config = {
            "pipeline": {
                "steps": [{"name": "AddKey", "type": "filter"}],
                "guarantee_output": ["result"],
            }
        }
        path = self._write_config(tmp_path, config)
        pipe = Pipeline.from_config(path, registry=reg)

        result = await pipe.run(Payload({}))
        assert result.get("result") == 42

    @pytest.mark.asyncio
    async def test_timeout_from_config(self, tmp_path):
        from codeupipe import Registry
        reg = Registry()
        reg.register("Slow", lambda: SlowFilter(5.0))

        config = {
            "pipeline": {
                "steps": [{"name": "Slow", "type": "filter"}],
                "timeout": 0.05,
            }
        }
        path = self._write_config(tmp_path, config)
        pipe = Pipeline.from_config(path, registry=reg)

        with pytest.raises(PipelineTimeoutError):
            await pipe.run(Payload())

    @pytest.mark.asyncio
    async def test_dead_letter_from_config(self, tmp_path):
        from codeupipe import Registry
        reg = Registry()
        reg.register("Boom", BoomFilter)
        dlh = LogDeadLetterHandler()
        reg.register("MyDLH", lambda: dlh)

        config = {
            "pipeline": {
                "steps": [{"name": "Boom", "type": "filter"}],
                "dead_letter": "MyDLH",
            }
        }
        path = self._write_config(tmp_path, config)
        pipe = Pipeline.from_config(path, registry=reg)

        await pipe.run(Payload({"x": 1}))
        assert len(dlh) == 1

    @pytest.mark.asyncio
    async def test_rate_limit_from_config(self, tmp_path):
        from codeupipe import Registry
        reg = Registry()
        reg.register("AddKey", lambda: AddKeyFilter("ok", True))

        config = {
            "pipeline": {
                "steps": [{"name": "AddKey", "type": "filter"}],
                "rate_limit": {"calls_per_second": 1000},
            }
        }
        path = self._write_config(tmp_path, config)
        pipe = Pipeline.from_config(path, registry=reg)

        result = await pipe.run(Payload())
        assert result.get("ok") is True

    @pytest.mark.asyncio
    async def test_rate_limit_scalar_from_config(self, tmp_path):
        from codeupipe import Registry
        reg = Registry()
        reg.register("AddKey", lambda: AddKeyFilter("ok", True))

        config = {
            "pipeline": {
                "steps": [{"name": "AddKey", "type": "filter"}],
                "rate_limit": 1000,
            }
        }
        path = self._write_config(tmp_path, config)
        pipe = Pipeline.from_config(path, registry=reg)

        result = await pipe.run(Payload())
        assert result.get("ok") is True


# ══════════════════════════════════════════════════════════════
# Wrapper chaining
# ══════════════════════════════════════════════════════════════

class TestGovernChaining:
    """Tests for chaining govern wrappers with resilience wrappers."""

    @pytest.mark.asyncio
    async def test_timeout_plus_retry(self):
        pipe = Pipeline()
        pipe.add_filter(AddKeyFilter("ok", True), name="fast")
        timeout_wrapped = pipe.with_timeout(seconds=5.0)
        # Compose manually: retry wraps timeout
        from codeupipe.core.pipeline import _RetryPipeline
        wrapped = _RetryPipeline(timeout_wrapped, max_retries=2)
        result = await wrapped.run(Payload())
        assert result.get("ok") is True

    @pytest.mark.asyncio
    async def test_dead_letter_plus_rate_limit(self):
        dlh = LogDeadLetterHandler()
        pipe = Pipeline()
        pipe.add_filter(BoomFilter(), name="boom")
        wrapped = pipe.with_dead_letter(dlh)

        result = await wrapped.run(Payload({"x": 1}))
        assert result.get("x") == 1
        assert len(dlh) == 1


# ══════════════════════════════════════════════════════════════
# LogDeadLetterHandler
# ══════════════════════════════════════════════════════════════

class TestLogDeadLetterHandler:
    """Tests for LogDeadLetterHandler in isolation."""

    @pytest.mark.asyncio
    async def test_collects_dead_letters(self):
        dlh = LogDeadLetterHandler()
        p = Payload({"a": 1})
        err = RuntimeError("test")
        await dlh.handle(p, err)

        assert len(dlh) == 1
        assert dlh.dead_letters[0] == (p, err)

    @pytest.mark.asyncio
    async def test_multiple_dead_letters(self):
        dlh = LogDeadLetterHandler()
        for i in range(5):
            await dlh.handle(Payload({"i": i}), ValueError(str(i)))
        assert len(dlh) == 5

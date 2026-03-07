"""Tests for Ring 5 — Distribute features.

Covers: serialization, RemoteFilter, Checkpoint, CheckpointHook,
        IterableSource, FileSource, WorkerPool.
"""

import asyncio
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import pytest
from codeupipe.core.payload import Payload
from codeupipe.core.pipeline import Pipeline
from codeupipe.distribute.remote import RemoteFilter
from codeupipe.distribute.checkpoint import Checkpoint, CheckpointHook
from codeupipe.distribute.source import IterableSource, FileSource
from codeupipe.distribute.worker import WorkerPool


# ── Helpers ──────────────────────────────────────────────────

class AddFilter:
    async def call(self, payload: Payload) -> Payload:
        return payload.insert("value", payload.get("value", 0) + 10)


# ── Payload Serialization ───────────────────────────────────

def test_payload_serialize_json():
    p = Payload({"x": 1, "y": "hello"})
    raw = p.serialize()
    assert isinstance(raw, bytes)
    envelope = json.loads(raw)
    assert envelope["data"]["x"] == 1
    assert envelope["data"]["y"] == "hello"


def test_payload_deserialize_json():
    raw = json.dumps({"data": {"x": 42}}).encode("utf-8")
    p = Payload.deserialize(raw)
    assert p.get("x") == 42


def test_payload_serialize_round_trip():
    original = Payload({"key": "value", "num": 99})
    raw = original.serialize()
    restored = Payload.deserialize(raw)
    assert restored.to_dict() == original.to_dict()


def test_payload_serialize_with_trace_and_lineage():
    p = Payload({"x": 1}, trace_id="trace-123", _lineage=["step_a", "step_b"])
    raw = p.serialize()
    restored = Payload.deserialize(raw)
    assert restored.trace_id == "trace-123"
    assert restored.lineage == ["step_a", "step_b"]
    assert restored.get("x") == 1


def test_payload_serialize_unsupported_format():
    p = Payload({"x": 1})
    with pytest.raises(ValueError, match="Unsupported format"):
        p.serialize(fmt="xml")


def test_payload_deserialize_unsupported_format():
    with pytest.raises(ValueError, match="Unsupported format"):
        Payload.deserialize(b"data", fmt="msgpack")


def test_payload_serialize_no_trace_no_lineage():
    """Envelope should not include trace_id/lineage if not set."""
    p = Payload({"x": 1})
    raw = p.serialize()
    envelope = json.loads(raw)
    assert "trace_id" not in envelope
    assert "lineage" not in envelope


# ── RemoteFilter ─────────────────────────────────────────────

class EchoHandler(BaseHTTPRequestHandler):
    """HTTP handler that echoes the payload back with a 'remote' flag."""

    def do_POST(self):
        content_length = int(self.headers["Content-Length"])
        body = self.rfile.read(content_length)
        payload = Payload.deserialize(body)
        result = payload.insert("remote", True)
        response = result.serialize()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        pass  # suppress output


@pytest.fixture
def echo_server():
    server = HTTPServer(("127.0.0.1", 0), EchoHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.mark.asyncio
async def test_remote_filter_sends_receives(echo_server):
    rf = RemoteFilter(echo_server)
    payload = Payload({"x": 42})
    result = await rf.call(payload)
    assert result.get("x") == 42
    assert result.get("remote") is True


@pytest.mark.asyncio
async def test_remote_filter_preserves_trace(echo_server):
    rf = RemoteFilter(echo_server)
    payload = Payload({"x": 1}, trace_id="t-100")
    result = await rf.call(payload)
    assert result.get("x") == 1
    assert result.trace_id == "t-100"


@pytest.mark.asyncio
async def test_remote_filter_in_pipeline(echo_server):
    rf = RemoteFilter(echo_server)
    pipe = Pipeline()
    pipe.add_filter(rf, name="remote_step")
    pipe.add_filter(AddFilter(), name="add")

    result = await pipe.run(Payload({"value": 5}))
    assert result.get("remote") is True
    assert result.get("value") == 15


# ── Checkpoint ───────────────────────────────────────────────

def test_checkpoint_save_load(tmp_path):
    path = str(tmp_path / "test.ckpt")
    ckpt = Checkpoint(path)

    payload = Payload({"count": 42})
    ckpt.save(payload)

    loaded = ckpt.load()
    assert loaded.get("count") == 42


def test_checkpoint_preserves_trace_and_lineage(tmp_path):
    path = str(tmp_path / "test.ckpt")
    ckpt = Checkpoint(path)

    payload = Payload({"x": 1}, trace_id="t-99", _lineage=["s1", "s2"])
    ckpt.save(payload)

    loaded = ckpt.load()
    assert loaded.trace_id == "t-99"
    assert loaded.lineage == ["s1", "s2"]


def test_checkpoint_exists(tmp_path):
    path = str(tmp_path / "test.ckpt")
    ckpt = Checkpoint(path)

    assert not ckpt.exists
    ckpt.save(Payload({"x": 1}))
    assert ckpt.exists


def test_checkpoint_clear(tmp_path):
    path = str(tmp_path / "test.ckpt")
    ckpt = Checkpoint(path)

    ckpt.save(Payload({"x": 1}))
    assert ckpt.exists
    ckpt.clear()
    assert not ckpt.exists


def test_checkpoint_metadata(tmp_path):
    path = str(tmp_path / "test.ckpt")
    ckpt = Checkpoint(path)

    ckpt.save(Payload({"x": 1}), metadata={"step": 3, "tag": "mid"})
    assert ckpt.metadata == {"step": 3, "tag": "mid"}


def test_checkpoint_timestamp(tmp_path):
    path = str(tmp_path / "test.ckpt")
    ckpt = Checkpoint(path)

    ckpt.save(Payload({"x": 1}))
    assert ckpt.timestamp is not None
    assert isinstance(ckpt.timestamp, float)


def test_checkpoint_no_metadata_before_save(tmp_path):
    path = str(tmp_path / "no_exist.ckpt")
    ckpt = Checkpoint(path)
    assert ckpt.metadata == {}
    assert ckpt.timestamp is None


@pytest.mark.asyncio
async def test_checkpoint_hook_auto_saves(tmp_path):
    path = str(tmp_path / "hook.ckpt")
    ckpt = Checkpoint(path)
    hook = CheckpointHook(ckpt)

    pipe = Pipeline()
    pipe.add_filter(AddFilter(), name="add_a")
    pipe.add_filter(AddFilter(), name="add_b")
    pipe.use_hook(hook)

    await pipe.run(Payload({"value": 0}))

    assert ckpt.exists
    loaded = ckpt.load()
    assert loaded.get("value") == 20
    assert ckpt.metadata["step"] == 2


def test_checkpoint_creates_parent_dirs(tmp_path):
    path = str(tmp_path / "deep" / "nested" / "test.ckpt")
    ckpt = Checkpoint(path)
    ckpt.save(Payload({"x": 1}))
    assert ckpt.exists


# ── Source Adapters ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_iterable_source_dicts():
    source = IterableSource([{"x": 1}, {"x": 2}, {"x": 3}])
    results = []
    async for payload in source:
        results.append(payload.get("x"))
    assert results == [1, 2, 3]


@pytest.mark.asyncio
async def test_iterable_source_payloads():
    items = [Payload({"a": i}) for i in range(3)]
    source = IterableSource(items)
    results = []
    async for payload in source:
        results.append(payload.get("a"))
    assert results == [0, 1, 2]


@pytest.mark.asyncio
async def test_iterable_source_reusable():
    source = IterableSource([{"x": 1}, {"x": 2}])
    first = []
    async for p in source:
        first.append(p.get("x"))
    second = []
    async for p in source:
        second.append(p.get("x"))
    assert first == second


@pytest.mark.asyncio
async def test_file_source(tmp_path):
    data_file = tmp_path / "data.txt"
    data_file.write_text("hello\nworld\nfoo")

    source = FileSource(str(data_file))
    results = []
    async for payload in source:
        results.append(payload.get("line"))
    assert results == ["hello", "world", "foo"]


@pytest.mark.asyncio
async def test_file_source_line_numbers(tmp_path):
    data_file = tmp_path / "data.txt"
    data_file.write_text("a\nb\nc")

    source = FileSource(str(data_file))
    line_nums = []
    async for payload in source:
        line_nums.append(payload.get("line_number"))
    assert line_nums == [1, 2, 3]


@pytest.mark.asyncio
async def test_file_source_custom_key(tmp_path):
    data_file = tmp_path / "data.txt"
    data_file.write_text("row1\nrow2")

    source = FileSource(str(data_file), key="row")
    results = []
    async for payload in source:
        results.append(payload.get("row"))
    assert results == ["row1", "row2"]


@pytest.mark.asyncio
async def test_iterable_source_with_pipeline_stream():
    class DoubleFilter:
        async def call(self, payload):
            return payload.insert("x", payload.get("x", 0) * 2)

    pipe = Pipeline()
    pipe.add_filter(DoubleFilter(), name="double")

    source = IterableSource([{"x": 1}, {"x": 2}, {"x": 3}])
    results = []
    async for result in pipe.stream(source):
        results.append(result.get("x"))

    assert results == [2, 4, 6]


# ── Worker Pool ──────────────────────────────────────────────

def _square(x):
    return x * x


@pytest.mark.asyncio
async def test_worker_pool_thread_run():
    pool = WorkerPool("thread", max_workers=2)
    result = await pool.run(_square, 7)
    assert result == 49
    pool.shutdown()


@pytest.mark.asyncio
async def test_worker_pool_thread_map():
    pool = WorkerPool("thread", max_workers=2)
    results = await pool.map(_square, [1, 2, 3, 4])
    assert results == [1, 4, 9, 16]
    pool.shutdown()


@pytest.mark.asyncio
async def test_worker_pool_process_run():
    pool = WorkerPool("process", max_workers=2)
    result = await pool.run(_square, 5)
    assert result == 25
    pool.shutdown()


@pytest.mark.asyncio
async def test_worker_pool_process_map():
    pool = WorkerPool("process", max_workers=2)
    results = await pool.map(_square, [2, 3, 4])
    assert results == [4, 9, 16]
    pool.shutdown()


def test_worker_pool_invalid_kind():
    with pytest.raises(ValueError, match="Unknown pool kind"):
        WorkerPool("gpu")


@pytest.mark.asyncio
async def test_worker_pool_in_filter():
    """WorkerPool integrates with a filter for CPU-bound work."""
    pool = WorkerPool("thread", max_workers=1)

    class PoolFilter:
        async def call(self, payload):
            val = payload.get("x", 0)
            result = await pool.run(_square, val)
            return payload.insert("x_squared", result)

    pipe = Pipeline()
    pipe.add_filter(PoolFilter(), name="pool_square")

    result = await pipe.run(Payload({"x": 6}))
    assert result.get("x_squared") == 36
    pool.shutdown()

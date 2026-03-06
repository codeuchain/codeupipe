"""
Tests for protection against calling .run() on pipelines with StreamFilters.

The .run() method enforces a 1→1 contract: one input payload → one output payload.
StreamFilters violate this by yielding 0..N outputs per input.
So .run() should fail loudly and tell the user to use .stream() instead.
"""

import pytest
from codeupipe.core import Pipeline, Payload
from codeupipe.core.filter import Filter
from codeupipe.core.stream_filter import StreamFilter


class SimpleFilter(Filter):
    """Regular filter: 1 in → 1 out."""
    async def call(self, payload):
        return payload.insert('processed', True)


class FanOutFilter(StreamFilter):
    """Stream filter: 1 in → 3 out (fan-out)."""
    async def stream(self, payload):
        # Yield 3 outputs from 1 input
        for i in range(3):
            yield payload.insert('copy', i)


class DropFilter(StreamFilter):
    """Stream filter: 1 in → 0 out (drop)."""
    async def stream(self, payload):
        # Yield nothing
        if False:
            yield  # Never executes, just for async generator syntax


class PassthroughStreamFilter(StreamFilter):
    """Stream filter: 1 in → 1 out (but still a StreamFilter structurally)."""
    async def stream(self, payload):
        yield payload


@pytest.mark.asyncio
async def test_run_fails_with_stream_filter():
    """Calling .run() on a pipeline with a StreamFilter raises ValueError."""
    pipeline = Pipeline()
    pipeline.add_filter(SimpleFilter(), "normal")
    pipeline.add_filter(FanOutFilter(), "fan_out")
    
    payload = Payload({'data': 'test'})
    
    with pytest.raises(ValueError) as exc_info:
        await pipeline.run(payload)
    
    # Check error message is helpful
    assert "StreamFilter" in str(exc_info.value)
    assert "fan_out" in str(exc_info.value)
    assert "pipeline.stream(" in str(exc_info.value)
    assert "async generator" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_fails_with_drop_filter():
    """Calling .run() with a drop StreamFilter (0 out) also fails."""
    pipeline = Pipeline()
    pipeline.add_filter(SimpleFilter(), "normal")
    pipeline.add_filter(DropFilter(), "drop")
    
    payload = Payload({'data': 'test'})
    
    with pytest.raises(ValueError) as exc_info:
        await pipeline.run(payload)
    
    assert "StreamFilter" in str(exc_info.value)
    assert "drop" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_fails_with_passthrough_stream_filter():
    """Even a 1→1 StreamFilter fails .run() (structural check, not semantic)."""
    pipeline = Pipeline()
    pipeline.add_filter(PassthroughStreamFilter(), "passthrough")
    
    payload = Payload({'data': 'test'})
    
    with pytest.raises(ValueError) as exc_info:
        await pipeline.run(payload)
    
    assert "StreamFilter" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_fails_with_stream_filter_in_middle():
    """StreamFilter in the middle of pipeline still triggers protection."""
    pipeline = Pipeline()
    pipeline.add_filter(SimpleFilter(), "before")
    pipeline.add_filter(FanOutFilter(), "fan_out_middle")
    pipeline.add_filter(SimpleFilter(), "after")
    
    payload = Payload({'data': 'test'})
    
    with pytest.raises(ValueError) as exc_info:
        await pipeline.run(payload)
    
    assert "StreamFilter" in str(exc_info.value)
    assert "fan_out_middle" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_fails_with_stream_filter_at_end():
    """StreamFilter at pipeline end also triggers protection."""
    pipeline = Pipeline()
    pipeline.add_filter(SimpleFilter(), "before")
    pipeline.add_filter(FanOutFilter(), "fan_out_end")
    
    payload = Payload({'data': 'test'})
    
    with pytest.raises(ValueError) as exc_info:
        await pipeline.run(payload)
    
    assert "StreamFilter" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_works_with_only_regular_filters():
    """Pipelines with only regular filters still work with .run()."""
    pipeline = Pipeline()
    pipeline.add_filter(SimpleFilter(), "first")
    pipeline.add_filter(SimpleFilter(), "second")
    
    payload = Payload({'test': 'data'})
    result = await pipeline.run(payload)
    
    assert result.get('processed') is True


@pytest.mark.asyncio
async def test_stream_works_with_stream_filter():
    """Using .stream() with StreamFilter pipeline works fine."""
    pipeline = Pipeline()
    pipeline.add_filter(SimpleFilter(), "normal")
    pipeline.add_filter(FanOutFilter(), "fan_out")
    
    async def source():
        yield Payload({'id': 1})
        yield Payload({'id': 2})
    
    results = []
    async for result in pipeline.stream(source()):
        results.append(result)
    
    # 2 inputs → 6 outputs (3 per input from fan-out)
    assert len(results) == 6
    
    # Check that all have 'processed' and 'copy' fields
    for result in results:
        assert result.get('processed') is True
        assert result.get('copy') is not None


@pytest.mark.asyncio
async def test_error_message_includes_stream_usage_hint():
    """Error message should show how to use .stream()."""
    pipeline = Pipeline()
    pipeline.add_filter(FanOutFilter(), "fan_out")
    
    payload = Payload({'data': 'test'})
    
    with pytest.raises(ValueError) as exc_info:
        await pipeline.run(payload)
    
    error_msg = str(exc_info.value)
    # Check for helpful hints in message
    assert "pipeline.stream(source)" in error_msg
    assert "async generator" in error_msg

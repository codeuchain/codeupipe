"""RED PHASE — Tests for ModelResponse and LanguageModelProvider protocol."""

import pytest

from codeupipe.ai.providers.base import LanguageModelProvider, ModelResponse


@pytest.mark.unit
class TestModelResponse:
    """Unit tests for the ModelResponse dataclass."""

    def test_default_construction(self):
        """Default ModelResponse has None content and empty tool_results."""
        resp = ModelResponse()
        assert resp.content is None
        assert resp.tool_results == ()
        assert resp.raw is None

    def test_with_content(self):
        """ModelResponse stores text content."""
        resp = ModelResponse(content="Hello, world!")
        assert resp.content == "Hello, world!"

    def test_with_tool_results(self):
        """ModelResponse stores tool results as immutable tuple."""
        tools = ({"result": {"key": "value"}},)
        resp = ModelResponse(content="ok", tool_results=tools)
        assert resp.tool_results == tools
        assert isinstance(resp.tool_results, tuple)

    def test_with_raw(self):
        """ModelResponse preserves raw provider response."""
        raw = {"provider_specific": True}
        resp = ModelResponse(raw=raw)
        assert resp.raw == raw

    def test_frozen(self):
        """ModelResponse is immutable."""
        resp = ModelResponse(content="hi")
        with pytest.raises(AttributeError):
            resp.content = "changed"  # type: ignore[misc]

    def test_to_event_dict_empty(self):
        """to_event_dict with no tool results produces expected shape."""
        resp = ModelResponse(content="hello")
        d = resp.to_event_dict()
        assert d == {"content": "hello", "tool_results": []}

    def test_to_event_dict_with_tools(self):
        """to_event_dict includes tool_results as list (not tuple)."""
        tools = (
            {"result": {"status": "ok"}, "__notifications__": []},
            {"result": {"data": 42}},
        )
        resp = ModelResponse(content="done", tool_results=tools)
        d = resp.to_event_dict()
        assert d["content"] == "done"
        assert isinstance(d["tool_results"], list)
        assert len(d["tool_results"]) == 2
        assert d["tool_results"][0]["result"]["status"] == "ok"

    def test_to_event_dict_none_content(self):
        """to_event_dict handles None content."""
        resp = ModelResponse()
        d = resp.to_event_dict()
        assert d["content"] is None
        assert d["tool_results"] == []


@pytest.mark.unit
class TestLanguageModelProviderProtocol:
    """Verify the protocol is runtime-checkable."""

    def test_protocol_is_runtime_checkable(self):
        """LanguageModelProvider supports isinstance checks."""

        class FakeProvider:
            async def start(self, **kwargs):
                pass

            async def send(self, prompt: str) -> ModelResponse:
                return ModelResponse(content="fake")

            async def stop(self):
                pass

        provider = FakeProvider()
        assert isinstance(provider, LanguageModelProvider)

    def test_non_provider_fails_check(self):
        """Objects missing methods are not providers."""

        class NotAProvider:
            async def send(self, prompt: str) -> ModelResponse:
                return ModelResponse()

        obj = NotAProvider()
        assert not isinstance(obj, LanguageModelProvider)

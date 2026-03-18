"""Base provider types — Protocol and normalized response.

LanguageModelProvider defines the interface every provider must implement.
ModelResponse is the normalized output that LanguageModelLink places
on context, ensuring downstream links never see provider-specific shapes.

Design:
    - Protocol (structural typing) so providers don't need to inherit
    - ModelResponse is frozen dataclass for immutability
    - tool_results as tuple (immutable) for context safety
    - tool_calls as tuple (immutable) for pending tool invocations
    - raw field preserves provider-specific data for debugging
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolCall:
    """A pending tool invocation requested by the model.

    When a provider does NOT handle tool execution internally
    (e.g., direct HTTP to chat/completions), it returns ToolCall
    instances on ModelResponse.tool_calls. ExecuteToolCallsLink
    detects these and runs them via the ToolExecutor on context.

    SDK-based providers (e.g., CopilotProvider via send_and_wait)
    handle tool execution internally and return empty tool_calls.

    Attributes:
        id: Unique call identifier from the model.
        name: Tool/function name to invoke.
        arguments: JSON-encoded argument string.
    """

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ModelResponse:
    """Normalized response from any language model provider.

    Attributes:
        content: The text response from the model (None if no content).
        tool_results: Tool call results returned by the provider, if any.
            Each dict follows the shape downstream links expect:
            ``{"result": {...}, "__notifications__": [...], ...}``
        tool_calls: Pending tool invocations the model requested.
            Non-empty only for providers that do NOT execute tools
            internally. ExecuteToolCallsLink processes these.
        raw: The original provider-specific response object.
            Preserved for debugging and provider-specific introspection.
    """

    content: str | None = None
    tool_results: tuple[dict, ...] = ()
    tool_calls: tuple[ToolCall, ...] = ()
    raw: Any = field(default=None, repr=False)

    def to_event_dict(self) -> dict:
        """Convert to the normalized dict shape downstream links expect.

        BackchannelLink, ToolContinuationLink, and ContextAttributionLink
        all handle ``isinstance(event, dict)`` with ``tool_results`` key.
        ExecuteToolCallsLink reads ``tool_calls`` for pending invocations.
        """
        return {
            "content": self.content,
            "tool_results": list(self.tool_results),
            "tool_calls": [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in self.tool_calls
            ],
        }


class ToolExecutor(Protocol):
    """Interface for executing tool calls locally.

    Providers that handle tool execution internally (SDK-based) don't
    need this. For providers that return raw tool_calls (HTTP-based),
    place a ToolExecutor on context and ExecuteToolCallsLink will use it.

    Implementations should be safe to call from async context.
    """

    async def execute(self, name: str, arguments: str) -> dict:
        """Execute a tool by name with JSON-encoded arguments.

        Args:
            name: The tool/function name.
            arguments: JSON string of arguments.

        Returns:
            Result dict. May contain ``__follow_up__`` or
            ``__notifications__`` keys for downstream processing.
        """
        ...


@runtime_checkable
class LanguageModelProvider(Protocol):
    """Interface for language model providers.

    Every provider must implement three lifecycle methods:
        start()  — Initialize connections, create sessions
        send()   — Send a prompt and return a normalized response
        stop()   — Tear down connections, release resources

    Providers are stateful: start() must be called before send(),
    and stop() should be called for graceful shutdown.

    Example:
        provider = SomeProvider(model="gpt-4.1", api_key="...")
        await provider.start()
        response = await provider.send("Hello, world!")
        print(response.content)
        await provider.stop()
    """

    async def start(self, **kwargs: Any) -> None:
        """Initialize the provider (connections, sessions, auth).

        Keyword arguments are provider-specific. CopilotProvider
        accepts ``mcp_servers`` here; an HTTP provider might accept
        ``headers`` or ``timeout``.
        """
        ...

    async def send(self, prompt: str) -> ModelResponse:
        """Send a prompt to the language model and return the response.

        Args:
            prompt: The complete prompt string to send.

        Returns:
            ModelResponse with content, tool_results, and raw response.

        Raises:
            RuntimeError: If the provider has not been started.
        """
        ...

    async def stop(self) -> None:
        """Tear down connections and release resources."""
        ...

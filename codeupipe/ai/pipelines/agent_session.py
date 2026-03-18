"""AgentSessionChain — Full agent lifecycle orchestration.

Composes the Links into a pipeline:
  RegisterServers → DiscoverByIntent → InitProvider → AgentLoop → Cleanup

The InitProvider replaces the old InitClient + CreateSession pair.
A LanguageModelProvider is configured once and passed to the chain;
all LLM interaction flows through LanguageModelLink inside the loop.

The DiscoverByIntent step is optional — if a capability_registry is
on context, it discovers capabilities from the user's prompt. Otherwise
it passes through unchanged, preserving backward compatibility.

Provider resolution order (when no explicit provider given):
  1. ApiKeyStore active provider → OpenAICompatibleProvider
  2. Fallback → CopilotProvider (Copilot SDK)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from codeupipe import Pipeline

from codeupipe.ai.filters.discovery.discover_by_intent import DiscoverByIntentLink
from codeupipe.ai.filters.init_provider import InitProviderLink
from codeupipe.ai.filters.loop.agent_loop import AgentLoopLink
from codeupipe.ai.filters.register_servers import RegisterServersLink
from codeupipe.ai.filters.session_cleanup import CleanupSessionLink

if TYPE_CHECKING:
    from codeupipe.ai.providers.base import LanguageModelProvider

logger = logging.getLogger("codeupipe.ai.pipelines.agent_session")


def _resolve_provider() -> LanguageModelProvider:
    """Resolve a provider from the encrypted key store, or fall back to Copilot.

    Resolution order:
        1. If ``ApiKeyStore`` has an active (or sole) provider,
           create an ``OpenAICompatibleProvider`` from it.
        2. Otherwise, fall back to ``CopilotProvider``.
    """
    try:
        from codeupipe.ai.providers.api_key_store import ApiKeyStore
        from codeupipe.ai.providers.openai_compat import OpenAICompatibleProvider

        store = ApiKeyStore()
        entry = store.resolve_active()
        if entry is not None:
            logger.info(
                "Using stored provider '%s' (%s, model=%s)",
                entry.name,
                entry.base_url,
                entry.model,
            )
            return OpenAICompatibleProvider(
                base_url=entry.base_url,
                api_key=entry.api_key,
                model=entry.model,
                **entry.extras,
            )
    except Exception:
        logger.debug("ApiKeyStore resolution failed, falling back to Copilot", exc_info=True)

    from codeupipe.ai.providers.copilot import CopilotProvider
    return CopilotProvider()


def build_agent_session_chain(
    provider: LanguageModelProvider | None = None,
    turn_chain: Pipeline | None = None,
) -> Pipeline:
    """Build the agent session lifecycle chain.

    Flow:
        register_servers → discover_by_intent → init_provider →
        agent_loop → cleanup

    Args:
        provider: Optional pre-configured language model provider.
            When *None*, resolves from the encrypted API key store
            (``ApiKeyStore``).  Falls back to ``CopilotProvider``
            if no stored keys exist.
        turn_chain: Optional pre-built turn chain for AgentLoopLink.
            Pass a chain with middleware attached (e.g. EventEmitterMiddleware)
            to observe inner-loop link execution.  When *None*, AgentLoopLink
            builds its own default turn chain.

    Context requirements:
        - registry: ServerRegistry (the hub dock)
        - model: str (e.g. "gpt-4.1")
        - prompt: str
        - capability_registry: CapabilityRegistry (optional, enables discovery)
        - max_iterations: int (optional, default 10 — safety cap)

    Context outputs:
        - response: str (agent's response from final turn)
        - agent_state: AgentState (full loop history)
        - cleaned_up: bool
        - provider: LanguageModelProvider (the initialized provider)
        - capabilities: list[CapabilityDefinition] (if discovery enabled)
    """
    if provider is None:
        provider = _resolve_provider()

    chain = Pipeline()

    chain.add_filter(RegisterServersLink(), "register_servers")
    chain.add_filter(DiscoverByIntentLink(), "discover_by_intent")
    chain.add_filter(InitProviderLink(provider), "init_provider")
    chain.add_filter(AgentLoopLink(turn_chain=turn_chain), "agent_loop")
    chain.add_filter(CleanupSessionLink(), "cleanup")

    # Sequential pipeline — each step always flows to the next

    return chain

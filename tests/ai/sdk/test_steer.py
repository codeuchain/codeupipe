"""RED PHASE — Tests for Agent.steer() and persistent context directives.

Steer modifies persistent context directives that are prepended to every
prompt. This is a zero-API-cost technique — directives are part of the
context, not a new request. The agent reads them as framing on every turn.

The directives are stored on the hub (HubIOWrapper) and injected into
context by seed_context(). ReadInputLink prepends them to every prompt.
"""

import pytest

from codeupipe.ai.hub.io_wrapper import HubIOWrapper
from codeupipe.ai.hub.registry import ServerRegistry


class TestHubDirectives:
    """HubIOWrapper manages persistent context directives."""

    def _make_wrapper(self) -> HubIOWrapper:
        return HubIOWrapper(server_registry=ServerRegistry())

    def test_no_directives_by_default(self):
        """Fresh hub has no directives."""
        wrapper = self._make_wrapper()
        assert wrapper.directives == []

    def test_add_directive(self):
        """add_directive() appends a persistent directive."""
        wrapper = self._make_wrapper()
        wrapper.add_directive("Focus on security")
        assert wrapper.directives == ["Focus on security"]

    def test_add_multiple_directives(self):
        """Multiple directives accumulate in order."""
        wrapper = self._make_wrapper()
        wrapper.add_directive("Use TypeScript")
        wrapper.add_directive("Focus on performance")
        assert wrapper.directives == ["Use TypeScript", "Focus on performance"]

    def test_clear_directives(self):
        """clear_directives() removes all persistent directives."""
        wrapper = self._make_wrapper()
        wrapper.add_directive("Something")
        wrapper.add_directive("Else")
        wrapper.clear_directives()
        assert wrapper.directives == []

    def test_remove_directive(self):
        """remove_directive() removes a specific directive."""
        wrapper = self._make_wrapper()
        wrapper.add_directive("Keep this")
        wrapper.add_directive("Remove this")
        wrapper.remove_directive("Remove this")
        assert wrapper.directives == ["Keep this"]

    def test_remove_nonexistent_directive_is_safe(self):
        """remove_directive() for missing directive is a no-op."""
        wrapper = self._make_wrapper()
        wrapper.add_directive("Only one")
        wrapper.remove_directive("Not here")
        assert wrapper.directives == ["Only one"]

    def test_directives_in_seed_context(self):
        """seed_context() includes directives."""
        wrapper = self._make_wrapper()
        wrapper.add_directive("Be concise")
        ctx = wrapper.seed_context()
        assert ctx["directives"] == ["Be concise"]

    def test_seed_context_empty_directives(self):
        """seed_context() includes empty directives list when none set."""
        wrapper = self._make_wrapper()
        ctx = wrapper.seed_context()
        assert ctx["directives"] == []

    def test_duplicate_directive_allowed(self):
        """Duplicate directives are allowed (user's choice)."""
        wrapper = self._make_wrapper()
        wrapper.add_directive("Same thing")
        wrapper.add_directive("Same thing")
        assert wrapper.directives == ["Same thing", "Same thing"]


class TestAgentSteer:
    """Agent.steer() and Agent.clear_steer() manage directives."""

    def test_steer_adds_directive(self):
        """steer() adds a persistent directive."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()
        agent.steer("Focus on security implications")
        assert "Focus on security implications" in agent.directives

    def test_steer_multiple(self):
        """Multiple steer() calls accumulate."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()
        agent.steer("Use TypeScript")
        agent.steer("Be concise")
        assert agent.directives == ["Use TypeScript", "Be concise"]

    def test_clear_steer(self):
        """clear_steer() removes all directives."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()
        agent.steer("Something")
        agent.clear_steer()
        assert agent.directives == []

    def test_unsteer(self):
        """unsteer() removes a specific directive."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()
        agent.steer("Keep")
        agent.steer("Remove")
        agent.unsteer("Remove")
        assert agent.directives == ["Keep"]

    def test_directives_property_returns_copy(self):
        """directives property returns current list."""
        from codeupipe.ai.agent.agent import Agent

        agent = Agent()
        agent.steer("Test")
        d = agent.directives
        assert d == ["Test"]


class TestReadInputWithDirectives:
    """ReadInputLink prepends directives to every prompt."""

    @pytest.mark.asyncio
    async def test_directives_prepended_to_first_prompt(self):
        """Directives are prepended to the initial user prompt."""
        from codeupipe import Payload

        from codeupipe.ai.filters.loop.read_input import ReadInputLink
        from codeupipe.ai.loop.state import AgentState

        link = ReadInputLink()
        ctx = Payload({
            "prompt": "Build tests for auth",
            "agent_state": AgentState(),
            "directives": ["Focus on security", "Use pytest"],
        })

        result = await link.call(ctx)
        prompt = result.get("next_prompt")

        assert prompt is not None
        assert "Focus on security" in prompt
        assert "Use pytest" in prompt
        assert "Build tests for auth" in prompt

    @pytest.mark.asyncio
    async def test_directives_prepended_to_follow_up(self):
        """Directives are prepended to follow-up prompts too."""
        from codeupipe import Payload

        from codeupipe.ai.filters.loop.read_input import ReadInputLink
        from codeupipe.ai.loop.state import AgentState

        link = ReadInputLink()
        state = AgentState().increment()  # Not first turn
        ctx = Payload({
            "prompt": "original",
            "agent_state": state,
            "follow_up_prompt": "Continue with step 2",
            "directives": ["Be verbose"],
        })

        result = await link.call(ctx)
        prompt = result.get("next_prompt")
        assert "Be verbose" in prompt
        assert "Continue with step 2" in prompt

    @pytest.mark.asyncio
    async def test_no_directives_prompt_unchanged(self):
        """Without directives, prompt is unchanged."""
        from codeupipe import Payload

        from codeupipe.ai.filters.loop.read_input import ReadInputLink
        from codeupipe.ai.loop.state import AgentState

        link = ReadInputLink()
        ctx = Payload({
            "prompt": "Build tests for auth",
            "agent_state": AgentState(),
        })

        result = await link.call(ctx)
        assert result.get("next_prompt") == "Build tests for auth"

    @pytest.mark.asyncio
    async def test_empty_directives_prompt_unchanged(self):
        """Empty directives list doesn't alter the prompt."""
        from codeupipe import Payload

        from codeupipe.ai.filters.loop.read_input import ReadInputLink
        from codeupipe.ai.loop.state import AgentState

        link = ReadInputLink()
        ctx = Payload({
            "prompt": "Build tests for auth",
            "agent_state": AgentState(),
            "directives": [],
        })

        result = await link.call(ctx)
        assert result.get("next_prompt") == "Build tests for auth"

    @pytest.mark.asyncio
    async def test_directives_prepended_to_notification_prompt(self):
        """Directives are prepended even when prompt comes from notifications."""
        from codeupipe import Payload

        from codeupipe.ai.filters.loop.read_input import ReadInputLink
        from codeupipe.ai.loop.state import AgentState

        link = ReadInputLink()
        state = AgentState().increment()  # Not first turn
        ctx = Payload({
            "prompt": "original",
            "agent_state": state,
            "pending_notifications": [
                {"source": "ci", "message": "Build passed"}
            ],
            "directives": ["Acknowledge all notifications"],
        })

        result = await link.call(ctx)
        prompt = result.get("next_prompt")
        assert "Acknowledge all notifications" in prompt
        assert "Build passed" in prompt

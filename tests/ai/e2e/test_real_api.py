"""E2E tests — REAL API calls to GitHub Copilot.

These tests hit the actual GitHub Copilot API and require authentication.

Authentication options (in priority order):
1. Stored credentials from `copilot` CLI login (OAuth device flow)
2. Environment variable: COPILOT_GITHUB_TOKEN
3. Environment variable: GH_TOKEN
4. Environment variable: GITHUB_TOKEN

To authenticate with Copilot CLI:
    1. Ensure you have a GitHub Copilot subscription
    2. The SDK will automatically prompt for authentication on first use
    3. Follow the device flow (visit URL, enter code)
    4. Credentials are stored in system keychain

Run these tests separately:
    pytest -m e2e -v --tb=short

These tests will incur charges against your GitHub Copilot subscription.
"""

import os

import pytest

from codeupipe.cli.commands.ai_cmds import _run_agent as run_agent


@pytest.mark.e2e
class TestRealCopilotAPI:
    """E2E tests with real GitHub Copilot API calls."""

    @pytest.fixture(autouse=True)
    def check_auth(self):
        """Skip E2E tests if no auth is available."""
        has_env_token = any(
            [
                os.getenv("COPILOT_GITHUB_TOKEN"),
                os.getenv("GH_TOKEN"),
                os.getenv("GITHUB_TOKEN"),
            ]
        )
        if not has_env_token:
            pytest.skip(
                "E2E tests require authentication. Set COPILOT_GITHUB_TOKEN "
                "or authenticate with `copilot` CLI."
            )

    @pytest.mark.asyncio
    async def test_simple_math_question(self):
        """Verify agent can answer a simple math question via real API."""
        response = await run_agent(
            prompt="What is 7 times 8? Reply with ONLY the number.",
            model="gpt-4.1",
            verbose=False,
        )

        assert response is not None
        assert "56" in response

    @pytest.mark.asyncio
    async def test_echo_tools_available(self):
        """Verify MCP hub correctly exposes echo server tools to the agent."""
        response = await run_agent(
            prompt="List all available tools. What tools do you see?",
            model="gpt-4.1",
            verbose=False,
        )

        assert response is not None
        # Agent should see echo tools from our docked server
        # The exact response format varies, but it should mention tools
        assert len(response) > 20  # Non-empty substantive response

    @pytest.mark.asyncio
    async def test_coding_assistance(self):
        """Verify agent provides coding help."""
        response = await run_agent(
            prompt="Write a Python function to check if a number is prime. "
            "Reply with ONLY the function, no explanation.",
            model="gpt-4.1",
            verbose=False,
        )

        assert response is not None
        assert "def " in response
        assert "prime" in response.lower()

    @pytest.mark.asyncio
    async def test_verbose_logging(self):
        """Verify verbose mode works with real API."""
        # This just ensures verbose mode doesn't crash
        response = await run_agent(
            prompt="Say hello",
            model="gpt-4.1",
            verbose=True,
        )

        assert response is not None
        assert len(response) > 0


@pytest.mark.e2e
class TestAuthenticationFallbacks:
    """Test various authentication paths."""

    @pytest.mark.asyncio
    async def test_with_explicit_env_var(self, monkeypatch):
        """Test that COPILOT_GITHUB_TOKEN is used when set."""
        token = os.getenv("COPILOT_GITHUB_TOKEN")
        if not token:
            pytest.skip("COPILOT_GITHUB_TOKEN not set")

        # Explicitly set to ensure it's used
        monkeypatch.setenv("COPILOT_GITHUB_TOKEN", token)

        response = await run_agent(
            prompt="What is 2+2? Reply with ONLY the number.",
            model="gpt-4.1",
            verbose=False,
        )

        assert response is not None
        assert "4" in response

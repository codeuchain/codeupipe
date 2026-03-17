"""Tests for the agent-loop template — agentic turn loop scaffold.

Verifies cup init agent-loop scaffolds the full Claude Code / orchie pattern:
    providers/, tools/, skills/, prompts/, sessions/, config/,
    main.py, agent-specific tests, recipe resolution.
"""

import json

import pytest

from codeupipe.deploy.init import _TEMPLATES, init_project


class TestAgentLoopTemplateRegistered:
    """Verify the agent-loop template is registered and discoverable."""

    @pytest.mark.unit
    def test_template_in_registry(self):
        assert "agent-loop" in _TEMPLATES

    @pytest.mark.unit
    def test_template_description(self):
        desc = _TEMPLATES["agent-loop"]["description"]
        assert "agentic" in desc.lower() or "agent" in desc.lower()
        assert "turn" in desc.lower() or "loop" in desc.lower()

    @pytest.mark.unit
    def test_template_uses_agent_loop_recipe(self):
        recipes = _TEMPLATES["agent-loop"]["recipes"]
        assert "agent-loop" in recipes


class TestAgentLoopScaffoldStructure:
    """Verify the scaffolded project has all expected directories and files."""

    @pytest.fixture
    def scaffolded(self, tmp_path):
        result = init_project(
            template="agent-loop",
            name="test-agent",
            output_dir=str(tmp_path / "test-agent"),
            options={"ai": "Copilot"},
        )
        return tmp_path / "test-agent", result

    @pytest.mark.unit
    def test_project_dir_created(self, scaffolded):
        proj, _ = scaffolded
        assert proj.exists()
        assert proj.is_dir()

    @pytest.mark.unit
    def test_standard_files_present(self, scaffolded):
        proj, _ = scaffolded
        assert (proj / "cup.toml").exists()
        assert (proj / "pyproject.toml").exists()
        assert (proj / "README.md").exists()
        assert (proj / ".gitignore").exists()

    @pytest.mark.unit
    def test_providers_dir(self, scaffolded):
        proj, _ = scaffolded
        assert (proj / "providers").is_dir()
        assert (proj / "providers" / "__init__.py").exists()
        assert (proj / "providers" / "provider.py").exists()

    @pytest.mark.unit
    def test_tools_dir(self, scaffolded):
        proj, _ = scaffolded
        assert (proj / "tools").is_dir()
        assert (proj / "tools" / "__init__.py").exists()
        assert (proj / "tools" / "echo.py").exists()

    @pytest.mark.unit
    def test_skills_dir(self, scaffolded):
        proj, _ = scaffolded
        assert (proj / "skills").is_dir()
        assert (proj / "skills" / "README.md").exists()
        assert (proj / "skills" / "example.md").exists()

    @pytest.mark.unit
    def test_prompts_dir(self, scaffolded):
        proj, _ = scaffolded
        assert (proj / "prompts").is_dir()
        assert (proj / "prompts" / "system.md").exists()
        assert (proj / "prompts" / "tools.md").exists()

    @pytest.mark.unit
    def test_sessions_dir(self, scaffolded):
        proj, _ = scaffolded
        assert (proj / "sessions").is_dir()
        assert (proj / "sessions" / ".gitkeep").exists()

    @pytest.mark.unit
    def test_config_dir(self, scaffolded):
        proj, _ = scaffolded
        assert (proj / "config").is_dir()
        assert (proj / "config" / "agent.toml").exists()
        assert (proj / "config" / "hub.toml").exists()

    @pytest.mark.unit
    def test_main_py_exists(self, scaffolded):
        proj, _ = scaffolded
        assert (proj / "main.py").exists()

    @pytest.mark.unit
    def test_pipeline_config_exists(self, scaffolded):
        proj, _ = scaffolded
        assert (proj / "pipelines" / "agent-loop.json").exists()

    @pytest.mark.unit
    def test_filters_dir_has_agent_filter(self, scaffolded):
        proj, _ = scaffolded
        custom = (proj / "filters" / "custom.py").read_text()
        assert "CustomAgentFilter" in custom

    @pytest.mark.unit
    def test_tests_dir_has_agent_tests(self, scaffolded):
        proj, _ = scaffolded
        test_text = (proj / "tests" / "test_test_agent.py").read_text()
        assert "Agent" in test_text
        assert "prompt" in test_text


class TestAgentLoopFileContents:
    """Verify the content of scaffolded files is correct."""

    @pytest.fixture
    def proj(self, tmp_path):
        init_project(
            template="agent-loop",
            name="my-agent",
            output_dir=str(tmp_path / "my-agent"),
            options={"ai": "Anthropic"},
        )
        return tmp_path / "my-agent"

    @pytest.mark.unit
    def test_pyproject_has_ai_extra(self, proj):
        text = (proj / "pyproject.toml").read_text()
        assert "codeupipe[ai]" in text

    @pytest.mark.unit
    def test_provider_uses_option(self, proj):
        text = (proj / "providers" / "provider.py").read_text()
        assert "AnthropicProvider" in text

    @pytest.mark.unit
    def test_system_prompt_has_layers(self, proj):
        text = (proj / "prompts" / "system.md").read_text()
        assert "Layer 1" in text
        assert "Layer 2" in text
        assert "Layer 3" in text
        assert "Layer 4" in text

    @pytest.mark.unit
    def test_tools_prompt_has_follow_up(self, proj):
        text = (proj / "prompts" / "tools.md").read_text()
        assert "__follow_up__" in text

    @pytest.mark.unit
    def test_agent_config_has_budget(self, proj):
        text = (proj / "config" / "agent.toml").read_text()
        assert "max_tokens" in text
        assert "revision_threshold" in text
        assert "pruning_threshold" in text

    @pytest.mark.unit
    def test_hub_config_has_echo_server(self, proj):
        text = (proj / "config" / "hub.toml").read_text()
        assert "[servers.echo]" in text

    @pytest.mark.unit
    def test_main_py_has_agent_import(self, proj):
        text = (proj / "main.py").read_text()
        assert "from codeupipe.ai import Agent" in text
        assert "agent.ask" in text or "agent.run" in text

    @pytest.mark.unit
    def test_readme_has_architecture(self, proj):
        text = (proj / "README.md").read_text()
        assert "TURN LOOP" in text
        assert "check_done" in text
        assert "language_model" in text

    @pytest.mark.unit
    def test_gitignore_has_sessions(self, proj):
        text = (proj / ".gitignore").read_text()
        assert "sessions/" in text

    @pytest.mark.unit
    def test_tool_echo_has_follow_up_convention(self, proj):
        text = (proj / "tools" / "echo.py").read_text()
        assert "__follow_up__" in text

    @pytest.mark.unit
    def test_skills_readme_explains_lazy_loading(self, proj):
        text = (proj / "skills" / "README.md").read_text()
        assert "lazy" in text.lower() or "on demand" in text.lower()


class TestAgentLoopRecipe:
    """Verify the agent-loop recipe resolves correctly."""

    @pytest.mark.unit
    def test_recipe_resolves_with_provider(self):
        from codeupipe.deploy.recipe import resolve_recipe

        config, deps = resolve_recipe("agent-loop", {"ai_provider": "OpenAI"})
        pipeline = config.get("pipeline", {})
        assert pipeline.get("name") == "agent-session"

        # Should have steps
        steps = pipeline.get("steps", [])
        assert len(steps) >= 3  # at least register, init, loop, cleanup

    @pytest.mark.unit
    def test_recipe_has_turn_loop_steps(self):
        from codeupipe.deploy.recipe import resolve_recipe

        config, _ = resolve_recipe("agent-loop", {"ai_provider": "Copilot"})
        steps = config["pipeline"]["steps"]

        # Find the AgentLoop step (nested pipeline)
        loop_step = None
        for step in steps:
            if step.get("name") == "AgentLoop":
                loop_step = step
                break

        assert loop_step is not None, "AgentLoop step not found"
        assert loop_step["type"] == "pipeline"

        inner_steps = loop_step.get("steps", [])
        inner_names = [s["name"] for s in inner_steps]

        # Verify the 14-filter turn pipeline
        assert "InjectNotifications" in inner_names
        assert "ReadInput" in inner_names
        assert "CopilotLanguageModel" in inner_names
        assert "ProcessResponse" in inner_names
        assert "ToolContinuation" in inner_names
        assert "CheckDone" in inner_names
        assert "ContextPruning" in inner_names
        assert "SaveCheckpoint" in inner_names

    @pytest.mark.unit
    def test_recipe_has_hooks(self):
        from codeupipe.deploy.recipe import resolve_recipe

        config, _ = resolve_recipe("agent-loop", {"ai_provider": "Copilot"})
        hooks = config["pipeline"].get("hooks", [])
        hook_names = [h["name"] for h in hooks]

        assert "EventEmitter" in hook_names
        assert "AuditHook" in hook_names
        assert "TimingHook" in hook_names

    @pytest.mark.unit
    def test_recipe_has_context_schema(self):
        from codeupipe.deploy.recipe import resolve_recipe

        config, _ = resolve_recipe("agent-loop", {"ai_provider": "Copilot"})
        schema = config["pipeline"].get("context_schema", {})

        assert "prompt" in schema
        assert "model" in schema
        assert "max_iterations" in schema
        assert "directives" in schema

    @pytest.mark.unit
    def test_recipe_requires_ai_provider_variable(self):
        from codeupipe.deploy.recipe import RecipeError, resolve_recipe

        with pytest.raises(RecipeError, match="variables"):
            resolve_recipe("agent-loop", {})


class TestAgentLoopDefaultProvider:
    """Verify scaffolding works with default (no ai option)."""

    @pytest.mark.unit
    def test_scaffold_without_ai_option(self, tmp_path):
        """When no ai option given, provider name defaults to 'Copilot'."""
        result = init_project(
            template="agent-loop",
            name="bare-agent",
            output_dir=str(tmp_path / "bare-agent"),
        )
        proj = tmp_path / "bare-agent"
        text = (proj / "providers" / "provider.py").read_text()
        assert "CopilotProvider" in text

"""CopilotApp — main Textual application for the Copilot Agent TUI.

This is the entry point for the TUI. It composes the ChatPane,
EventPanel, InputBar, Header, and Footer into a split-horizontal
layout (Option A from TUI_DESIGN.md).

The app consumes the same AgentEvent stream as the CLI — it's just
another consumer of the SDK's Agent.run() async iterator.
"""

from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Footer, Header

from codeupipe.ai.tui.widgets.chat_pane import ChatPane
from codeupipe.ai.tui.widgets.event_panel import EventPanel
from codeupipe.ai.tui.widgets.input_bar import InputBar

from codeupipe.ai.agent.events import EventType


class CopilotApp(App):
    """Copilot Agent TUI — a Textual-based chat interface.

    Split-horizontal layout with chat pane (left) and activity
    panel (right). Streams AgentEvent objects from the SDK into
    visual widgets.
    """

    CSS_PATH = "app.tcss"
    TITLE = "Copilot Agent"
    SUB_TITLE = ""

    # Reactive state
    model_name: reactive[str] = reactive("gpt-4.1")
    mode: reactive[str] = reactive("agent")
    turn_count: reactive[int] = reactive(0)
    is_busy: reactive[bool] = reactive(False)

    # Tier 1: Always shown in footer
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+e", "toggle_events", "Events", show=True),
        Binding("ctrl+l", "clear_chat", "Clear", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
        # Tier 2: Hidden from footer, active
        Binding("ctrl+s", "save_session", "Save", show=False),
        Binding("ctrl+v", "toggle_verbose", "Verbose", show=False),
    ]

    def __init__(
        self,
        model: str = "gpt-4.1",
        verbose: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._model = model
        self._verbose = verbose
        self._agent = None
        self._agent_task: asyncio.Task | None = None
        self._events_visible = True

    def compose(self) -> ComposeResult:
        """Build the widget tree."""
        yield Header()
        with Horizontal(id="main"):
            yield ChatPane(id="chat")
            yield EventPanel(id="events")
        yield InputBar(id="input")
        yield Footer(show_command_palette=True, compact=True)

    def on_mount(self) -> None:
        """Initialize the app after mounting."""
        self.model_name = self._model
        self.sub_title = f"{self._model} │ {self.mode}"

        # Write initial headers
        event_panel = self.query_one("#events", EventPanel)
        event_panel.write_header()

        chat = self.query_one("#chat", ChatPane)
        chat.write_system(
            f"Copilot Agent ({self._model}) — type /help for commands"
        )

        # Focus the input bar
        self.query_one("#input", InputBar).focus()

    # ── Reactive watchers ────────────────────────────────────────

    def watch_model_name(self, value: str) -> None:
        """Update subtitle when model changes."""
        self.sub_title = f"{value} │ {self.mode}"

    def watch_mode(self, value: str) -> None:
        """Update subtitle when mode changes."""
        self.sub_title = f"{self.model_name} │ {value}"

    def watch_is_busy(self, busy: bool) -> None:
        """Disable input while agent is processing."""
        input_bar = self.query_one("#input", InputBar)
        input_bar.disabled = busy
        if not busy:
            input_bar.focus()

    # ── Event handlers ───────────────────────────────────────────

    def on_input_bar_submitted(self, event: InputBar.Submitted) -> None:
        """Handle user input submission."""
        value = event.value
        mode = event.mode

        # Handle slash commands
        if value.startswith("/"):
            self._handle_command(value)
            return

        # Handle shell passthrough
        if value.startswith("!"):
            self._handle_shell(value[1:])
            return

        # Handle per-message ask mode (? prefix)
        effective_mode = mode
        if value.startswith("? "):
            value = value[2:]
            effective_mode = "ask"

        # Write user message to chat
        chat = self.query_one("#chat", ChatPane)
        mode_prefix = f"[{effective_mode}] " if effective_mode != "agent" else ""
        chat.write_user(f"{mode_prefix}{value}")

        # Run the agent
        self._run_agent(value)

    # ── Slash commands ───────────────────────────────────────────

    def _handle_command(self, command: str) -> None:
        """Dispatch a slash command."""
        chat = self.query_one("#chat", ChatPane)
        cmd = command.strip().lower()

        if cmd == "/help":
            chat.write_system(
                "Commands: /help, /clear, /save, /sessions, /model, /exit\n"
                "Prefixes: @ (file context), ! (shell), ? (ask mode)\n"
                "Keys: Ctrl+E (events), Ctrl+L (clear), Ctrl+Q (quit)"
            )
        elif cmd == "/clear":
            chat.clear()
            chat.write_system("Chat cleared.")
        elif cmd == "/exit":
            self.exit()
        elif cmd.startswith("/model"):
            parts = command.split(maxsplit=1)
            if len(parts) > 1:
                self.model_name = parts[1].strip()
                chat.write_system(f"Model changed to {self.model_name}")
            else:
                chat.write_system(f"Current model: {self.model_name}")
        elif cmd == "/save":
            chat.write_system("Session save not yet implemented (Phase 2c)")
        elif cmd == "/sessions":
            chat.write_system("Session browser not yet implemented (Phase 2c)")
        else:
            chat.write_system(f"Unknown command: {command}")

    def _handle_shell(self, command: str) -> None:
        """Execute a shell command and show output."""
        import subprocess

        chat = self.query_one("#chat", ChatPane)
        chat.write_system(f"$ {command}")

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=".",
            )
            output = result.stdout or result.stderr or "(no output)"
            chat.write_system(output.strip())
        except subprocess.TimeoutExpired:
            chat.write_error("Shell command timed out (30s limit)")
        except Exception as e:
            chat.write_error(f"Shell error: {e}")

    # ── Agent execution ──────────────────────────────────────────

    def _run_agent(self, prompt: str) -> None:
        """Start the agent in a background task."""
        self.is_busy = True
        self._agent_task = asyncio.create_task(self._agent_loop(prompt))

    async def _agent_loop(self, prompt: str) -> None:
        """Run the agent and stream events to widgets."""
        chat = self.query_one("#chat", ChatPane)
        event_panel = self.query_one("#events", EventPanel)

        try:
            agent = self._get_agent()
            response_parts: list[str] = []

            chat.begin_agent()

            async for event in agent.run(prompt):
                # Always update event panel
                event_panel.handle_event(event)

                match event.type:
                    case EventType.RESPONSE:
                        content = event.data.get("content", "")
                        if content:
                            response_parts.append(content)
                            chat.stream_token(content)

                    case EventType.TURN_START:
                        self.turn_count = event.data.get(
                            "iteration", self.turn_count + 1
                        )

                    case EventType.ERROR:
                        error = event.data.get("error", str(event.data))
                        chat.end_agent()
                        chat.write_error(str(error))

                    case EventType.DONE:
                        chat.end_agent()
                        if not response_parts:
                            chat.write_system("(No response)")

        except Exception as e:
            chat.end_agent()
            chat.write_error(f"Agent error: {e}")
        finally:
            self.is_busy = False

    def _get_agent(self):
        """Get or create the Agent instance."""
        if self._agent is None:
            from codeupipe.ai.agent import Agent, AgentConfig

            self._agent = Agent(
                config=AgentConfig(
                    model=self.model_name,
                    max_iterations=20,
                    verbose=self._verbose,
                )
            )
        return self._agent

    # ── Actions ──────────────────────────────────────────────────

    def action_toggle_events(self) -> None:
        """Toggle the event panel visibility."""
        panel = self.query_one("#events", EventPanel)
        self._events_visible = not self._events_visible
        panel.display = self._events_visible

    def action_clear_chat(self) -> None:
        """Clear the chat pane."""
        chat = self.query_one("#chat", ChatPane)
        chat.clear()
        chat.write_system("Chat cleared.")

    def action_cancel(self) -> None:
        """Cancel the current agent run."""
        if self._agent_task and not self._agent_task.done():
            self._agent_task.cancel()
            self.is_busy = False
            chat = self.query_one("#chat", ChatPane)
            chat.end_agent()
            chat.write_system("Cancelled.")

    def action_save_session(self) -> None:
        """Save the current session (Phase 2c placeholder)."""
        chat = self.query_one("#chat", ChatPane)
        chat.write_system("Session save not yet implemented (Phase 2c)")

    def action_toggle_verbose(self) -> None:
        """Toggle verbose event output."""
        self._verbose = not self._verbose
        if self._agent is not None:
            self._agent.config.verbose = self._verbose
        chat = self.query_one("#chat", ChatPane)
        state = "on" if self._verbose else "off"
        chat.write_system(f"Verbose mode: {state}")

"""``cup ai`` command group — agent, discovery, hub, TUI, eval.

All AI commands require ``pip install codeupipe[ai]`` at minimum.
Discovery needs ``[ai-discovery]`` and TUI needs ``[ai-tui]``.
"""

import asyncio
import json
import logging
import sys
from typing import List, Optional


# ── helpers ──────────────────────────────────────────────────────────

def _require_ai():
    """Fail fast if codeupipe[ai] extras are missing."""
    try:
        from codeupipe.ai._check import require_ai_deps
        require_ai_deps()
    except ImportError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


# ── setup ────────────────────────────────────────────────────────────

def setup(sub, reg):
    # ── cup ai ask <prompt> [--model M] [--verbose] ──────────────
    ask_parser = sub.add_parser(
        "ai-ask",
        help="Send a single prompt to the AI agent and print the response",
    )
    ask_parser.add_argument("prompt", help="Natural-language prompt")
    ask_parser.add_argument(
        "--model", "-m", default="gpt-4.1",
        help="Model to use (default: gpt-4.1)",
    )
    ask_parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging",
    )
    ask_parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output result as JSON",
    )
    reg.register("ai-ask", _handle_ask)

    # ── cup ai-interactive [--model M] [--verbose] ───────────────
    interactive_parser = sub.add_parser(
        "ai-interactive",
        help="Start an interactive REPL session with the AI agent",
    )
    interactive_parser.add_argument(
        "--model", "-m", default="gpt-4.1",
        help="Model to use (default: gpt-4.1)",
    )
    interactive_parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose event output",
    )
    reg.register("ai-interactive", _handle_interactive)

    # ── cup ai-tui [--model M] [--verbose] ───────────────────────
    tui_parser = sub.add_parser(
        "ai-tui",
        help="Launch the rich Textual TUI (requires codeupipe[ai-tui])",
    )
    tui_parser.add_argument(
        "--model", "-m", default="gpt-4.1",
        help="Model to use (default: gpt-4.1)",
    )
    tui_parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose event output",
    )
    reg.register("ai-tui", _handle_tui)

    # ── cup ai-discover <intent> [--verbose] ─────────────────────
    discover_parser = sub.add_parser(
        "ai-discover",
        help="Discover capabilities matching a natural-language intent",
    )
    discover_parser.add_argument("intent", help="Natural-language intent to search for")
    discover_parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging",
    )
    discover_parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output results as JSON",
    )
    reg.register("ai-discover", _handle_discover)

    # ── cup ai-sync [--verbose] ──────────────────────────────────
    sync_parser = sub.add_parser(
        "ai-sync",
        help="Sync local file-based capabilities (skills, instructions, plans)",
    )
    sync_parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging",
    )
    reg.register("ai-sync", _handle_sync)

    # ── cup ai-register --server-name N (--server-url U | --server-command C) ──
    register_parser = sub.add_parser(
        "ai-register",
        help="Register capabilities from an MCP server",
    )
    register_parser.add_argument(
        "--server-name", "-n", required=True,
        help="Name of the MCP server",
    )
    register_parser.add_argument(
        "--server-url", "-u",
        help="URL of the MCP server (for SSE connections)",
    )
    register_parser.add_argument(
        "--server-command", "-c",
        help="Command to run the MCP server (for Stdio connections)",
    )
    register_parser.add_argument(
        "--server-args", "-a", nargs="*",
        help="Arguments for the MCP server command (for Stdio connections)",
    )
    register_parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging",
    )
    reg.register("ai-register", _handle_register)

    # ── cup ai-hub ────────────────────────────────────────────────
    hub_parser = sub.add_parser(
        "ai-hub",
        help="Show the default hub server registry",
    )
    hub_parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output as JSON",
    )
    reg.register("ai-hub", _handle_hub)

    # ── cup ai-hub-manage <action> [options] ─────────────────────
    manage_parser = sub.add_parser(
        "ai-hub-manage",
        help="Manage MCP servers in the hub (list/add/remove/enable/disable/status/tools)",
    )
    manage_parser.add_argument(
        "action",
        choices=["list", "add", "remove", "enable", "disable", "status", "tools", "config"],
        help="Management action to perform",
    )
    manage_parser.add_argument(
        "--name", "-n",
        help="Server name (required for add/remove/enable/disable/status/tools/config)",
    )
    manage_parser.add_argument(
        "--command", "-c", dest="server_command",
        help="Server command (required for add, e.g. 'python' or 'node')",
    )
    manage_parser.add_argument(
        "--args", "-a", dest="server_args",
        help="Space-separated server arguments (e.g. '-m weather_server')",
    )
    manage_parser.add_argument(
        "--env", "-e",
        help="Comma-separated KEY=VALUE env pairs (e.g. 'API_KEY=abc,PORT=8080')",
    )
    manage_parser.add_argument(
        "--tools", "-t",
        help="Comma-separated tool names to expose (empty = all)",
    )
    manage_parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output as JSON",
    )
    reg.register("ai-hub-manage", _handle_hub_manage)

    # ── cup ai-keys <action> [options] ───────────────────────────
    keys_parser = sub.add_parser(
        "ai-keys",
        help="Manage encrypted LLM provider API keys (save/list/remove/active/show)",
    )
    keys_parser.add_argument(
        "action",
        choices=["save", "list", "remove", "active", "show"],
        help="Key management action",
    )
    keys_parser.add_argument(
        "--name", "-n",
        help="Provider name (required for save/remove/active/show)",
    )
    keys_parser.add_argument(
        "--base-url", "-u",
        help="OpenAI-compatible base URL (required for save)",
    )
    keys_parser.add_argument(
        "--api-key", "-k",
        help="API key / token (required for save; use - to read from stdin)",
    )
    keys_parser.add_argument(
        "--model", "-m",
        help="Default model for this provider (required for save)",
    )
    keys_parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output as JSON",
    )
    reg.register("ai-keys", _handle_keys)


# ── handlers ─────────────────────────────────────────────────────────

def _handle_ask(args):
    """Run the agent with a single prompt."""
    _require_ai()
    try:
        response = asyncio.run(_run_agent(
            args.prompt, args.model, getattr(args, "verbose", False),
        ))
        if getattr(args, "json_output", False):
            print(json.dumps({"response": response}))
        elif response:
            print(response)
        else:
            print("No response received.", file=sys.stderr)
            return 1
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _handle_interactive(args):
    """Run interactive REPL session."""
    _require_ai()
    try:
        asyncio.run(_run_interactive(args.model, getattr(args, "verbose", False)))
        return 0
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _handle_tui(args):
    """Launch the Textual TUI."""
    _require_ai()
    try:
        from codeupipe.ai.tui.app import CopilotApp
    except ImportError:
        print(
            "Error: TUI dependencies not installed.\n"
            "Install with: pip install codeupipe[ai-tui]",
            file=sys.stderr,
        )
        return 1
    try:
        app = CopilotApp(model=args.model, verbose=getattr(args, "verbose", False))
        app.run()
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _handle_discover(args):
    """Discover capabilities matching an intent."""
    _require_ai()
    try:
        asyncio.run(_discover_capabilities(
            args.intent,
            getattr(args, "verbose", False),
            getattr(args, "json_output", False),
        ))
        return 0
    except ImportError:
        print(
            "Error: Discovery dependencies not installed.\n"
            "Install with: pip install codeupipe[ai-discovery]",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _handle_sync(args):
    """Sync local file-based capabilities."""
    _require_ai()
    try:
        asyncio.run(_sync_local_sources(getattr(args, "verbose", False)))
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _handle_register(args):
    """Register capabilities from an MCP server."""
    _require_ai()
    url = getattr(args, "server_url", None)
    command = getattr(args, "server_command", None)
    if not url and not command:
        print("Error: Either --server-url or --server-command is required.", file=sys.stderr)
        return 1
    try:
        asyncio.run(_register_server(
            args.server_name,
            url,
            command,
            getattr(args, "server_args", None),
            getattr(args, "verbose", False),
        ))
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _handle_hub(args):
    """Show the default hub server registry."""
    _require_ai()
    try:
        from codeupipe.ai.hub.server import create_default_hub

        hub = create_default_hub()
        servers = hub.list_servers() if hasattr(hub, "list_servers") else []
        if getattr(args, "json_output", False):
            print(json.dumps({"servers": [str(s) for s in servers]}))
        else:
            if not servers:
                print("No servers registered in the default hub.")
            else:
                print(f"Hub — {len(servers)} server(s):")
                for s in servers:
                    print(f"  • {s}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _handle_hub_manage(args):
    """Manage MCP servers in the hub."""
    _require_ai()
    action = args.action
    name = getattr(args, "name", None)
    json_out = getattr(args, "json_output", False)

    from codeupipe.ai.hub.server import create_default_hub
    from codeupipe.ai.servers.mcp_manager import (
        add_server,
        disable_server,
        discover_tools,
        enable_server,
        get_server_config,
        list_servers,
        remove_server,
        server_status,
    )

    try:
        hub = create_default_hub()

        if action == "list":
            result = list_servers(hub)
        elif action in ("add", "remove", "enable", "disable", "status", "tools", "config"):
            if not name:
                print(f"Error: --name is required for '{action}'", file=sys.stderr)
                return 1
            if action == "add":
                cmd = getattr(args, "server_command", None)
                if not cmd:
                    print("Error: --command is required for 'add'", file=sys.stderr)
                    return 1
                raw_args = getattr(args, "server_args", None)
                parsed_args = raw_args.split() if raw_args else []
                raw_env = getattr(args, "env", None)
                parsed_env: dict[str, str] = {}
                if raw_env:
                    for pair in raw_env.split(","):
                        pair = pair.strip()
                        if "=" in pair:
                            k, v = pair.split("=", 1)
                            parsed_env[k.strip()] = v.strip()
                raw_tools = getattr(args, "tools", None)
                parsed_tools = [t.strip() for t in raw_tools.split(",") if t.strip()] if raw_tools else None
                result = add_server(
                    hub, name=name, command=cmd,
                    args=parsed_args, env=parsed_env, tools=parsed_tools,
                )
            elif action == "remove":
                result = remove_server(hub, name=name)
            elif action == "enable":
                result = enable_server(hub, name=name)
            elif action == "disable":
                result = disable_server(hub, name=name)
            elif action == "status":
                result = server_status(hub, name=name)
            elif action == "tools":
                result = discover_tools(hub, name=name)
            elif action == "config":
                result = get_server_config(hub, name=name)
            else:
                result = {"error": f"Unknown action: {action}"}
        else:
            result = {"error": f"Unknown action: {action}"}

        if json_out:
            print(json.dumps(result, indent=2))
        else:
            _print_manage_result(action, result)
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _print_manage_result(action: str, result: dict) -> None:
    """Pretty-print a management result."""
    if action == "list":
        servers = result.get("servers", [])
        if not servers:
            print("No servers docked.")
        else:
            print(f"Hub — {result['count']} server(s):")
            for s in servers:
                print(f"  • {s}")
    elif action == "add":
        verb = "Replaced" if result.get("replaced") else "Added"
        print(f"{verb} server '{result['name']}' ({result['command']})")
    elif action == "remove":
        if result.get("removed"):
            print(f"Removed server '{result['name']}'")
        else:
            print(f"Server '{result['name']}' not found.")
    elif action in ("enable", "disable"):
        ok = result.get("enabled" if action == "enable" else "disabled", False)
        if ok:
            print(f"{'Enabled' if action == 'enable' else 'Disabled'} server '{result['name']}'")
        else:
            print(f"Server '{result['name']}' not found.")
    elif action == "status":
        if not result.get("found"):
            print(f"Server '{result['name']}' not found.")
        else:
            disabled = " (disabled)" if result.get("disabled") else ""
            tools = result.get("tools", [])
            print(f"Server: {result['name']}{disabled}")
            print(f"  Command: {result['command']} {' '.join(result.get('args', []))}")
            print(f"  Tools:   {len(tools)} — {', '.join(tools) if tools else '(none)'}")
    elif action == "tools":
        if not result.get("found"):
            print(f"Server '{result['name']}' not found.")
        else:
            tools = result.get("tools", [])
            if not tools:
                print(f"Server '{result['name']}' has no mapped tools.")
            else:
                print(f"Server '{result['name']}' — {len(tools)} tool(s):")
                for t in tools:
                    print(f"  • {t}")
    elif action == "config":
        if not result.get("found"):
            print(f"Server '{result.get('name', '?')}' not found.")
        else:
            cfg = result["config"]
            print(f"Server: {cfg['name']}")
            print(f"  Command:  {cfg['command']}")
            print(f"  Args:     {cfg['args']}")
            print(f"  Env:      {cfg['env'] or '(none)'}")
            print(f"  CWD:      {cfg['cwd'] or '(inherit)'}")
            print(f"  Tools:    {cfg['tools']}")
            print(f"  Timeout:  {cfg['timeout']}ms")


def _handle_keys(args):
    """Manage encrypted LLM provider API keys."""
    action = args.action
    name = getattr(args, "name", None)
    json_out = getattr(args, "json_output", False)

    from codeupipe.ai.providers.api_key_store import ApiKeyStore
    from codeupipe.ai.servers.api_keys import (
        get_active_provider,
        get_provider_details,
        list_api_keys,
        remove_api_key,
        save_api_key,
        set_active_provider,
    )

    try:
        store = ApiKeyStore()

        if action == "save":
            if not name:
                print("Error: --name is required for 'save'", file=sys.stderr)
                return 1
            base_url = getattr(args, "base_url", None)
            api_key = getattr(args, "api_key", None)
            model = getattr(args, "model", None)
            if not base_url or not model:
                print("Error: --base-url and --model are required for 'save'", file=sys.stderr)
                return 1
            # Support reading key from stdin with --api-key -
            if api_key == "-":
                api_key = sys.stdin.readline().strip()
            elif not api_key:
                print("Error: --api-key is required for 'save'", file=sys.stderr)
                return 1
            result = save_api_key(
                store, name=name, base_url=base_url,
                api_key=api_key, model=model,
            )
        elif action == "list":
            result = list_api_keys(store)
        elif action == "remove":
            if not name:
                print("Error: --name is required for 'remove'", file=sys.stderr)
                return 1
            result = remove_api_key(store, name=name)
        elif action == "active":
            if name:
                result = set_active_provider(store, name=name)
            else:
                result = get_active_provider(store)
        elif action == "show":
            if not name:
                print("Error: --name is required for 'show'", file=sys.stderr)
                return 1
            result = get_provider_details(store, name=name)
        else:
            result = {"error": f"Unknown action: {action}"}

        if json_out:
            print(json.dumps(result, indent=2))
        else:
            _print_keys_result(action, result, name)
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _print_keys_result(action: str, result: dict, name: "Optional[str]") -> None:
    """Pretty-print a key management result."""
    if action == "save":
        verb = "Updated" if result.get("replaced") else "Saved"
        print(f"{verb} API key for '{result['name']}'")
    elif action == "list":
        keys = result.get("keys", [])
        active = result.get("active")
        if not keys:
            print("No API keys saved. Use 'cup ai-keys save' to add one.")
        else:
            print(f"API keys — {result['count']} provider(s):")
            for k in keys:
                marker = " (active)" if k == active else ""
                print(f"  • {k}{marker}")
    elif action == "remove":
        if result.get("removed"):
            print(f"Removed API key for '{result['name']}'")
        else:
            print(f"Provider '{result['name']}' not found.")
    elif action == "active":
        if "ok" in result:
            # set_active response
            if result["ok"]:
                print(f"Active provider set to '{result['active']}'")
            else:
                print(f"Error: {result['error']}", file=sys.stderr)
        else:
            # get_active response
            provider = result.get("provider")
            if provider:
                print(f"Active: {provider['name']}")
                print(f"  URL:   {provider['base_url']}")
                print(f"  Model: {provider['model']}")
                print(f"  Key:   {provider['api_key']}")
            else:
                active = result.get("active")
                if active:
                    print(f"Active provider '{active}' not found in store.")
                else:
                    print("No active provider set.")
    elif action == "show":
        if not result.get("found"):
            print(f"Provider '{name}' not found.")
        else:
            p = result["provider"]
            print(f"Provider: {p['name']}")
            print(f"  URL:   {p['base_url']}")
            print(f"  Model: {p['model']}")
            print(f"  Key:   {p['api_key']}")
            if p.get("extras"):
                print(f"  Extra: {json.dumps(p['extras'])}")


# ── async helpers ────────────────────────────────────────────────────

async def _run_agent(prompt: str, model: str, verbose: bool = False):
    """Run the agent with a single prompt and return the response."""
    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    from codeupipe import Payload
    from codeupipe.ai.hooks.logging_hook import LoggingMiddleware
    from codeupipe.ai.hooks.timing_hook import TimingMiddleware
    from codeupipe.ai.hub.server import create_default_hub
    from codeupipe.ai.pipelines.agent_session import build_agent_session_chain

    registry = create_default_hub()
    chain = build_agent_session_chain()
    if verbose:
        chain.use_hook(LoggingMiddleware())
        chain.use_hook(TimingMiddleware())

    ctx_data = {
        "registry": registry,
        "model": model,
        "prompt": prompt,
    }

    try:
        from codeupipe.ai.config import get_settings
        from codeupipe.ai.discovery.registry import CapabilityRegistry

        settings = get_settings()
        cap_registry = CapabilityRegistry(settings.registry_path)
        ctx_data["capability_registry"] = cap_registry
    except ImportError:
        pass  # Discovery extras not installed

    ctx = Payload(ctx_data)
    result = await chain.run(ctx)
    return result.get("response")


async def _run_interactive(model: str, verbose: bool = False):
    """Run interactive REPL session with persistent context."""
    from codeupipe.ai.agent import Agent, AgentConfig, EventType

    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    agent = Agent(config=AgentConfig(
        model=model,
        max_iterations=20,
        verbose=verbose,
    ))

    print(f"\n🤖 Copilot Agent ({model}) — Interactive Mode")
    print("   Type 'exit', 'quit', or Ctrl+C to exit")
    print("   Type 'help' for available commands\n")

    conversation_history: List[dict] = []

    while True:
        try:
            prompt = input("\n\033[1;36mYou:\033[0m ").strip()
            if not prompt:
                continue
            if prompt.lower() in ("exit", "quit", "q"):
                print("\n👋 Goodbye!\n")
                break
            if prompt.lower() == "help":
                print(
                    "\n\033[1mAvailable commands:\033[0m\n"
                    "  exit, quit, q    - Exit interactive mode\n"
                    "  help             - Show this help message\n"
                    "  clear            - Clear conversation history\n"
                    "  history          - Show conversation history\n"
                    "  usage            - Show cumulative billing usage\n"
                    "\n\033[1mJust type naturally to chat with the agent.\033[0m"
                )
                continue
            if prompt.lower() == "clear":
                conversation_history = []
                print("\n✓ Conversation history cleared\n")
                continue
            if prompt.lower() == "history":
                if not conversation_history:
                    print("\n(No conversation history yet)\n")
                else:
                    print("\n\033[1mConversation History:\033[0m")
                    for i, turn in enumerate(conversation_history, 1):
                        print(f"\n--- Turn {i} ---")
                        _u = turn["user"]
                        _a = turn["agent"]
                        print(f"You: {_u[:100]}..." if len(_u) > 100 else f"You: {_u}")
                        print(f"Agent: {_a[:100]}..." if len(_a) > 100 else f"Agent: {_a}")
                    print()
                continue
            if prompt.lower() == "usage":
                usage = agent.usage
                print(f"\n\033[1mCumulative Usage:\033[0m")
                print(f"  Total requests: {usage.get('total_requests', 0)}")
                print(f"  Total tokens: {usage.get('total_tokens', 0)}")
                print()
                continue

            # Run agent and stream response
            print("\n\033[1;32mAgent:\033[0m ", end="", flush=True)
            response_parts: List[str] = []
            turn_count = 0

            async for event in agent.run(prompt):
                if event.type == EventType.TURN_START:
                    turn_count = event.data.get("iteration", turn_count)
                    if verbose:
                        print(f"\n  [Turn {turn_count}]", end=" ", flush=True)
                elif event.type == EventType.TOOL_CALL:
                    if verbose:
                        tool_name = event.data.get("name", "unknown")
                        print(f"\n  🔧 {tool_name}", end="", flush=True)
                elif event.type == EventType.RESPONSE:
                    content = event.data.get("content", "")
                    if content:
                        response_parts.append(content)
                        if not verbose:
                            print(content, end="", flush=True)
                elif event.type == EventType.TURN_END:
                    if verbose:
                        print(" ✓", end="", flush=True)
                elif event.type == EventType.DONE:
                    total_iters = event.data.get("total_iterations", 0)
                    if verbose:
                        print(f" ({total_iters} turns)")
                    else:
                        print()  # newline after response
                elif event.type == EventType.ERROR:
                    print(f"\n\n❌ Error: {event.data}")
                    break

            full_response = "".join(response_parts) if response_parts else "(No response)"
            conversation_history.append({
                "user": prompt,
                "agent": full_response,
                "turns": turn_count,
            })

        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!\n")
            break
        except EOFError:
            print("\n\n👋 Goodbye!\n")
            break
        except Exception as exc:
            print(f"\n\n❌ Unexpected error: {exc}")
            if verbose:
                import traceback
                traceback.print_exc()


async def _discover_capabilities(
    intent: str, verbose: bool = False, json_output: bool = False,
):
    """Discover and print capabilities matching an intent."""
    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    from codeupipe import Payload
    from codeupipe.ai.config import get_settings
    from codeupipe.ai.discovery.registry import CapabilityRegistry
    from codeupipe.ai.hooks.logging_hook import LoggingMiddleware
    from codeupipe.ai.hooks.timing_hook import TimingMiddleware
    from codeupipe.ai.pipelines.intent_discovery import build_intent_discovery_chain

    settings = get_settings()
    registry = CapabilityRegistry(settings.registry_path)
    chain = build_intent_discovery_chain()
    if verbose:
        chain.use_hook(LoggingMiddleware())
        chain.use_hook(TimingMiddleware())

    ctx = Payload({
        "intent": intent,
        "capability_registry": registry,
    })

    result = await chain.run(ctx)
    capabilities = result.get("capabilities") or []
    grouped = result.get("grouped_capabilities") or {}

    if json_output:
        print(json.dumps({
            "intent": intent,
            "count": len(capabilities),
            "grouped": {k: [c.name if hasattr(c, "name") else str(c) for c in v] for k, v in grouped.items()},
        }))
        return

    if not capabilities:
        print("No matching capabilities found.", file=sys.stderr)
        return

    print(f"Found {len(capabilities)} matching capabilities:\n")
    for type_key in ("tool", "skill", "instruction", "plan", "prompt", "resource"):
        caps_in_type = grouped.get(type_key, [])
        if not caps_in_type:
            continue
        print(f"  [{type_key.upper()}]")
        for cap in caps_in_type:
            print(f"    {cap.name}")
            if cap.description:
                print(f"      {cap.description}")
            if cap.server_name:
                print(f"      server: {cap.server_name}")
            if cap.source_path:
                print(f"      source: {cap.source_path}")
        print()


async def _sync_local_sources(verbose: bool = False):
    """Scan and sync local file-based capabilities."""
    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    from codeupipe import Payload
    from codeupipe.ai.config import get_settings
    from codeupipe.ai.discovery.registry import CapabilityRegistry
    from codeupipe.ai.hooks.logging_hook import LoggingMiddleware
    from codeupipe.ai.hooks.timing_hook import TimingMiddleware
    from codeupipe.ai.pipelines.file_registration import build_file_registration_chain

    settings = get_settings()
    registry = CapabilityRegistry(settings.registry_path)
    chain = build_file_registration_chain()
    if verbose:
        chain.use_hook(LoggingMiddleware())
        chain.use_hook(TimingMiddleware())

    ctx = Payload({"capability_registry": registry})
    result = await chain.run(ctx)
    stats = result.get("sync_stats") or {}
    registered = result.get("registered_count") or 0

    print("Sync complete:")
    print(f"  Added:      {stats.get('added', 0)}")
    print(f"  Updated:    {stats.get('updated', 0)}")
    print(f"  Unchanged:  {stats.get('unchanged', 0)}")
    print(f"  Removed:    {stats.get('removed', 0)}")
    print(f"  Registered: {registered}")


async def _register_server(
    name: str,
    url: str = None,
    command: str = None,
    server_args: list = None,
    verbose: bool = False,
):
    """Register capabilities from an MCP server."""
    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client

    from codeupipe import Payload
    from codeupipe.ai.config import get_settings
    from codeupipe.ai.discovery.registry import CapabilityRegistry
    from codeupipe.ai.pipelines.capability_registration import (
        build_capability_registration_chain,
    )

    settings = get_settings()
    registry = CapabilityRegistry(settings.registry_path)
    chain = build_capability_registration_chain()

    server_tools = []
    try:
        if url:
            async with sse_client(url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    server_tools.extend([t.model_dump() for t in result.tools])
        elif command:
            params = StdioServerParameters(command=command, args=server_args or [])
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    server_tools.extend([t.model_dump() for t in result.tools])
    except Exception as exc:
        print(f"Error connecting to server: {exc}", file=sys.stderr)
        return

    if not server_tools:
        print(f"No tools found on server '{name}'.", file=sys.stderr)
        return

    print(f"Found {len(server_tools)} tools. Registering...", file=sys.stderr)

    ctx = Payload({
        "server_name": name,
        "server_tools": server_tools,
        "capability_registry": registry,
    })
    await chain.run(ctx)
    print(f"Successfully registered server '{name}'.")

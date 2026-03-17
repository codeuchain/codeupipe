"""``cup ai`` command group — agent, discovery, hub, TUI, eval.

All AI commands require ``pip install codeupipe[ai]`` at minimum.
Discovery needs ``[ai-discovery]`` and TUI needs ``[ai-tui]``.
"""

import asyncio
import json
import logging
import sys
from typing import List


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

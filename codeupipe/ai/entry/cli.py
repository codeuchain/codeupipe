"""Entry point functions for AI CLI subcommands.

Provides async functions that the ``cup ai-*`` CLI handlers
delegate to.  Each function accepts a small set of typed
arguments so that tests can call them directly without going
through argparse.
"""

from __future__ import annotations

import sys


async def discover_capabilities(
    query: str,
    verbose: bool = False,
    top_k: int = 5,
) -> None:
    """Search the capability registry for capabilities matching *query*.

    Prints matching capabilities to stdout.  If nothing is found,
    writes a "no matching capabilities" message to stderr.

    Args:
        query: Natural-language intent to search for.
        verbose: If True, include extra detail (embeddings, scores).
        top_k: Maximum number of results to return.
    """
    from codeupipe.ai.config import get_settings
    import codeupipe.ai.discovery.registry as _reg_mod

    settings = get_settings()
    registry = _reg_mod.CapabilityRegistry(settings.registry_path)

    try:
        # Try text search first (no torch required)
        results = registry.text_search(query, limit=top_k)
    except Exception as exc:  # noqa: BLE001
        if verbose:
            print(f"Discovery error: {exc}", file=sys.stderr)
        results = []

    if not results:
        print(f"No matching capabilities found for: {query!r}", file=sys.stderr)
        return

    count = len(results)
    print(f"Found {count} matching capabilities for {query!r}:")
    for cap in results:
        name = getattr(cap, "name", str(cap))
        desc = getattr(cap, "description", "")
        if verbose and desc:
            print(f"  • {name}: {desc}")
        else:
            print(f"  • {name}")

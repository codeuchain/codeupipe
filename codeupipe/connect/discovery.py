"""
Connector discovery via Python entry points.

External connector packages register under the ``codeupipe.connectors``
entry point group.  This module discovers them at runtime, calls their
``register()`` function with the project's Registry and config, and
provides health-check orchestration.
"""

import asyncio
import importlib.metadata
import inspect
from typing import Any, Callable, Dict, List, Optional, Tuple

from .config import ConnectorConfig

__all__ = ["discover_connectors", "check_health"]

_ENTRY_POINT_GROUP = "codeupipe.connectors"


def discover_connectors(
    configs: List[ConnectorConfig],
    registry: Any,
) -> Dict[str, List[str]]:
    """Discover and register connector filters from installed packages.

    For each ConnectorConfig whose ``provider`` matches an entry point
    name (or the built-in ``"http"``), calls the entry point's
    ``register(registry, config)`` function.

    Args:
        configs: Connector configs parsed from cup.toml.
        registry: A codeupipe Registry instance.

    Returns:
        Dict mapping provider name → list of filter names registered.
    """
    # Load entry points once
    ep_map: Dict[str, Any] = {}
    try:
        eps = importlib.metadata.entry_points()
        if hasattr(eps, "select"):
            entries = eps.select(group=_ENTRY_POINT_GROUP)
        else:
            entries = eps.get(_ENTRY_POINT_GROUP, [])
        for ep in entries:
            ep_map[ep.name] = ep
    except Exception:
        pass

    registered: Dict[str, List[str]] = {}

    for cfg in configs:
        provider = cfg.provider

        if provider == "http":
            # Built-in — handled by HttpConnector; register it directly.
            from .http import HttpConnector
            connector = HttpConnector.from_config(cfg)
            name = cfg.name
            registry.register(name, lambda _cfg=cfg, _c=connector: _c, kind="connector", force=True)
            registered.setdefault(provider, []).append(name)
            continue

        ep = ep_map.get(provider)
        if ep is None:
            continue  # Provider not installed — skip silently

        try:
            register_fn = ep.load()
            before = set(registry.list())
            register_fn(registry, cfg)
            after = set(registry.list())
            new_names = sorted(after - before)
            registered.setdefault(provider, []).extend(new_names)
        except Exception:
            pass  # Skip broken connectors

    return registered


def check_health(
    registry: Any,
    names: Optional[List[str]] = None,
) -> Dict[str, bool]:
    """Run health checks on connector filters.

    Calls ``health()`` on each connector filter that has the method.
    Sync and async ``health()`` are both supported.

    Args:
        registry: A codeupipe Registry instance.
        names: Specific connector names to check.  If None, checks all
               components with ``kind="connector"``.

    Returns:
        Dict mapping connector name → healthy (True/False).
    """
    if names is None:
        names = [
            n for n in registry.list()
            if registry.info(n).get("kind") == "connector"
        ]

    results: Dict[str, bool] = {}
    for name in names:
        try:
            instance = registry.get(name)
            if not hasattr(instance, "health"):
                results[name] = True  # No health method = assumed healthy
                continue
            health_result = instance.health()
            if inspect.isawaitable(health_result):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    results[name] = True  # Can't await inside running loop; skip
                else:
                    results[name] = bool(asyncio.run(health_result))
            else:
                results[name] = bool(health_result)
        except Exception:
            results[name] = False

    return results

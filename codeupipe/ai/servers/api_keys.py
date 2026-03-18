"""API Keys MCP Server — agent-driven API key management.

An MCP server whose tools let the agent manage saved LLM provider
API keys on behalf of the user.  Keys are encrypted at rest via
``ApiKeyStore``.

Architecture:
    Pure functions (save_api_key, list_api_keys, …) do the work.
    The FastMCP ``@server.tool()`` decorators are just transport.
    Tests target the pure-function layer — zero FastMCP dependency.

Run standalone:  python -m codeupipe.ai.servers.api_keys
"""

from __future__ import annotations

import json
from typing import Any

from codeupipe.ai.providers.api_key_store import ApiKeyEntry, ApiKeyStore

__all__ = [
    "get_active_provider",
    "get_provider_details",
    "list_api_keys",
    "remove_api_key",
    "save_api_key",
    "set_active_provider",
]


# ── Helpers ───────────────────────────────────────────────────────────


def _redact_key(api_key: str) -> str:
    """Redact all but the first 4 chars of an API key."""
    if len(api_key) > 4:
        return api_key[:4] + "****"
    return "****"


def _entry_to_safe_dict(entry: ApiKeyEntry) -> dict[str, Any]:
    """Serialize an entry with the API key redacted."""
    return {
        "name": entry.name,
        "base_url": entry.base_url,
        "api_key": _redact_key(entry.api_key),
        "model": entry.model,
        "extras": entry.extras,
    }


# ── Pure functions (testable without mcp dependency) ──────────────────


def save_api_key(
    store: ApiKeyStore,
    *,
    name: str,
    base_url: str,
    api_key: str,
    model: str,
    extras: str = "",
) -> dict[str, Any]:
    """Save or update an API key in the encrypted store.

    Args:
        store: The ApiKeyStore instance.
        name: Provider identifier (e.g. "openai", "groq", "ollama").
        base_url: Base URL for the OpenAI-compatible API.
        api_key: API key / token (will be encrypted at rest).
        model: Default model to use.
        extras: JSON string of extra provider config, or empty.

    Returns:
        {"saved": True, "name": ..., "replaced": bool}
    """
    replaced = store.get(name) is not None

    parsed_extras: dict[str, Any] = {}
    if extras:
        parsed_extras = json.loads(extras)

    entry = ApiKeyEntry(
        name=name,
        base_url=base_url,
        api_key=api_key,
        model=model,
        extras=parsed_extras,
    )
    store.save(entry)

    return {"saved": True, "name": name, "replaced": replaced}


def list_api_keys(store: ApiKeyStore) -> dict[str, Any]:
    """List all stored provider names.

    Returns:
        {"keys": [...names], "count": N, "active": str|None}
    """
    keys = store.list_keys()
    active = store.get_active()
    return {"keys": keys, "count": len(keys), "active": active}


def remove_api_key(
    store: ApiKeyStore,
    *,
    name: str,
) -> dict[str, Any]:
    """Remove a provider from the encrypted store.

    Returns:
        {"removed": bool, "name": ...}
    """
    removed = store.remove(name)
    return {"removed": removed, "name": name}


def set_active_provider(
    store: ApiKeyStore,
    *,
    name: str,
) -> dict[str, Any]:
    """Set the active (default) provider.

    Returns:
        {"ok": True, "active": ...} on success,
        {"ok": False, "error": ...} if not found.
    """
    try:
        store.set_active(name)
        return {"ok": True, "active": name}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


def get_active_provider(store: ApiKeyStore) -> dict[str, Any]:
    """Get the current active provider's details.

    Returns:
        {"active": str|None, "provider": {...}|None}

    The API key is redacted in the response.
    """
    entry = store.resolve_active()
    if entry is None:
        return {"active": store.get_active(), "provider": None}

    return {
        "active": store.get_active() or entry.name,
        "provider": _entry_to_safe_dict(entry),
    }


def get_provider_details(
    store: ApiKeyStore,
    *,
    name: str,
) -> dict[str, Any]:
    """Get full (redacted) details for a specific provider.

    Returns:
        {"found": True, "provider": {...}} or {"found": False}
    """
    entry = store.get(name)
    if entry is None:
        return {"found": False, "name": name}

    return {"found": True, "provider": _entry_to_safe_dict(entry)}


# ── Module-level store (wired at startup) ─────────────────────────────

_store: ApiKeyStore | None = None


def set_store(store: ApiKeyStore) -> None:
    """Wire the global store for FastMCP tool handlers."""
    global _store
    _store = store


def _get_store() -> ApiKeyStore:
    """Get the wired store or raise."""
    if _store is None:
        raise RuntimeError(
            "API Keys server not wired — call set_store() at startup"
        )
    return _store


# ── FastMCP server (transport layer) ──────────────────────────────────


def _build_server():  # noqa: C901
    """Build and return the FastMCP server instance."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("api-keys")

    @server.tool()
    async def mcp_save_api_key(
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        extras: str = "",
    ) -> str:
        """Save or update an LLM provider API key (encrypted at rest).

        Args:
            name: Provider identifier (e.g. "openai", "groq", "ollama").
            base_url: Base URL for the OpenAI-compatible API.
            api_key: API key / token.
            model: Default model to use.
            extras: JSON string of extra config, or empty.
        """
        result = save_api_key(
            _get_store(),
            name=name,
            base_url=base_url,
            api_key=api_key,
            model=model,
            extras=extras,
        )
        return json.dumps(result, indent=2)

    @server.tool()
    async def mcp_list_api_keys() -> str:
        """List all saved LLM provider API keys."""
        result = list_api_keys(_get_store())
        return json.dumps(result, indent=2)

    @server.tool()
    async def mcp_remove_api_key(name: str) -> str:
        """Remove an LLM provider API key.

        Args:
            name: Provider name to remove.
        """
        result = remove_api_key(_get_store(), name=name)
        return json.dumps(result, indent=2)

    @server.tool()
    async def mcp_set_active_provider(name: str) -> str:
        """Set which LLM provider to use by default.

        Args:
            name: Provider name to set as active.
        """
        result = set_active_provider(_get_store(), name=name)
        return json.dumps(result, indent=2)

    @server.tool()
    async def mcp_get_active_provider() -> str:
        """Get the current active LLM provider and its configuration."""
        result = get_active_provider(_get_store())
        return json.dumps(result, indent=2)

    @server.tool()
    async def mcp_get_provider_details(name: str) -> str:
        """Get details for a specific LLM provider (API key redacted).

        Args:
            name: Provider name to inspect.
        """
        result = get_provider_details(_get_store(), name=name)
        return json.dumps(result, indent=2)

    return server


if __name__ == "__main__":
    set_store(ApiKeyStore())
    server = _build_server()
    server.run(transport="stdio")

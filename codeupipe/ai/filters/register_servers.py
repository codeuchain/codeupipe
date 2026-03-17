"""RegisterServersLink — Convert registry to mcp_servers config.

Reads the ServerRegistry from context and produces the
mcp_servers dict that the Copilot SDK session expects.

Input:  registry (ServerRegistry)
Output: mcp_servers (dict)
"""

from codeupipe import Payload

from codeupipe.ai.hub.registry import ServerRegistry


class RegisterServersLink:
    """Produce mcp_servers config from the server registry."""

    async def call(self, payload: Payload) -> Payload:
        registry = payload.get("registry")
        if not isinstance(registry, ServerRegistry):
            raise ValueError("registry (ServerRegistry) is required on context")

        mcp_servers = registry.to_mcp_configs()
        return payload.insert("mcp_servers", mcp_servers)

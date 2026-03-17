"""ScanServerLink — Introspect an MCP server for its capabilities.

Reads server metadata and creates CapabilityDefinition entries
for each tool, prompt, and resource the server exposes.

Input:  payload["server_name"] (str), payload["server_tools"] (list of dict)
Output: payload["scanned_capabilities"] (list of CapabilityDefinition)
"""

from codeupipe import Payload

from codeupipe.ai.discovery.models import CapabilityDefinition, CapabilityType


class ScanServerLink:
    """Create CapabilityDefinition entries from server tool metadata."""

    async def call(self, payload: Payload) -> Payload:
        server_name = payload.get("server_name") or None
        if not server_name:
            raise ValueError("server_name (str) is required on context")

        server_tools = payload.get("server_tools") or []

        capabilities = []
        for tool in server_tools:
            name = tool.get("name") or ""
            description = tool.get("description") or ""
            capability_type_str = tool.get("type") or "tool"

            try:
                cap_type = CapabilityType(capability_type_str)
            except ValueError:
                cap_type = CapabilityType.TOOL

            cap = CapabilityDefinition(
                name=name,
                description=description,
                capability_type=cap_type,
                server_name=server_name,
                command=tool.get("command") or "",
                args_schema=tool.get("args_schema") or {},
                metadata=tool.get("metadata") or {},
            )
            capabilities.append(cap)

        return payload.insert("scanned_capabilities", capabilities)

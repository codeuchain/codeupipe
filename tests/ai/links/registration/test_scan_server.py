"""Unit tests for ScanServerLink.

Verifies that the link correctly:
- Creates CapabilityDefinition from tool metadata
- Handles different capability types
- Raises on missing server_name
"""

import pytest
from codeupipe import Payload

from codeupipe.ai.discovery.models import CapabilityType
from codeupipe.ai.filters.registration.scan_server import ScanServerLink


@pytest.mark.asyncio
async def test_scan_creates_capabilities():
    """Should create CapabilityDefinition entries from tools."""
    link = ScanServerLink()
    ctx = Payload({
        "server_name": "math-server",
        "server_tools": [
            {"name": "add", "description": "adds numbers", "type": "tool"},
            {"name": "subtract", "description": "subtracts numbers", "type": "tool"},
        ],
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert len(caps) == 2
    assert caps[0].name == "add"
    assert caps[1].name == "subtract"


@pytest.mark.asyncio
async def test_scan_sets_server_name():
    """Each capability should have the server_name set."""
    link = ScanServerLink()
    ctx = Payload({
        "server_name": "math-server",
        "server_tools": [
            {"name": "add", "description": "adds numbers"},
        ],
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps[0].server_name == "math-server"


@pytest.mark.asyncio
async def test_scan_defaults_to_tool_type():
    """Should default to TOOL type when not specified."""
    link = ScanServerLink()
    ctx = Payload({
        "server_name": "s1",
        "server_tools": [
            {"name": "my_tool", "description": "does stuff"},
        ],
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps[0].capability_type == CapabilityType.TOOL


@pytest.mark.asyncio
async def test_scan_supports_different_types():
    """Should handle skill, prompt, resource types."""
    link = ScanServerLink()
    ctx = Payload({
        "server_name": "s1",
        "server_tools": [
            {"name": "p1", "description": "a prompt", "type": "prompt"},
            {"name": "r1", "description": "a resource", "type": "resource"},
            {"name": "s1", "description": "a skill", "type": "skill"},
        ],
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    types = {c.capability_type for c in caps}
    assert CapabilityType.PROMPT in types
    assert CapabilityType.RESOURCE in types
    assert CapabilityType.SKILL in types


@pytest.mark.asyncio
async def test_scan_handles_invalid_type():
    """Should default to TOOL for unrecognised types."""
    link = ScanServerLink()
    ctx = Payload({
        "server_name": "s1",
        "server_tools": [
            {"name": "x", "description": "unknown type", "type": "banana"},
        ],
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps[0].capability_type == CapabilityType.TOOL


@pytest.mark.asyncio
async def test_scan_empty_tools():
    """Should return empty list when no tools provided."""
    link = ScanServerLink()
    ctx = Payload({"server_name": "s1", "server_tools": []})
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps == []


@pytest.mark.asyncio
async def test_scan_missing_tools_key():
    """Should handle missing server_tools gracefully (empty list)."""
    link = ScanServerLink()
    ctx = Payload({"server_name": "s1"})
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps == []


@pytest.mark.asyncio
async def test_scan_raises_without_server_name():
    """Should raise ValueError when server_name is missing."""
    link = ScanServerLink()
    ctx = Payload({"server_tools": []})

    with pytest.raises(ValueError, match="server_name"):
        await link.call(ctx)


@pytest.mark.asyncio
async def test_scan_preserves_args_schema():
    """Should preserve args_schema on created capabilities."""
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}}
    link = ScanServerLink()
    ctx = Payload({
        "server_name": "s1",
        "server_tools": [
            {"name": "add", "description": "adds", "args_schema": schema},
        ],
    })
    result = await link.call(ctx)

    caps = result.get("scanned_capabilities")
    assert caps[0].args_schema == schema

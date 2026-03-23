"""Capability models — the universal unit of discovery.

A CapabilityDefinition represents anything discoverable:
tools, skills, prompts, or resources. They all share the
same shape so intent-based search works uniformly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from codeupipe.ai._compat import StrEnum

# Python 3.11+ has datetime.UTC; use timezone.utc for 3.9/3.10 compat
_UTC = timezone.utc


class CapabilityType(StrEnum):
    """Kind of capability registered in the hub."""

    TOOL = "tool"
    SKILL = "skill"
    PROMPT = "prompt"
    RESOURCE = "resource"
    INSTRUCTION = "instruction"
    PLAN = "plan"


@dataclass
class CapabilityDefinition:
    """One discoverable capability.

    Attributes:
        id: Database primary key (None until persisted).
        name: Unique canonical name (e.g. "echo_message").
        description: Human-readable description used for embedding.
        capability_type: What kind of capability this is.
        server_name: Which MCP server provides this capability.
        command: Execution command (for CLI-style tools).
        args_schema: JSON Schema dict describing accepted arguments.
        embedding: Raw embedding bytes (float32 BLOB, None until embedded).
        metadata: Type-specific extra data.
        created_at: Timestamp of registration.
    """

    name: str
    description: str
    capability_type: CapabilityType = CapabilityType.TOOL
    server_name: str = ""
    command: str = ""
    args_schema: dict[str, Any] = field(default_factory=dict)
    embedding: bytes | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    source_path: str = ""
    content_hash: str = ""
    id: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(_UTC))

    # ── Serialisation helpers ─────────────────────────────────────────

    def args_schema_json(self) -> str:
        """Return args_schema as a JSON string."""
        return json.dumps(self.args_schema)

    def metadata_json(self) -> str:
        """Return metadata as a JSON string."""
        return json.dumps(self.metadata)

    @staticmethod
    def args_schema_from_json(raw: str) -> dict[str, Any]:
        """Parse a JSON string into an args_schema dict."""
        if not raw:
            return {}
        return json.loads(raw)

    @staticmethod
    def metadata_from_json(raw: str) -> dict[str, Any]:
        """Parse a JSON string into a metadata dict."""
        if not raw:
            return {}
        return json.loads(raw)

    # ── Display ───────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"CapabilityDefinition(name={self.name!r}, "
            f"type={self.capability_type.value}, "
            f"server={self.server_name!r})"
        )

"""codeupipe.ai — Autonomous AI Agent Suite.

Built entirely on codeupipe primitives (Payload, Filter, Pipeline, Hook).
Requires extra dependencies: ``pip install codeupipe[ai]``

Public API::

    from codeupipe.ai import Agent, AgentConfig, AgentEvent, EventType
"""

from codeupipe.ai._check import require_ai_deps as _require_ai_deps

_require_ai_deps()

from codeupipe.ai.agent.agent import Agent
from codeupipe.ai.agent.config import AgentConfig
from codeupipe.ai.agent.events import AgentEvent, EventType

__all__ = [
    "Agent",
    "AgentConfig",
    "AgentEvent",
    "EventType",
]

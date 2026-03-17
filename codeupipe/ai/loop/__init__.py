"""Agent loop — persistent multi-turn READ → WRITE → EXECUTE cycle.

This module contains the state tracking, notification queue, and
loop orchestration that turns the single-pass session into a
persistent agent.
"""

from codeupipe.ai.loop.notifications import (
    Notification,
    NotificationPriority,
    NotificationQueue,
    NotificationSource,
)
from codeupipe.ai.loop.state import AgentState, TurnRecord

__all__ = [
    "AgentState",
    "Notification",
    "NotificationPriority",
    "NotificationQueue",
    "NotificationSource",
    "TurnRecord",
]

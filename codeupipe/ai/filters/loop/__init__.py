"""Loop Links — Links that compose the agent loop.

Each Link handles one step of the READ → MODEL → PROCESS cycle:
  InjectNotificationsLink    — Drain notification queue into context
  ReadInputLink              — Prepare the next prompt for the agent
  LanguageModelLink          — Send prompt to provider, get response (string in, string out)
  ExecuteToolCallsLink       — Execute pending tool calls via ToolExecutor
  ProcessResponseLink        — Record turn in agent state from response
  BackchannelLink            — Extract embedded notifications from tool results
  UpdateIntentLink           — Detect intent shifts from agent output
  RediscoverLink             — Re-run discovery when intent changes
  ManageStateLink            — Apply capability adopt/drop from agent decisions
  ContextAttributionLink     — Track token usage per source for observability
  ConversationRevisionLink   — Compress older turns when budget threshold crossed
  SaveCheckpointLink         — Persist session state after revision
  ResumeSessionLink          — Restore session from checkpoint (pre-loop)
  ContextPruningLink         — Remove stale context to stay within budget
  ToolContinuationLink       — Inspect tool results for follow-up signals
  CheckDoneLink              — Determine if the loop should continue
  AgentLoopLink              — Wraps a sub-chain and runs it in a loop
"""

from codeupipe.ai.filters.language_model import LanguageModelLink
from codeupipe.ai.filters.loop.agent_loop import AgentLoopLink
from codeupipe.ai.filters.loop.backchannel import BackchannelLink
from codeupipe.ai.filters.loop.check_done import CheckDoneLink
from codeupipe.ai.filters.loop.context_attribution import ContextAttributionLink
from codeupipe.ai.filters.loop.context_pruning import ContextPruningLink
from codeupipe.ai.filters.loop.conversation_revision import ConversationRevisionLink
from codeupipe.ai.filters.loop.execute_tool_calls import ExecuteToolCallsLink
from codeupipe.ai.filters.loop.inject_notifications import InjectNotificationsLink
from codeupipe.ai.filters.loop.manage_state import ManageStateLink
from codeupipe.ai.filters.loop.process_response import ProcessResponseLink
from codeupipe.ai.filters.loop.read_input import ReadInputLink
from codeupipe.ai.filters.loop.rediscover import RediscoverLink
from codeupipe.ai.filters.loop.resume_session import ResumeSessionLink
from codeupipe.ai.filters.loop.save_checkpoint import SaveCheckpointLink
from codeupipe.ai.filters.loop.tool_continuation import ToolContinuationLink
from codeupipe.ai.filters.loop.update_intent import UpdateIntentLink

__all__ = [
    "AgentLoopLink",
    "BackchannelLink",
    "CheckDoneLink",
    "ContextAttributionLink",
    "ContextPruningLink",
    "ConversationRevisionLink",
    "ExecuteToolCallsLink",
    "InjectNotificationsLink",
    "LanguageModelLink",
    "ManageStateLink",
    "ProcessResponseLink",
    "ReadInputLink",
    "RediscoverLink",
    "ResumeSessionLink",
    "SaveCheckpointLink",
    "ToolContinuationLink",
    "UpdateIntentLink",
]

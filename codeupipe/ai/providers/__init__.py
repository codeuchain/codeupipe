"""Language Model Providers — Pluggable adapters for LLM backends.

The provider abstraction decouples the agent from any specific LLM SDK.
LanguageModelLink talks to a LanguageModelProvider; the provider handles
the protocol details (HTTP, SDK, local inference, etc.).

Providers:
  LanguageModelProvider      — Protocol defining the interface
  ModelResponse              — Normalized response from any provider
  ToolCall                   — Pending tool invocation from the model
  ToolExecutor               — Protocol for local tool execution
  CopilotProvider            — Copilot SDK implementation
  OpenAICompatibleProvider   — Any OpenAI-compatible chat/completions API

Credential storage:
  ApiKeyEntry   — Data class for a saved provider configuration
  ApiKeyStore   — Encrypted persistence for API keys (~/.codeupipe/api_keys.enc)
"""

from codeupipe.ai.providers.api_key_store import ApiKeyEntry, ApiKeyStore
from codeupipe.ai.providers.base import (
    LanguageModelProvider,
    ModelResponse,
    ToolCall,
    ToolExecutor,
)
from codeupipe.ai.providers.copilot import CopilotProvider
from codeupipe.ai.providers.openai_compat import OpenAICompatibleProvider

__all__ = [
    "ApiKeyEntry",
    "ApiKeyStore",
    "CopilotProvider",
    "LanguageModelProvider",
    "ModelResponse",
    "OpenAICompatibleProvider",
    "ToolCall",
    "ToolExecutor",
]

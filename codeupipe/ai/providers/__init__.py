"""Language Model Providers — Pluggable adapters for LLM backends.

The provider abstraction decouples the agent from any specific LLM SDK.
LanguageModelLink talks to a LanguageModelProvider; the provider handles
the protocol details (HTTP, SDK, local inference, etc.).

Providers:
  LanguageModelProvider — Protocol defining the interface
  ModelResponse         — Normalized response from any provider
  CopilotProvider       — Copilot SDK implementation
"""

from codeupipe.ai.providers.base import LanguageModelProvider, ModelResponse
from codeupipe.ai.providers.copilot import CopilotProvider

__all__ = [
    "CopilotProvider",
    "LanguageModelProvider",
    "ModelResponse",
]

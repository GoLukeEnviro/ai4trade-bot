import logging

import config

from ai.providers.claude_provider import ClaudeProvider
from ai.providers.openai_provider import OpenAICompatibleProvider

log = logging.getLogger(__name__)


def create_provider(provider=None, **kwargs):
    name = (provider or config.LLM_PROVIDER or "claude").lower()
    if name == "claude":
        return ClaudeProvider(**kwargs)
    if name == "openai":
        return OpenAICompatibleProvider(**kwargs)
    raise ValueError(f"Unbekannter LLM-Provider: {name}")

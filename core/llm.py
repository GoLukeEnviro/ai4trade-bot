import logging
from typing import Protocol

import config

log = logging.getLogger(__name__)


class LLMProvider(Protocol):
    def complete(self, prompt: str, max_tokens: int = 200) -> str: ...


class ClaudeProvider:
    def __init__(self, api_key=None, model=None):
        from anthropic import Anthropic
        self._client = Anthropic(api_key=api_key or config.CLAUDE_API_KEY)
        self._model = model or config.CLAUDE_MODEL

    def complete(self, prompt, max_tokens=200):
        response = self._client.messages.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return response.content[0].text


class OpenAICompatibleProvider:
    def __init__(self, api_key=None, model=None, base_url=None):
        from openai import OpenAI
        self._client = OpenAI(
            api_key=api_key or config.LLM_API_KEY or "not-needed",
            base_url=base_url or config.LLM_BASE_URL,
        )
        self._model = model or config.LLM_MODEL

    def complete(self, prompt, max_tokens=200):
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content


def create_provider(provider=None, **kwargs):
    name = (provider or config.LLM_PROVIDER or "claude").lower()
    if name == "claude":
        return ClaudeProvider(**kwargs)
    if name == "openai":
        return OpenAICompatibleProvider(**kwargs)
    raise ValueError(f"Unbekannter LLM-Provider: {name}")

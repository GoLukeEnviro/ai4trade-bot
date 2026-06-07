# Backward-compatible re-exports — Logik lebt in ai/providers/
import sys

import config as _original_config


class _ConfigProxy:
    """Leitet alle Attribut-Zugriffe an core.llm.config weiter.
    So greifen Patches auf core.llm.config auch in den Provider-Modulen.
    """
    def __getattr__(self, name):
        return getattr(sys.modules[__name__].__dict__["config"], name)


config = _original_config

from ai.providers import claude_provider as _claude_mod  # noqa: E402
from ai.providers import openai_provider as _openai_mod  # noqa: E402

# Provider-Module nutzen den Proxy, damit Patches auf core.llm.config greifen.
_proxy = _ConfigProxy()
_claude_mod.config = _proxy
_openai_mod.config = _proxy

ClaudeProvider = _claude_mod.ClaudeProvider
OpenAICompatibleProvider = _openai_mod.OpenAICompatibleProvider


def create_provider(provider=None, **kwargs):
    name = (provider or config.LLM_PROVIDER or "claude").lower()
    if name == "claude":
        return ClaudeProvider(**kwargs)
    if name == "openai":
        return OpenAICompatibleProvider(**kwargs)
    raise ValueError(f"Unbekannter LLM-Provider: {name}")

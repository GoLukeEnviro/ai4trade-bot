import logging

import config as _default_config

log = logging.getLogger(__name__)

# Wird von core/llm.py bei Bedarf auf den gepatchten config-Namespace gesetzt.
# Standardmaessig das echte config-Modul.
config = _default_config


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

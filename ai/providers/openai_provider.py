import logging

import config as _default_config

log = logging.getLogger(__name__)

# Wird von core/llm.py bei Bedarf auf den gepatchten config-Namespace gesetzt.
# Standardmaessig das echte config-Modul.
config = _default_config


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

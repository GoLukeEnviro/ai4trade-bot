from typing import Protocol


class LLMProvider(Protocol):
    def complete(self, prompt: str, max_tokens: int = 200) -> str: ...

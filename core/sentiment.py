# Backward-compatible re-exports — Logik lebt in ai/sentiment
import sys

from ai.providers import create_provider as _original_create_provider

# Standardmaessig das echte create_provider. Tests patchen core.sentiment.create_provider.
create_provider = _original_create_provider

# Proxy: ai.sentiment.create_provider delegiert an core.sentiment.create_provider.
import ai.sentiment as _ai_sentiment  # noqa: E402


def _create_provider_proxy(*args, **kwargs):
    """Leitet create_provider-Aufrufe an das aktuelle core.sentiment.create_provider weiter."""
    return sys.modules[__name__].__dict__["create_provider"](*args, **kwargs)


_ai_sentiment.create_provider = _create_provider_proxy

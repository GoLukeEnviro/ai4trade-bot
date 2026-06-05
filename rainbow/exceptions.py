class RainbowError(Exception):
    """Base exception for all Rainbow errors."""


class CollectorError(RainbowError):
    """Raised when a collector fails."""

    def __init__(self, collector_name: str, message: str):
        self.collector_name = collector_name
        super().__init__(f"Collector '{collector_name}': {message}")


class ProviderError(RainbowError):
    """Raised when a market data provider fails."""

    def __init__(self, provider_name: str, message: str):
        self.provider_name = provider_name
        super().__init__(f"Provider '{provider_name}': {message}")


class ConfigValidationError(RainbowError):
    """Raised when configuration validation fails."""

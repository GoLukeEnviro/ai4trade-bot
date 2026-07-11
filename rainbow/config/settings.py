from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CollectorConfig(BaseModel):
    enabled: bool = True
    interval_seconds: int = Field(default=60, ge=10)
    assets: list[str] = Field(default_factory=lambda: ["BTC", "ETH", "SOL"])
    params: dict[str, Any] = Field(default_factory=dict)


class ScorerConfig(BaseModel):
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "technical": 0.4,
            "sentiment": 0.3,
            "social": 0.2,
            "news": 0.1,
        }
    )

    @field_validator("weights")
    @classmethod
    def weights_sum_to_one(cls, v: dict[str, float]) -> dict[str, float]:
        total = sum(v.values())
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"Scorer weights must sum to 1.0, got {total}")
        return v


class ApiConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)


class EvaluationConfig(BaseModel):
    enabled: bool = False
    model: str = "deepseek-reasoner"
    temperature: float = 0.1
    timeout_seconds: float = 5.0
    threshold: float = 0.5
    cache_ttl_seconds: int = 300

    # Ollama Cloud / DeepSeek V4 Pro provider fields
    provider: str = "ollama_cloud"
    base_url_env: str = "RAINBOW_LLM_BASE_URL"
    api_key_env: str = "RAINBOW_LLM_API_KEY"
    primary_model: str = "deepseek-v4-pro"
    fallback_model: str = "deepseek-v4-flash"
    summary_temperature: float = 0.15
    max_reviews_per_cycle: int = 10

    # Critic section
    critic_enabled: bool = False
    critic_trigger_min_priority: str = "high"
    critic_trigger_min_risk_score: float = 0.7

    def get_effective_model(self) -> str:
        """Return primary_model, falling back to the legacy model field."""
        return self.primary_model or self.model


class MarketDataConfig(BaseModel):
    bitget_base_url: str = "https://api.bitget.com"
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"
    default_interval: str = "1h"
    default_candle_limit: int = Field(default=200, ge=50, le=1000)


class RainbowSettings(BaseSettings):
    log_level: str = "INFO"
    log_format: str = "text"

    market_data: MarketDataConfig = Field(default_factory=MarketDataConfig)

    bitget_api_key: str = ""
    claude_api_key: str = ""
    llm_api_key: str = ""
    twitter_bearer_token: str = ""

    api: ApiConfig = Field(default_factory=ApiConfig)

    scorer: ScorerConfig = Field(default_factory=ScorerConfig)

    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)

    collectors: dict[str, CollectorConfig] = Field(
        default_factory=lambda: {
            "ta": CollectorConfig(enabled=True, interval_seconds=60),
        }
    )

    db_path: str = "rainbow/storage/signals.db"

    model_config = SettingsConfigDict(env_prefix="RAINBOW_", env_nested_delimiter="__")

    @classmethod
    def from_yaml(cls, path: Path) -> "RainbowSettings":
        """Load settings from YAML file, env vars take precedence."""
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)

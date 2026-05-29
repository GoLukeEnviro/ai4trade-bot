"""Tests for core.secret_provider and config integration."""
import os
from unittest.mock import MagicMock, patch

import pytest

from core.secret_provider import (
    EnvSecretProvider,
    KeyringSecretProvider,
    VaultSecretProvider,
    create_secret_provider,
)


class TestEnvSecretProvider:
    def test_returns_env_var_value(self, monkeypatch):
        monkeypatch.setenv("TEST_KEY", "test_value")
        provider = EnvSecretProvider()
        assert provider.get("TEST_KEY") == "test_value"

    def test_returns_default_for_missing_key(self):
        provider = EnvSecretProvider()
        assert provider.get("NONEXISTENT_KEY_XYZ", "fallback") == "fallback"

    def test_default_is_empty_string(self):
        provider = EnvSecretProvider()
        assert provider.get("NONEXISTENT_KEY_XYZ") == ""


class TestKeyringSecretProvider:
    def test_falls_back_to_env_on_import_error(self, monkeypatch):
        monkeypatch.setenv("FALLBACK_KEY", "env_value")
        provider = KeyringSecretProvider()
        with patch.dict("sys.modules", {"keyring": None}):
            result = provider.get("FALLBACK_KEY")
        assert result == "env_value"

    def test_falls_back_to_env_on_exception(self, monkeypatch):
        monkeypatch.setenv("ERR_KEY", "env_value")
        provider = KeyringSecretProvider()
        mock_keyring = MagicMock()
        mock_keyring.get_password.side_effect = RuntimeError("keyring broken")
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = provider.get("ERR_KEY")
        assert result == "env_value"

    def test_returns_keyring_value_when_available(self):
        provider = KeyringSecretProvider()
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = "secret_from_keyring"
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = provider.get("ANY_KEY")
        assert result == "secret_from_keyring"

    def test_returns_env_default_when_keyring_returns_none(self, monkeypatch):
        monkeypatch.setenv("MISSING_KR_KEY", "from_env")
        provider = KeyringSecretProvider()
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = None
        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = provider.get("MISSING_KR_KEY")
        assert result == "from_env"


class TestVaultSecretProvider:
    def test_falls_back_to_env_on_import_error(self, monkeypatch):
        monkeypatch.setenv("VAULT_FB_KEY", "env_value")
        provider = VaultSecretProvider()
        with patch.dict("sys.modules", {"hvac": None}):
            result = provider.get("VAULT_FB_KEY")
        assert result == "env_value"

    def test_falls_back_to_env_on_vault_exception(self, monkeypatch):
        monkeypatch.setenv("VAULT_ERR_KEY", "env_value")
        mock_hvac = MagicMock()
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.side_effect = Exception("vault down")
        mock_hvac.Client.return_value = mock_client
        provider = VaultSecretProvider()
        with patch.dict("sys.modules", {"hvac": mock_hvac}):
            result = provider.get("VAULT_ERR_KEY")
        assert result == "env_value"

    def test_returns_vault_value_when_available(self, monkeypatch):
        mock_hvac = MagicMock()
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"SECRET_KEY": "from_vault"}}
        }
        mock_hvac.Client.return_value = mock_client
        provider = VaultSecretProvider()
        with patch.dict("sys.modules", {"hvac": mock_hvac}):
            result = provider.get("SECRET_KEY")
        assert result == "from_vault"


class TestCreateSecretProvider:
    def test_default_returns_env_provider(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SECRET_BACKEND", None)
            provider = create_secret_provider()
        assert isinstance(provider, EnvSecretProvider)

    def test_env_backend_returns_env_provider(self, monkeypatch):
        monkeypatch.setenv("SECRET_BACKEND", "env")
        provider = create_secret_provider()
        assert isinstance(provider, EnvSecretProvider)

    def test_keyring_backend_returns_keyring_provider(self, monkeypatch):
        monkeypatch.setenv("SECRET_BACKEND", "keyring")
        provider = create_secret_provider()
        assert isinstance(provider, KeyringSecretProvider)

    def test_vault_backend_returns_vault_provider(self, monkeypatch):
        monkeypatch.setenv("SECRET_BACKEND", "vault")
        provider = create_secret_provider()
        assert isinstance(provider, VaultSecretProvider)

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("SECRET_BACKEND", "KEYRING")
        provider = create_secret_provider()
        assert isinstance(provider, KeyringSecretProvider)

    def test_unknown_backend_returns_env_provider(self, monkeypatch):
        monkeypatch.setenv("SECRET_BACKEND", "unknown")
        provider = create_secret_provider()
        assert isinstance(provider, EnvSecretProvider)


class TestConfigIntegration:
    """Verify config.py still loads all values correctly with EnvSecretProvider."""

    def test_config_loads_with_env_provider(self, monkeypatch):
        monkeypatch.setenv("SECRET_BACKEND", "env")
        monkeypatch.setenv("AI4TRADE_TOKEN", "test_token")
        monkeypatch.setenv("CLAUDE_API_KEY", "test_claude_key")
        monkeypatch.setenv("LLM_API_KEY", "test_llm_key")

        import importlib
        import config as cfg

        importlib.reload(cfg)

        assert cfg.AI4TRADE_TOKEN == "test_token"
        assert cfg.CLAUDE_API_KEY == "test_claude_key"
        assert cfg.LLM_API_KEY == "test_llm_key"

    def test_config_defaults_unchanged(self, monkeypatch):
        monkeypatch.setenv("SECRET_BACKEND", "env")
        for key in [
            "AI4TRADE_TOKEN", "CLAUDE_API_KEY", "LLM_API_KEY",
            "CLAUDE_MODEL", "LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL",
            "TRADING_PAIRS", "DATA_INTERVAL", "SENTIMENT_INTERVAL",
            "HEARTBEAT_INTERVAL", "MAX_POSITION_PCT", "MAX_DRAWDOWN_PCT",
            "MAX_OPEN_POSITIONS", "CONFIDENCE_THRESHOLD", "MODE",
            "LOG_LEVEL", "MAX_SIGNAL_QUEUE",
        ]:
            monkeypatch.delenv(key, raising=False)

        import importlib
        import config as cfg

        importlib.reload(cfg)

        assert cfg.CLAUDE_MODEL == "claude-sonnet-4-5-20250929"
        assert cfg.LLM_PROVIDER == "claude"
        assert cfg.DATA_INTERVAL == 60
        assert cfg.SENTIMENT_INTERVAL == 300
        assert cfg.HEARTBEAT_INTERVAL == 30
        assert cfg.MAX_POSITION_PCT == 0.10
        assert cfg.MAX_DRAWDOWN_PCT == 0.20
        assert cfg.MAX_OPEN_POSITIONS == 3
        assert cfg.CONFIDENCE_THRESHOLD == 60
        assert cfg.MODE == "dry_run"
        assert cfg.LOG_LEVEL == "INFO"
        assert cfg.MAX_SIGNAL_QUEUE == 50
        assert cfg.BITGET_BASE == "https://api.bitget.com"
        assert cfg.COINGECKO_BASE == "https://api.coingecko.com/api/v3"
        assert cfg.AI4TRADE_BASE == "https://ai4trade.ai/api"
        assert cfg.CRYPTOCOMPARE_BASE == "https://min-api.cryptocompare.com/data/v2"

    def test_config_module_import_is_clean(self):
        """config import triggers secret_provider creation without error."""
        import importlib
        import config as cfg

        importlib.reload(cfg)
        assert hasattr(cfg, "_secret_provider")

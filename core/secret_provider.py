import logging
import os
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)


class SecretProvider(ABC):
    @abstractmethod
    def get(self, key: str, default: str = "") -> str: ...


class EnvSecretProvider(SecretProvider):
    """Default provider — reads from environment variables (same as current behavior)."""

    def get(self, key: str, default: str = "") -> str:
        return os.getenv(key, default)


class KeyringSecretProvider(SecretProvider):
    """Reads from OS keyring, falls back to env."""

    def get(self, key: str, default: str = "") -> str:
        try:
            import keyring

            val = keyring.get_password("ai4trade-bot", key)
            return val if val is not None else os.getenv(key, default)
        except Exception:
            log.warning("Keyring access failed for %s, falling back to env", key)
            return os.getenv(key, default)


class VaultSecretProvider(SecretProvider):
    """Reads from HashiCorp Vault, falls back to env."""

    def __init__(self):
        self._client = None

    def _init_client(self):
        if self._client is None:
            try:
                import hvac

                self._client = hvac.Client(
                    url=os.getenv("VAULT_URL", ""),
                    token=os.getenv("VAULT_TOKEN", ""),
                )
            except Exception as e:
                log.warning("Vault init failed: %s", e)

    def get(self, key: str, default: str = "") -> str:
        self._init_client()
        if self._client:
            try:
                resp = self._client.secrets.kv.v2.read_secret_version(path="ai4trade-bot")
                return resp["data"]["data"].get(key, os.getenv(key, default))
            except Exception:
                log.warning("Vault access failed for %s", key)
        return os.getenv(key, default)


def create_secret_provider() -> SecretProvider:
    backend = os.getenv("SECRET_BACKEND", "env").lower()
    if backend == "keyring":
        return KeyringSecretProvider()
    if backend == "vault":
        return VaultSecretProvider()
    return EnvSecretProvider()

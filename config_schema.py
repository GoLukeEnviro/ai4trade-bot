from __future__ import annotations

import os
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "config.yml"


def load_yaml_config(path: str | None = None) -> dict:
    """
    YAML-Konfiguration laden. Returns leeres dict wenn:
    - Kein Pfad angegeben und keine config.yml existiert
    - yaml nicht installiert ist
    """
    config_path = path or os.getenv("CONFIG_PATH", DEFAULT_CONFIG_PATH)

    if not Path(config_path).exists():
        return {}

    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except ImportError:
        log.warning("PyYAML nicht installiert. Nutze nur .env Konfiguration.")
        return {}
    except Exception as e:
        log.warning("YAML-Config Fehler: %s", e)
        return {}


def apply_yaml_to_env(config: dict, prefix: str = "") -> None:
    """
    YAML-Config in Umgebungsvariablen setzen (nur wenn nicht bereits gesetzt).
    Dies erlaubt .env Override von YAML-Werten.
    """
    for key, value in config.items():
        env_key = f"{prefix}{key}".upper() if prefix else key.upper()
        if isinstance(value, dict):
            apply_yaml_to_env(value, prefix=f"{env_key}_")
        elif env_key not in os.environ:
            os.environ[env_key] = str(value)

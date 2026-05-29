import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from config_schema import apply_yaml_to_env, load_yaml_config


class TestLoadYamlConfig:
    def test_load_yaml_missing_file(self, tmp_path):
        result = load_yaml_config(str(tmp_path / "nonexistent.yml"))
        assert result == {}

    def test_load_yaml_valid(self, tmp_path):
        cfg = tmp_path / "config.yml"
        cfg.write_text(textwrap.dedent("""\
            mode: dry_run
            log_level: INFO
            trading:
              pairs: "BTC/USDT"
              data_interval: 60
        """), encoding="utf-8")
        result = load_yaml_config(str(cfg))
        assert result["mode"] == "dry_run"
        assert result["trading"]["pairs"] == "BTC/USDT"
        assert result["trading"]["data_interval"] == 60

    def test_load_yaml_empty_file(self, tmp_path):
        cfg = tmp_path / "config.yml"
        cfg.write_text("", encoding="utf-8")
        result = load_yaml_config(str(cfg))
        assert result == {}

    def test_load_yaml_invalid_content(self, tmp_path):
        cfg = tmp_path / "config.yml"
        cfg.write_text("- item1\n- item2\n", encoding="utf-8")
        result = load_yaml_config(str(cfg))
        assert result == {}

    def test_load_yaml_no_pyyaml(self, tmp_path):
        cfg = tmp_path / "config.yml"
        cfg.write_text("mode: dry_run\n", encoding="utf-8")
        with patch.dict("sys.modules", {"yaml": None}):
            with patch("builtins.__import__", side_effect=ImportError("no yaml")):
                result = load_yaml_config(str(cfg))
                assert result == {}


class TestApplyYamlToEnv:
    def test_apply_yaml_to_env(self):
        config = {"mode": "live", "log_level": "DEBUG"}
        keys_to_clean = ["MODE", "LOG_LEVEL"]
        for k in keys_to_clean:
            os.environ.pop(k, None)
        try:
            apply_yaml_to_env(config)
            assert os.environ["MODE"] == "live"
            assert os.environ["LOG_LEVEL"] == "DEBUG"
        finally:
            for k in keys_to_clean:
                os.environ.pop(k, None)

    def test_apply_yaml_does_not_override_existing(self):
        os.environ["MODE"] = "dry_run"
        try:
            apply_yaml_to_env({"mode": "live"})
            assert os.environ["MODE"] == "dry_run"
        finally:
            os.environ.pop("MODE")

    def test_apply_yaml_nested(self):
        keys_to_clean = ["TRADING_PAIRS", "TRADING_DATA_INTERVAL"]
        for k in keys_to_clean:
            os.environ.pop(k, None)
        try:
            apply_yaml_to_env({
                "trading": {
                    "pairs": "BTC/USDT",
                    "data_interval": 120,
                }
            })
            assert os.environ["TRADING_PAIRS"] == "BTC/USDT"
            assert os.environ["TRADING_DATA_INTERVAL"] == "120"
        finally:
            for k in keys_to_clean:
                os.environ.pop(k, None)

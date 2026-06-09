"""Tests for scripts/validate_config.py"""
import textwrap
from pathlib import Path

import pytest

from scripts.validate_config import (
    MIN_CONFIG_VERSION,
    _find_config,
    _parse_yaml_value,
    main,
)

# ---------------------------------------------------------------------------
# _parse_yaml_value
# ---------------------------------------------------------------------------

class TestParseYamlValue:
    def test_extracts_top_level_key(self, tmp_path: Path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(textwrap.dedent("""\
            # comment line
            _config_version: 30
            other_key: bar
        """))
        assert _parse_yaml_value(cfg, "_config_version") == "30"

    def test_returns_none_for_missing_key(self, tmp_path: Path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("other_key: bar\n")
        assert _parse_yaml_value(cfg, "_config_version") is None

    def test_ignores_nested_keys(self, tmp_path: Path):
        cfg = tmp_path / "config.yaml"
        # "  nested: val" should not be treated as a top-level key
        cfg.write_text(textwrap.dedent("""\
            top: 1
              _config_version: 99
        """))
        # The indented line has leading spaces, so it won't match as top-level
        assert _parse_yaml_value(cfg, "_config_version") is None

    def test_strips_quotes(self, tmp_path: Path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text('_config_version: "28"\n')
        assert _parse_yaml_value(cfg, "_config_version") == "28"


# ---------------------------------------------------------------------------
# _find_config
# ---------------------------------------------------------------------------

class TestFindConfig:
    def test_finds_existing_file(self, tmp_path: Path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("dummy: true\n")
        monkeypatch.chdir(tmp_path)
        result = _find_config()
        assert result is not None and result.resolve() == cfg.resolve()

    def test_returns_none_when_nothing_exists(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert _find_config() is None


# ---------------------------------------------------------------------------
# main (integration-style)
# ---------------------------------------------------------------------------

class TestMain:
    def test_version_check_passes(self, tmp_path: Path, monkeypatch):
        """Config with version >= MIN_CONFIG_VERSION exits 0."""
        cfg = tmp_path / "config.yaml"
        cfg.write_text(f"_config_version: {MIN_CONFIG_VERSION}\n")
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    def test_version_check_fails_low_version(self, tmp_path: Path, monkeypatch):
        """Config with version < MIN_CONFIG_VERSION exits 1."""
        cfg = tmp_path / "config.yaml"
        cfg.write_text("_config_version: 1\n")
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    def test_missing_config_handled(self, tmp_path: Path, monkeypatch):
        """No config file at all exits 1 (not a crash)."""
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

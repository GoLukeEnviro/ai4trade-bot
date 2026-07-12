"""
Tests for factory-mode logging in rainbow/main.py.
Phase B: ensure create_app() initializes logging without duplicate handlers.
"""

import logging
import os
from unittest.mock import patch

import pytest

from rainbow.main import setup_logging


@pytest.fixture(autouse=True)
def _reset_rainbow_logger():
    """Reset the rainbow logger before each test to ensure clean state."""
    logger = logging.getLogger("rainbow")
    logger.handlers.clear()
    logger.setLevel(logging.NOTSET)
    yield
    logger.handlers.clear()
    logger.setLevel(logging.NOTSET)


class TestSetupLogging:
    def test_initializes_handler(self):
        """setup_logging() adds a handler when none exist."""
        logger = logging.getLogger("rainbow")
        assert logger.handlers == []

        setup_logging(level="INFO", fmt="text")
        assert len(logger.handlers) == 1

    def test_no_duplicate_handlers(self):
        """Calling setup_logging() twice does not add duplicate handlers."""
        setup_logging(level="INFO", fmt="text")
        assert len(logging.getLogger("rainbow").handlers) == 1

        setup_logging(level="DEBUG", fmt="json")
        assert len(logging.getLogger("rainbow").handlers) == 1

    def test_level_set_correctly(self):
        """setup_logging() respects the level parameter."""
        setup_logging(level="DEBUG", fmt="text")
        assert logging.getLogger("rainbow").level == logging.DEBUG

    def test_handler_is_stream_handler(self):
        """setup_logging() adds a StreamHandler to stdout."""
        setup_logging(level="INFO", fmt="text")
        logger = logging.getLogger("rainbow")
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)

    def test_main_path_still_works_after_factory(self):
        """setup_logging() twice (main() after create_app() pattern) is safe."""
        setup_logging(level="INFO", fmt="text")
        assert len(logging.getLogger("rainbow").handlers) == 1

        # Second call (duplicate guard prevents stacking)
        setup_logging(level="DEBUG", fmt="json")
        assert len(logging.getLogger("rainbow").handlers) == 1


class TestCreateAppLogging:
    @pytest.fixture(autouse=True)
    def _setup_config(self, tmp_path):
        """Create a minimal rainbow/config.yaml in a temp dir and chdir there."""
        config_dir = tmp_path / "rainbow"
        config_dir.mkdir()
        config_path = config_dir / "config.yaml"
        config_path.write_text("""
log_level: DEBUG
log_format: text
api:
  host: "127.0.0.1"
  port: 8000
db_path: ":memory:"
collectors: {}
market_data:
  bitget_base_url: "https://api.bitget.com"
scorer:
  weights:
    technical: 0.5
    sentiment: 0.3
    social: 0.1
    news: 0.1
""")
        cwd = os.getcwd()
        os.chdir(tmp_path)
        yield
        os.chdir(cwd)

    def test_factory_initializes_logging(self):
        """create_app() initializes the rainbow logger via setup_logging()."""
        logger = logging.getLogger("rainbow")
        logger.handlers.clear()

        from rainbow.main import create_app

        with patch("rainbow.main.create_engine", return_value="fastapi-app"):
            result = create_app()

        assert result == "fastapi-app"
        assert len(logger.handlers) >= 1
        assert logger.level == logging.DEBUG

    def test_repeated_factory_no_duplicates(self):
        """Repeated calls to create_app() do not stack handlers."""
        logger = logging.getLogger("rainbow")
        logger.handlers.clear()

        from rainbow.main import create_app

        with patch("rainbow.main.create_engine", return_value="fastapi-app"):
            create_app()
        assert len(logger.handlers) == 1

        with patch("rainbow.main.create_engine", return_value="fastapi-app"):
            create_app()
        assert len(logger.handlers) == 1


class TestFactoryRespectsConfigEnvVar:
    """RAINBOW_CONFIG must override the hardcoded default config path."""

    def test_factory_uses_rainbow_config_env_var(self, tmp_path, monkeypatch):
        """create_app() loads settings from the path given by RAINBOW_CONFIG,
        not from the hardcoded 'rainbow/config.yaml'."""
        custom_config = tmp_path / "custom-location.yaml"
        custom_config.write_text("""
log_level: DEBUG
log_format: text
api:
  host: "127.0.0.1"
  port: 9123
db_path: ":memory:"
collectors: {}
market_data:
  bitget_base_url: "https://api.bitget.com"
scorer:
  weights:
    technical: 0.5
    sentiment: 0.3
    social: 0.1
    news: 0.1
""")
        monkeypatch.setenv("RAINBOW_CONFIG", str(custom_config))

        logger = logging.getLogger("rainbow")
        logger.handlers.clear()

        from rainbow.main import create_app

        captured_settings = {}

        def _fake_create_engine(settings):
            captured_settings["settings"] = settings
            return "fastapi-app"

        with patch("rainbow.main.create_engine", side_effect=_fake_create_engine):
            result = create_app()

        assert result == "fastapi-app"
        assert captured_settings["settings"].api.port == 9123

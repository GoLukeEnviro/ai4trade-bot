"""Tests for rainbow.exceptions — custom exception hierarchy."""

import pytest

from rainbow.exceptions import CollectorError, ConfigValidationError, ProviderError, RainbowError


class TestRainbowError:
    def test_base_exception(self) -> None:
        exc = RainbowError("base error")
        assert str(exc) == "base error"
        assert isinstance(exc, Exception)

    def test_inherits_from_exception(self) -> None:
        assert issubclass(RainbowError, Exception)


class TestCollectorError:
    def test_construction(self) -> None:
        exc = CollectorError("ta", "network timeout")
        assert exc.collector_name == "ta"
        assert "ta" in str(exc)
        assert "network timeout" in str(exc)

    def test_inherits_from_rainbow_error(self) -> None:
        exc = CollectorError("news", "failed")
        assert isinstance(exc, RainbowError)

    def test_inherits_from_exception(self) -> None:
        assert issubclass(CollectorError, Exception)

    def test_can_be_caught_as_rainbow_error(self) -> None:
        with pytest.raises(RainbowError):
            raise CollectorError("test", "error")

    def test_collector_name_attribute(self) -> None:
        exc = CollectorError("twitter", "rate limit")
        assert exc.collector_name == "twitter"


class TestProviderError:
    def test_construction(self) -> None:
        exc = ProviderError("coingecko", "HTTP 500")
        assert exc.provider_name == "coingecko"
        assert "coingecko" in str(exc)
        assert "HTTP 500" in str(exc)

    def test_inherits_from_rainbow_error(self) -> None:
        exc = ProviderError("binance", "timeout")
        assert isinstance(exc, RainbowError)

    def test_can_be_caught_as_rainbow_error(self) -> None:
        with pytest.raises(RainbowError):
            raise ProviderError("test", "error")

    def test_provider_name_attribute(self) -> None:
        exc = ProviderError("coingecko", "rate limit")
        assert exc.provider_name == "coingecko"


class TestConfigValidationError:
    def test_construction(self) -> None:
        exc = ConfigValidationError("invalid config")
        assert "invalid config" in str(exc)

    def test_inherits_from_rainbow_error(self) -> None:
        assert issubclass(ConfigValidationError, RainbowError)

    def test_can_be_caught_as_rainbow_error(self) -> None:
        with pytest.raises(RainbowError):
            raise ConfigValidationError("bad config")


class TestExceptionHierarchy:
    def test_collector_and_provider_distinct(self) -> None:
        exc1 = CollectorError("a", "x")
        exc2 = ProviderError("b", "y")
        assert type(exc1) is not type(exc2)

    def test_all_inherit_from_rainbow_error(self) -> None:
        assert issubclass(CollectorError, RainbowError)
        assert issubclass(ProviderError, RainbowError)
        assert issubclass(ConfigValidationError, RainbowError)

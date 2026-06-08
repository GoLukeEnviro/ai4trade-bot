# tests/core/test_signal_adapter.py
"""Tests for core.signal_adapter.SignalAdapter — bidirectional signal conversion."""

from core.signal_adapter import SignalAdapter, _asset_to_pair
from core.signal_model import Signal


class TestLegacySignalToRainbow:
    """Test legacy Signal -> Rainbow dict conversion."""

    def test_buy_signal_conversion(self):
        signal = Signal(pair="BTC/USDT", action="BUY", confidence=80, price=50000.0, quantity=0.1)
        result = SignalAdapter.legacy_signal_to_rainbow(signal)

        assert result["source"] == "legacy_strategy"
        assert result["asset"] == "BTCUSDT"
        assert result["signal_type"] == "technical"
        assert result["direction"] == "bullish"
        assert result["strength"] == 0.8
        assert result["confidence"] == 0.8
        assert result["value"] == 50000.0

    def test_sell_signal_conversion(self):
        signal = Signal(pair="ETH/USDT", action="SELL", confidence=60, price=3000.0, quantity=1.0)
        result = SignalAdapter.legacy_signal_to_rainbow(signal)

        assert result["direction"] == "bearish"
        assert result["asset"] == "ETHUSDT"
        assert result["strength"] == 0.6

    def test_hold_signal_conversion(self):
        signal = Signal(pair="SOL/USDT", action="HOLD", confidence=0, price=100.0, quantity=0)
        result = SignalAdapter.legacy_signal_to_rainbow(signal)

        assert result["direction"] == "neutral"
        assert result["strength"] == 0.0
        assert result["confidence"] == 0.0

    def test_confidence_clamped_to_1(self):
        signal = Signal(pair="BTC/USDT", action="BUY", confidence=150, price=50000.0, quantity=0.1)
        result = SignalAdapter.legacy_signal_to_rainbow(signal)

        assert result["confidence"] == 1.0
        assert result["strength"] == 1.0

    def test_raw_data_contains_original(self):
        signal = Signal(pair="BTC/USDT", action="BUY", confidence=75, price=50000.0, quantity=0.1)
        result = SignalAdapter.legacy_signal_to_rainbow(signal)

        assert result["raw_data"]["pair"] == "BTC/USDT"
        assert result["raw_data"]["action"] == "BUY"
        assert result["raw_data"]["confidence"] == 75

    def test_metadata_contains_pair_action_quantity_mode(self):
        signal = Signal(pair="BTC/USDT", action="BUY", confidence=75, price=50000.0, quantity=0.1)
        result = SignalAdapter.legacy_signal_to_rainbow(signal)

        assert result["metadata"]["pair"] == "BTC/USDT"
        assert result["metadata"]["action"] == "BUY"
        assert result["metadata"]["quantity"] == 0.1
        assert result["metadata"]["mode"] == "dry_run"

    def test_unknown_action_defaults_to_neutral(self):
        signal = Signal(pair="BTC/USDT", action="UNKNOWN", confidence=50, price=50000.0, quantity=0.1)
        result = SignalAdapter.legacy_signal_to_rainbow(signal)

        assert result["direction"] == "neutral"


class TestRainbowDictToSignal:
    """Test Rainbow dict -> legacy Signal conversion."""

    def test_bullish_direction_to_buy(self):
        data = {"asset": "BTCUSDT", "direction": "bullish", "confidence": 0.8, "value": 50000.0}
        signal = SignalAdapter.rainbow_dict_to_signal(data)

        assert signal.action == "BUY"
        assert signal.pair == "BTC/USDT"
        assert signal.confidence == 80
        assert signal.price == 50000.0

    def test_bearish_direction_to_sell(self):
        data = {"asset": "ETHUSDT", "direction": "bearish", "confidence": 0.6, "value": 3000.0}
        signal = SignalAdapter.rainbow_dict_to_signal(data)

        assert signal.action == "SELL"
        assert signal.pair == "ETH/USDT"
        assert signal.confidence == 60

    def test_neutral_direction_to_hold(self):
        data = {"asset": "SOLUSDT", "direction": "neutral", "confidence": 0.3, "value": 100.0}
        signal = SignalAdapter.rainbow_dict_to_signal(data)

        assert signal.action == "HOLD"

    def test_confidence_float_to_int(self):
        data = {"asset": "BTCUSDT", "direction": "bullish", "confidence": 0.75, "value": 50000.0}
        signal = SignalAdapter.rainbow_dict_to_signal(data)

        assert signal.confidence == 75

    def test_confidence_clamped_to_100(self):
        data = {"asset": "BTCUSDT", "direction": "bullish", "confidence": 1.5, "value": 50000.0}
        signal = SignalAdapter.rainbow_dict_to_signal(data)

        assert signal.confidence == 100

    def test_confidence_clamped_to_0(self):
        data = {"asset": "BTCUSDT", "direction": "bullish", "confidence": -0.5, "value": 50000.0}
        signal = SignalAdapter.rainbow_dict_to_signal(data)

        assert signal.confidence == 0

    def test_default_values(self):
        data = {}
        signal = SignalAdapter.rainbow_dict_to_signal(data)

        assert signal.action == "HOLD"
        assert signal.confidence == 0
        assert signal.price == 0.0
        assert signal.quantity == 0.0

    def test_unknown_direction_defaults_to_hold(self):
        data = {"asset": "BTCUSDT", "direction": "sideways", "confidence": 0.5, "value": 50000.0}
        signal = SignalAdapter.rainbow_dict_to_signal(data)

        assert signal.action == "HOLD"


class TestAssetToPair:
    """Test asset -> pair conversion."""

    def test_usdt_pair(self):
        assert _asset_to_pair("BTCUSDT") == "BTC/USDT"

    def test_eth_pair(self):
        assert _asset_to_pair("ETHBTC") == "ETH/BTC"

    def test_busd_pair(self):
        assert _asset_to_pair("BNBBUSD") == "BNB/BUSD"

    def test_unknown_returns_as_is(self):
        assert _asset_to_pair("FOOBAR") == "FOOBAR"

    def test_usd_pair(self):
        assert _asset_to_pair("BTCUSD") == "BTC/USD"


class TestRoundTrip:
    """Test that converting legacy->rainbow->legacy preserves key fields."""

    def test_buy_round_trip(self):
        original = Signal(pair="BTC/USDT", action="BUY", confidence=80, price=50000.0, quantity=0.1)
        rainbow = SignalAdapter.legacy_signal_to_rainbow(original)
        restored = SignalAdapter.rainbow_dict_to_signal(rainbow)

        assert restored.pair == original.pair
        assert restored.action == original.action
        assert restored.confidence == original.confidence
        assert restored.price == original.price

    def test_sell_round_trip(self):
        original = Signal(pair="ETH/USDT", action="SELL", confidence=65, price=3000.0, quantity=2.0)
        rainbow = SignalAdapter.legacy_signal_to_rainbow(original)
        restored = SignalAdapter.rainbow_dict_to_signal(rainbow)

        assert restored.pair == original.pair
        assert restored.action == original.action
        assert restored.confidence == original.confidence

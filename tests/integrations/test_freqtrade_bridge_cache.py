"""Tests for FreqtradeBridge optional cache persistence.

Verifies:
  - Cache persists to JSON file when cache_file is provided
  - Cache loads from JSON file on startup
  - Corrupted file is handled gracefully (empty cache, no crash)
  - No file means empty cache (backward compatible)
  - Default cache_file=None does not persist
"""
from __future__ import annotations

import json
import os
import tempfile

from core.signals.envelope import (
    Actionability,
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    SignalClass,
    SignalDirection,
    SignalPriority,
)
from core.signals.registry import CanonicalSignalRegistry
from integrations.freqtrade_bridge import FreqtradeBridge

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_envelope(
    *,
    asset: str = "BTC/USDT",
    confidence: float = 0.85,
    risk_score: float = 0.3,
    direction: SignalDirection = SignalDirection.BULLISH,
) -> CanonicalSignalEnvelope:
    return CanonicalSignalEnvelope(
        signal_class=SignalClass.ENTRY,
        subtype="test",
        source="test",
        asset=asset,
        direction=direction,
        confidence=confidence,
        risk_score=risk_score,
        priority=SignalPriority.MEDIUM,
        reason_codes=["test"],
        data_quality=DataQuality(status=DataQualityStatus.OK),
        actionability=Actionability(can_alert=True),
    )


def _make_registry_with_signal(envelope: CanonicalSignalEnvelope) -> CanonicalSignalRegistry:
    db_path = os.path.join(tempfile.mkdtemp(), "test_signals.db")
    registry = CanonicalSignalRegistry(db_path)
    registry.append(envelope)
    return registry


class TestCachePersistsToFile:
    """Cache is persisted to JSON when cache_file is set."""

    def test_cache_written_on_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = os.path.join(tmpdir, "cache.json")
            env = _make_envelope()
            registry = _make_registry_with_signal(env)
            bridge = FreqtradeBridge(
                registry,
                cache_file=cache_file,
                cache_ttl_seconds=300.0,
                min_interval_seconds=0.0,
            )
            # Force a cache write via _cache_and_return
            result = {"action": "hold", "reason": "test"}
            bridge._cache_and_return("BTC/USDT", result)

            assert os.path.exists(cache_file)
            with open(cache_file) as fh:
                data = json.load(fh)
            assert "BTC/USDT" in data

    def test_no_persistence_when_cache_file_is_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = _make_envelope()
            registry = _make_registry_with_signal(env)
            bridge = FreqtradeBridge(
                registry,
                cache_file=None,
                cache_ttl_seconds=300.0,
                min_interval_seconds=0.0,
            )
            result = {"action": "hold", "reason": "test"}
            bridge._cache_and_return("ETH/USDT", result)

            # No JSON files should exist in tmpdir
            json_files = [f for f in os.listdir(tmpdir) if f.endswith(".json")]
            assert json_files == []


class TestCacheLoadsFromFile:
    """Cache is loaded from JSON on startup when file exists."""

    def test_load_existing_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = os.path.join(tmpdir, "cache.json")
            cached_data = {
                "BTC/USDT": {
                    "result": {"action": "long", "reason": "loaded"},
                    "time": 1000.0,
                },
            }
            with open(cache_file, "w") as fh:
                json.dump(cached_data, fh)

            env = _make_envelope()
            registry = _make_registry_with_signal(env)
            bridge = FreqtradeBridge(
                registry,
                cache_file=cache_file,
                cache_ttl_seconds=300.0,
                min_interval_seconds=0.0,
            )
            assert "BTC/USDT" in bridge._cache
            assert bridge._cache["BTC/USDT"]["result"]["action"] == "long"


class TestCorruptedFileHandled:
    """Corrupted or invalid cache file results in empty cache (no crash)."""

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = os.path.join(tmpdir, "cache.json")
            with open(cache_file, "w") as fh:
                fh.write("{bad json content!!")

            env = _make_envelope()
            registry = _make_registry_with_signal(env)
            # Should NOT raise
            bridge = FreqtradeBridge(
                registry,
                cache_file=cache_file,
                cache_ttl_seconds=300.0,
                min_interval_seconds=0.0,
            )
            assert bridge._cache == {}

    def test_non_dict_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = os.path.join(tmpdir, "cache.json")
            with open(cache_file, "w") as fh:
                json.dump([1, 2, 3], fh)

            env = _make_envelope()
            registry = _make_registry_with_signal(env)
            bridge = FreqtradeBridge(
                registry,
                cache_file=cache_file,
                cache_ttl_seconds=300.0,
                min_interval_seconds=0.0,
            )
            assert bridge._cache == {}


class TestNoFileEmptyCache:
    """When cache_file is set but the file doesn't exist, start with empty cache."""

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = os.path.join(tmpdir, "nonexistent.json")
            env = _make_envelope()
            registry = _make_registry_with_signal(env)
            bridge = FreqtradeBridge(
                registry,
                cache_file=cache_file,
                cache_ttl_seconds=300.0,
                min_interval_seconds=0.0,
            )
            assert bridge._cache == {}

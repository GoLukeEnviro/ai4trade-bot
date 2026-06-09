"""Tests for DryRunDerivativesFetcher runtime-configurable feature flag.

Verifies:
  - Default ENABLED is False (class-level)
  - Constructor can override ENABLED
  - Runtime attribute change works
"""
from __future__ import annotations

from adapters.derivatives.client import DryRunDerivativesFetcher


class TestDryRunDerivativesFetcherRuntimeFlag:
    """DryRunDerivativesFetcher.ENABLED is runtime-configurable."""

    def test_default_is_false(self):
        # Class-level default
        assert DryRunDerivativesFetcher.ENABLED is False
        # Instance without override inherits class default
        fetcher = DryRunDerivativesFetcher()
        assert fetcher.ENABLED is False

    def test_constructor_override_true(self):
        fetcher = DryRunDerivativesFetcher(enabled=True)
        assert fetcher.ENABLED is True

    def test_constructor_override_false(self):
        fetcher = DryRunDerivativesFetcher(enabled=False)
        assert fetcher.ENABLED is False

    def test_constructor_none_uses_default(self):
        fetcher = DryRunDerivativesFetcher(enabled=None)
        assert fetcher.ENABLED is False

    def test_runtime_change(self):
        fetcher = DryRunDerivativesFetcher(enabled=False)
        assert fetcher.ENABLED is False
        fetcher.ENABLED = True
        assert fetcher.ENABLED is True

    def test_instance_does_not_affect_class(self):
        fetcher = DryRunDerivativesFetcher(enabled=True)
        assert fetcher.ENABLED is True
        # Class-level default remains False
        assert DryRunDerivativesFetcher.ENABLED is False

"""Tests for rainbow.collectors.base — BaseCollector ABC."""

import pytest

from rainbow.collectors.base import BaseCollector


class TestBaseCollectorABC:
    """BaseCollector is abstract; verify it cannot be instantiated."""

    def test_cannot_instantiate_directly(self) -> None:
        """BaseCollector has abstract methods, so direct instantiation must fail."""
        with pytest.raises(TypeError, match="abstract method"):
            BaseCollector()  # type: ignore[abstract]

    def test_concrete_subclass_instantiation(self) -> None:
        """A subclass that implements both abstract methods can be instantiated."""

        class StubCollector(BaseCollector):
            @property
            def name(self) -> str:
                return "stub"

            async def collect(self) -> list:
                return []

        collector = StubCollector()
        assert collector.name == "stub"

    async def test_health_check_default(self) -> None:
        """Default health_check returns True."""

        class StubCollector(BaseCollector):
            @property
            def name(self) -> str:
                return "stub"

            async def collect(self) -> list:
                return []

        collector = StubCollector()
        assert await collector.health_check() is True

    def test_missing_collect_raises_type_error(self) -> None:
        """Subclass missing collect() should not be instantiable."""

        class IncompleteCollector(BaseCollector):
            @property
            def name(self) -> str:
                return "incomplete"

        with pytest.raises(TypeError):
            IncompleteCollector()  # type: ignore[abstract]

    def test_missing_name_raises_type_error(self) -> None:
        """Subclass missing name property should not be instantiable."""

        class IncompleteCollector(BaseCollector):
            async def collect(self) -> list:
                return []

        with pytest.raises(TypeError):
            IncompleteCollector()  # type: ignore[abstract]

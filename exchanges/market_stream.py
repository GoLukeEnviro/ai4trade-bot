from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger(__name__)


class MarketStream(Protocol):
    """Interface fuer WebSocket-basiertes Market-Data Streaming."""

    def subscribe(self, symbol: str, callback) -> None:
        """Abonniere Real-Time-Daten fuer ein Symbol."""
        ...

    def unsubscribe(self, symbol: str) -> None:
        """Abonnement beenden."""
        ...

    def close(self) -> None:
        """Verbindung schliessen."""
        ...


class NoOpMarketStream:
    """Placeholder fuer MVP. Tut nichts, loggt Debug-Meldung."""

    def subscribe(self, symbol: str, callback=None) -> None:
        log.debug("WebSocket nicht aktiv (REST-Fallback). Subscribe %s ignoriert.", symbol)

    def unsubscribe(self, symbol: str) -> None:
        pass

    def close(self) -> None:
        pass


class BitgetWebSocketStream:
    """Zukuenftige Bitget WebSocket-Implementierung. Aktuell: Stub.

    Bitget WebSocket Endpoints:
    - wss://ws.bitget.com/v2/ws/public
    - Channels: candles, ticker, depth
    """

    def __init__(self):
        raise NotImplementedError("Bitget WebSocket ist noch nicht implementiert. Nutze BitgetRestClient als Fallback.")

    def subscribe(self, symbol: str, callback=None) -> None:
        raise NotImplementedError

    def unsubscribe(self, symbol: str) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


def create_market_stream(provider: str = "rest") -> MarketStream:
    """Factory fuer Market-Stream. Default: NoOp (REST-Fallback)."""
    if provider == "rest":
        return NoOpMarketStream()
    if provider == "bitget_ws":
        raise NotImplementedError("Bitget WebSocket noch nicht verfuegbar")
    raise ValueError(f"Unbekannter Stream-Provider: {provider}")

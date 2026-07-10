"""Canonical symbol mappings shared by Rainbow producers and adapters."""

_CANONICAL_SYMBOLS: dict[str, str] = {
    "BTC": "BTC/USDT:USDT",
    "ETH": "ETH/USDT:USDT",
    "SOL": "SOL/USDT:USDT",
}


def canonical_symbol_for_asset(asset: str) -> str:
    """Return the Trading-Hub canonical symbol for a configured Rainbow asset."""
    normalized = asset.strip().upper()
    try:
        return _CANONICAL_SYMBOLS[normalized]
    except KeyError as exc:
        raise ValueError(f"No canonical symbol configured for asset: {asset!r}") from exc

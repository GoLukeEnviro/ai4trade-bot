from __future__ import annotations

from execution.execution_models import OrderRequest


def validate_order_request(request: OrderRequest) -> tuple[bool, str]:
    """
    Letzte Validierung vor dem Senden.
    Checkt: positive price, positive quantity, valid action.
    """
    if request.price <= 0:
        return False, f"invalid price: {request.price}"
    if request.quantity <= 0:
        return False, f"invalid quantity: {request.quantity}"
    if request.action not in ("BUY", "SELL", "HOLD"):
        return False, f"invalid action: {request.action}"
    return True, "valid"


def sanitize_pair(pair: str) -> str:
    """Pair-Format normalisieren: BTC/USDT -> BTCUSDT."""
    return pair.replace("/", "").replace(" ", "").upper()

import logging
import time

import requests

import config

log = logging.getLogger(__name__)


class AI4TradeClient:
    def __init__(self, token: str | None = None):
        self._token = token or config.AI4TRADE_TOKEN
        self._base = config.AI4TRADE_BASE
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        })

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self._base}{path}"
        resp = self._session.request(method, url, timeout=15, **kwargs)
        if resp.status_code == 401:
            log.error("Token abgelaufen (401). Bot muss pausieren.")
            raise ConnectionError("AI4Trade 401: Token abgelaufen")
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, dict) and "success" in body and "data" in body:
            return body["data"]
        return body

    def get_me(self) -> dict:
        return self._request("GET", "/claw/agents/me")

    def publish_signal(self, market: str, action: str, symbol: str, price: float, quantity: float) -> dict:
        return self._request("POST", "/signals/realtime", json={
            "market": market,
            "action": action,
            "symbol": symbol,
            "price": price,
            "quantity": quantity,
            "executed_at": time.time(),
        })

    def get_positions(self) -> dict:
        return self._request("GET", "/positions")

    def get_feed(self) -> dict:
        return self._request("GET", "/signals/feed")

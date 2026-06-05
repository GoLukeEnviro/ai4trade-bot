from typing import Protocol

import pandas as pd


class MarketDataProvider(Protocol):
    async def get_ohlcv(self, symbol: str, interval: str = "1h", limit: int = 200) -> pd.DataFrame: ...
    async def get_price(self, symbol: str) -> float: ...

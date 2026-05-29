from typing import Protocol

import pandas as pd


class ExchangeClient(Protocol):
    def get_ohlcv(self, symbol: str, interval: str = "1h", limit: int = 200) -> pd.DataFrame: ...
    def get_price(self, symbol: str) -> float: ...

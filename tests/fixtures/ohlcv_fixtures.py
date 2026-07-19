# tests/fixtures/ohlcv_fixtures.py
import random

import pandas as pd


def make_ohlcv(n=200, base_price=50000.0, trend="up") -> pd.DataFrame:
    random.seed(42)
    data = []
    price = base_price
    for _ in range(n):
        change = random.uniform(-0.02, 0.02)
        if trend == "up":
            change += 0.001
        elif trend == "down":
            change -= 0.001
        open_ = price
        close = price * (1 + change)
        high = max(open_, close) * (1 + random.uniform(0, 0.01))
        low = min(open_, close) * (1 - random.uniform(0, 0.01))
        volume = random.uniform(100, 1000)
        data.append([open_, high, low, close, volume])
        price = close
    return pd.DataFrame(data, columns=["open", "high", "low", "close", "volume"])


def make_bitget_ohlcv_response(n=200, base_price=50000.0) -> list:
    df = make_ohlcv(n, base_price)
    result = []
    for _, row in df.iterrows():
        result.append([
            str(int(row["open"] * 1000)),
            str(row["open"]),
            str(row["high"]),
            str(row["low"]),
            str(row["close"]),
            str(row["volume"]),
            str(row["volume"] * row["close"]),
        ])
    return result

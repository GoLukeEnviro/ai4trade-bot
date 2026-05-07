import logging

import config

log = logging.getLogger(__name__)


class RiskGate:
    def __init__(self, starting_capital: float = 100000, max_position_pct: float = None,
                 max_drawdown_pct: float = None, max_positions: int = None):
        if starting_capital <= 0:
            raise ValueError("starting_capital muss positiv sein")
        self._starting_capital = starting_capital
        self._max_pos_pct = max_position_pct if max_position_pct is not None else config.MAX_POSITION_PCT
        self._max_dd_pct = max_drawdown_pct if max_drawdown_pct is not None else config.MAX_DRAWDOWN_PCT
        self._max_positions = max_positions if max_positions is not None else config.MAX_OPEN_POSITIONS

    def check(self, signal, positions: list[dict], current_capital: float) -> tuple[bool, str]:
        if signal.action == "HOLD":
            return True, "hold"

        trade_value = signal.price * signal.quantity
        if trade_value > current_capital * self._max_pos_pct:
            return False, f"position_size: {trade_value} exceeds {self._max_pos_pct * 100}% of capital"

        if len(positions) >= self._max_positions:
            return False, f"max_positions: {len(positions)}/{self._max_positions}"

        drawdown = (self._starting_capital - current_capital) / self._starting_capital
        if drawdown > self._max_dd_pct:
            return False, f"drawdown: {drawdown * 100:.1f}% exceeds {self._max_dd_pct * 100}%"

        return True, "ok"

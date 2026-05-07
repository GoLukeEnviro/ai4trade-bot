import logging

log = logging.getLogger(__name__)


class PositionState:
    def __init__(self, client=None):
        self._client = client
        self.positions: list[dict] = []

    def refresh(self):
        try:
            result = self._client.get_positions()
            self.positions = result.get("positions", [])
            log.debug(f"Positionen aktualisiert: {len(self.positions)} offen")
        except Exception as e:
            log.warning(f"Positions-Refresh fehlgeschlagen, Cache beibehalten: {e}")

    def count(self) -> int:
        return len(self.positions)

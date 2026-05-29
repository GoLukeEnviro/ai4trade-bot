import logging

from core.signal_model import Signal

import config

log = logging.getLogger(__name__)


class SignalPublisher:
    def __init__(self, client=None, max_queue: int | None = None, repository=None):
        self._client = client
        self._repository = repository
        self.queue: list[dict] = []
        self._max_queue = max_queue if max_queue is not None else config.MAX_SIGNAL_QUEUE

    def publish(self, signal: Signal) -> bool:
        try:
            if self._send(signal):
                log.info(f"Signal veröffentlicht: {signal.pair} {signal.action}")
                if self._repository is not None:
                    self._repository.save_signal(signal)
                return True
        except Exception as e:
            log.warning(f"Signal-Veröffentlichung fehlgeschlagen: {e}")
        self._enqueue(signal)
        return False

    def flush_queue(self) -> int:
        if not self.queue:
            return 0
        flushed = 0
        remaining = []
        for item in self.queue:
            signal = Signal(**item)
            if self._send(signal):
                flushed += 1
            else:
                remaining.append(item)
        self.queue = remaining
        return flushed

    def _send(self, signal: Signal) -> bool:
        symbol = signal.pair.replace("/", "")
        result = self._client.publish_signal(
            market="crypto",
            action=signal.action,
            symbol=symbol,
            price=signal.price,
            quantity=signal.quantity,
        )
        return bool(result.get("success"))

    def _enqueue(self, signal: Signal):
        entry = signal.to_dict()
        self.queue.append(entry)
        if len(self.queue) > self._max_queue:
            self.queue.pop(0)
            log.warning("Signal-Queue Überlauf, ältestes Signal verworfen")

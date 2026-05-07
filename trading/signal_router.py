# trading/signal_router.py
import logging

from core.signal_model import Signal

log = logging.getLogger(__name__)

_KNOWN_TARGETS = {"ai4trade", "log"}


class SignalRouter:
    def __init__(self, publisher=None):
        self._publisher = publisher

    def route(self, signal: Signal, targets: list[str]) -> bool:
        if signal.action == "HOLD":
            log.info("HOLD: %s — kein Publish noetig", signal.pair)
            return True

        for target in targets:
            if target not in _KNOWN_TARGETS:
                log.warning("Unbekanntes Target ignoriert: %s", target)
                continue

            if target == "ai4trade":
                success = self._publisher.publish(signal)
                if not success:
                    return False

        log.info(
            "Signal geroutet: %s %s → %s",
            signal.pair,
            signal.action,
            targets,
        )
        return True

    def flush_queue(self, timeout: int = 5) -> int:
        return self._publisher.flush_queue()

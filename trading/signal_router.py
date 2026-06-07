# trading/signal_router.py
import logging

from core.signal_model import Signal

log = logging.getLogger(__name__)

_KNOWN_TARGETS = {"ai4trade", "log", "rainbow_api"}


class SignalRouter:
    def __init__(self, publisher=None, rainbow_publisher=None):
        self._publisher = publisher
        self._rainbow_publisher = rainbow_publisher

    def route(self, signal: Signal, targets: list[str]) -> bool:
        if signal.action == "HOLD":
            log.info("HOLD: %s — kein Publish noetig", signal.pair)
            return True

        all_ok = True
        for target in targets:
            if target not in _KNOWN_TARGETS:
                log.warning("Unbekanntes Target ignoriert: %s", target)
                continue

            if target == "ai4trade":
                success = self._publisher.publish(signal)
                if not success:
                    all_ok = False

            if target == "rainbow_api":
                if self._rainbow_publisher is None:
                    log.warning("rainbow_api target: kein RainbowApiPublisher konfiguriert")
                    continue
                success = self._rainbow_publisher.publish(signal)
                if not success:
                    log.warning("rainbow_api publish fehlgeschlagen fuer %s", signal.pair)
                    # Graceful: don't block other targets

        if all_ok:
            log.info(
                "Signal geroutet: %s %s → %s",
                signal.pair,
                signal.action,
                targets,
            )
        return all_ok

    def flush_queue(self, timeout: int = 5) -> int:
        return self._publisher.flush_queue()

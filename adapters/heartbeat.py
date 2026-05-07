import logging
import threading

log = logging.getLogger(__name__)

MAX_CONSECUTIVE_POLLS = 5
CIRCUIT_BREAKER_THRESHOLD = 3


class Heartbeat:
    def __init__(
        self,
        client,
        shutdown_event: threading.Event,
        interval: int = 30,
        circuit_breaker_pause: int = 60,
        message_queue=None,
    ):
        self._client = client
        self._shutdown = shutdown_event
        self._interval = interval
        self._cb_pause = circuit_breaker_pause
        self._msg_queue = message_queue
        self._error_count = 0

    def run(self):
        consecutive_polls = 0
        while not self._shutdown.is_set():
            try:
                result = self._client._request("POST", "/claw/agents/heartbeat")
                messages = result.get("messages", [])
                has_more = result.get("has_more_messages", False)

                if self._msg_queue is not None and messages:
                    self._msg_queue.put(messages)

                self._error_count = 0

                if has_more:
                    consecutive_polls += 1
                    if consecutive_polls >= MAX_CONSECUTIVE_POLLS:
                        consecutive_polls = 0
                        self._shutdown.wait(self._interval)
                        continue
                else:
                    consecutive_polls = 0

            except Exception as e:
                self._error_count += 1
                log.error("Heartbeat-Fehler: %s", e)
                if self._error_count >= CIRCUIT_BREAKER_THRESHOLD:
                    log.warning("Circuit Breaker aktiv — %ds Pause", self._cb_pause)
                    self._shutdown.wait(self._cb_pause)
                    self._error_count = 0
                    continue

            self._shutdown.wait(self._interval)

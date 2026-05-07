import logging
import queue

log = logging.getLogger(__name__)


class TaskHandler:
    def __init__(self, message_queue: queue.Queue):
        self._queue = message_queue

    def process_pending(self) -> int:
        processed = 0
        while True:
            try:
                messages = self._queue.get_nowait()
            except queue.Empty:
                break
            if not isinstance(messages, list):
                log.warning("TaskHandler: queue item ist keine Liste, wird ignoriert")
                continue
            for msg in messages:
                if not isinstance(msg, dict):
                    log.warning("TaskHandler: Nachricht ist kein Dict, wird ignoriert")
                    continue
                msg_type = msg.get("type", "unknown")
                log.info("Task empfangen: %s", msg_type)
                processed += 1
        return processed

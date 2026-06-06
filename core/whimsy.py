from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

LEVEL_EMOJI = {
    "DEBUG": "🔍",
    "INFO": "✨",
    "WARNING": "⚡",
    "ERROR": "🔥",
    "CRITICAL": "🚨",
}

DEFAULT_TEXT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def print_whimsy_banner(title: str, tagline: str | None = None) -> None:
    lines = [
        "🌈=================================🌈",
        f"  {title}",
        f"  {tagline or 'Bereit für farbenfrohe Signale'}",
        "🌈=================================🌈",
    ]
    print("\n".join(lines))


class TextWhimsyFormatter(logging.Formatter):
    def __init__(self, fmt: str = DEFAULT_TEXT_FORMAT) -> None:
        super().__init__(fmt)

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        emoji = LEVEL_EMOJI.get(record.levelname, "")
        if emoji:
            text = f"{emoji} {text}"
        return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def create_formatter(log_format: str) -> logging.Formatter:
    if log_format.lower() == "json":
        return JsonFormatter()
    return TextWhimsyFormatter()

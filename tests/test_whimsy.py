import logging
from io import StringIO

from core.whimsy import TextWhimsyFormatter, create_formatter


def test_text_whimsy_formatter_adds_emoji() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(TextWhimsyFormatter("%(levelname)s: %(message)s"))

    logger = logging.getLogger("test_whimsy_formatter")
    logger.setLevel(logging.INFO)
    logger.handlers = [handler]
    logger.propagate = False

    logger.info("Hallo Welt")
    handler.flush()

    assert "✨ INFO: Hallo Welt" in stream.getvalue()


def test_create_formatter_json_returns_json_message() -> None:
    formatter = create_formatter("json")
    record = logging.LogRecord("test", logging.INFO, "", 0, "Hi json", (), None)
    formatted = formatter.format(record)

    assert '"message": "Hi json"' in formatted
    assert '"level": "INFO"' in formatted

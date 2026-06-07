import queue
import threading
import time
from unittest.mock import MagicMock

from adapters.heartbeat import Heartbeat


def test_heartbeat_stops_on_shutdown_event():
    shutdown = threading.Event()
    mock_client = MagicMock()
    mock_client._request.return_value = {"messages": [], "has_more_messages": False}
    hb = Heartbeat(client=mock_client, shutdown_event=shutdown, interval=1)
    t = threading.Thread(target=hb.run)
    t.start()
    time.sleep(0.5)
    shutdown.set()
    t.join(timeout=3)
    assert not t.is_alive()


def test_heartbeat_calls_client_request():
    shutdown = threading.Event()
    mock_client = MagicMock()
    mock_client._request.return_value = {"messages": [], "has_more_messages": False}
    hb = Heartbeat(client=mock_client, shutdown_event=shutdown, interval=0.1)
    t = threading.Thread(target=hb.run)
    t.start()
    time.sleep(0.4)
    shutdown.set()
    t.join(timeout=3)
    mock_client._request.assert_called_with("POST", "/claw/agents/heartbeat")
    assert mock_client._request.call_count >= 2


def test_messages_placed_into_queue():
    shutdown = threading.Event()
    mock_client = MagicMock()
    mock_client._request.return_value = {
        "messages": [{"type": "task", "id": 1}],
        "has_more_messages": False,
    }
    msg_queue = queue.Queue()
    hb = Heartbeat(client=mock_client, shutdown_event=shutdown, interval=0.1, message_queue=msg_queue)
    t = threading.Thread(target=hb.run)
    t.start()
    time.sleep(0.4)
    shutdown.set()
    t.join(timeout=3)
    assert msg_queue.qsize() >= 2
    messages = msg_queue.get_nowait()
    assert messages == [{"type": "task", "id": 1}]


def test_has_more_messages_no_infinite_loop():
    shutdown = threading.Event()
    call_count = 0

    def counting_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return {"messages": [], "has_more_messages": True}

    mock_client = MagicMock()
    mock_client._request = counting_request
    hb = Heartbeat(client=mock_client, shutdown_event=shutdown, interval=0.05)
    t = threading.Thread(target=hb.run)
    t.start()
    time.sleep(1.0)
    shutdown.set()
    t.join(timeout=3)
    assert call_count >= 5
    assert call_count < 50


def test_circuit_breaker_after_3_errors():
    shutdown = threading.Event()
    call_count = 0

    def failing_request(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise Exception("network error")

    mock_client = MagicMock()
    mock_client._request = failing_request
    hb = Heartbeat(client=mock_client, shutdown_event=shutdown, interval=0.1, circuit_breaker_pause=0.5)
    t = threading.Thread(target=hb.run)
    t.start()
    time.sleep(0.45)
    shutdown.set()
    t.join(timeout=3)
    assert call_count >= 3
    assert call_count < 10


def test_heartbeat_uses_shutdown_event_wait_not_time_sleep():
    shutdown = threading.Event()
    mock_client = MagicMock()
    mock_client._request.return_value = {"messages": [], "has_more_messages": False}

    original_wait = shutdown.wait
    wait_calls = []

    def tracking_wait(timeout):
        wait_calls.append(timeout)
        return original_wait(timeout)

    shutdown.wait = tracking_wait
    hb = Heartbeat(client=mock_client, shutdown_event=shutdown, interval=0.1)
    t = threading.Thread(target=hb.run)
    t.start()
    time.sleep(0.35)
    shutdown.set()
    t.join(timeout=3)
    assert len(wait_calls) >= 1


def test_no_message_queue_still_works():
    shutdown = threading.Event()
    mock_client = MagicMock()
    mock_client._request.return_value = {
        "messages": [{"type": "task", "id": 1}],
        "has_more_messages": False,
    }
    hb = Heartbeat(client=mock_client, shutdown_event=shutdown, interval=0.1, message_queue=None)
    t = threading.Thread(target=hb.run)
    t.start()
    time.sleep(0.3)
    shutdown.set()
    t.join(timeout=3)
    assert not t.is_alive()
    mock_client._request.assert_called()

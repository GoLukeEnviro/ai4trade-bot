
from core.events import Event, EventType, InMemoryEventBus, NoOpEventBus


def test_event_creation():
    evt = Event(
        event_type=EventType.MARKET,
        payload={"pair": "BTCUSDT", "price": 42000.0},
        correlation_id="abc-123",
    )
    assert evt.event_type is EventType.MARKET
    assert evt.payload["pair"] == "BTCUSDT"
    assert evt.correlation_id == "abc-123"
    assert evt.causation_id == ""
    assert isinstance(evt.timestamp, float)


def test_event_is_frozen():
    evt = Event(event_type=EventType.STRATEGY, payload={})
    try:
        evt.event_type = EventType.RISK
        assert False, "Event sollte immutable sein"
    except AttributeError:
        pass


def test_noop_publish_does_not_raise():
    bus = NoOpEventBus()
    bus.publish(Event(event_type=EventType.MARKET, payload={}))


def test_noop_subscribe_does_not_raise():
    bus = NoOpEventBus()
    bus.subscribe(EventType.MARKET, handler=lambda e: None)


def test_inmemory_publish_and_retrieve():
    bus = InMemoryEventBus()
    e1 = Event(event_type=EventType.MARKET, payload={"a": 1})
    e2 = Event(event_type=EventType.STRATEGY, payload={"b": 2})
    bus.publish(e1)
    bus.publish(e2)
    assert len(bus.get_events()) == 2


def test_inmemory_subscribe_handler_called():
    bus = InMemoryEventBus()
    received = []
    bus.subscribe(EventType.RISK, handler=lambda e: received.append(e))
    evt = Event(event_type=EventType.RISK, payload={"level": "high"})
    bus.publish(evt)
    assert len(received) == 1
    assert received[0] is evt


def test_inmemory_handler_not_called_for_other_type():
    bus = InMemoryEventBus()
    received = []
    bus.subscribe(EventType.RISK, handler=lambda e: received.append(e))
    bus.publish(Event(event_type=EventType.MARKET, payload={}))
    assert len(received) == 0


def test_inmemory_get_events_filtered():
    bus = InMemoryEventBus()
    bus.publish(Event(event_type=EventType.MARKET, payload={}))
    bus.publish(Event(event_type=EventType.STRATEGY, payload={}))
    bus.publish(Event(event_type=EventType.MARKET, payload={}))
    assert len(bus.get_events(EventType.MARKET)) == 2
    assert len(bus.get_events(EventType.STRATEGY)) == 1
    assert len(bus.get_events(EventType.RISK)) == 0


def test_inmemory_handler_error_does_not_crash():
    bus = InMemoryEventBus()
    bus.subscribe(EventType.EXECUTION, handler=lambda e: 1 / 0)
    bus.publish(Event(event_type=EventType.EXECUTION, payload={}))
    assert len(bus.get_events()) == 1


def test_inmemory_clear():
    bus = InMemoryEventBus()
    bus.publish(Event(event_type=EventType.AUDIT, payload={}))
    bus.publish(Event(event_type=EventType.AUDIT, payload={}))
    assert len(bus.get_events()) == 2
    bus.clear()
    assert len(bus.get_events()) == 0

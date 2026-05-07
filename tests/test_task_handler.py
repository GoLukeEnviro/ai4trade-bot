import queue

from adapters.task_handler import TaskHandler


def test_empty_queue_returns_0():
    q = queue.Queue()
    th = TaskHandler(q)
    assert th.process_pending() == 0


def test_one_queued_list_with_two_messages_returns_2():
    q = queue.Queue()
    q.put([{"type": "task", "id": 1}, {"type": "signal", "id": 2}])
    th = TaskHandler(q)
    assert th.process_pending() == 2


def test_multiple_queued_batches_are_all_processed():
    q = queue.Queue()
    q.put([{"type": "task", "id": 1}])
    q.put([{"type": "task", "id": 2}, {"type": "task", "id": 3}])
    q.put([{"type": "task", "id": 4}])
    th = TaskHandler(q)
    assert th.process_pending() == 4


def test_messages_without_type_field_handled_as_unknown():
    q = queue.Queue()
    q.put([{"id": 1}, {"type": "command", "id": 2}])
    th = TaskHandler(q)
    assert th.process_pending() == 2


def test_malformed_non_dict_entries_do_not_crash():
    q = queue.Queue()
    q.put([{"type": "task", "id": 1}, "not_a_dict", 42, None])
    th = TaskHandler(q)
    assert th.process_pending() == 1


def test_queue_is_empty_after_process_pending():
    q = queue.Queue()
    q.put([{"type": "task", "id": 1}])
    q.put([{"type": "task", "id": 2}])
    th = TaskHandler(q)
    th.process_pending()
    assert q.empty()


def test_malformed_queue_item_not_iterable_does_not_crash():
    q = queue.Queue()
    q.put("not_a_list")
    q.put([{"type": "task", "id": 1}])
    th = TaskHandler(q)
    assert th.process_pending() == 1

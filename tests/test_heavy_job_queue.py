import threading
import time

import pytest

from backend.main_api import _HeavyJobQueue


def _wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("Timed out waiting for queue state")


def test_heavy_queue_runs_jobs_fifo_one_at_a_time():
    queue = _HeavyJobQueue(max_jobs=3)
    queue.acquire("first", "ctkm")
    entered = threading.Event()

    def wait_for_second():
        queue.acquire("second", "tem_r")
        entered.set()

    thread = threading.Thread(target=wait_for_second)
    thread.start()
    _wait_until(lambda: len(queue.snapshot()["waiting"]) == 1)

    snapshot = queue.snapshot()
    assert snapshot["active"]["job_id"] == "first"
    assert snapshot["waiting"][0]["job_id"] == "second"
    assert snapshot["waiting"][0]["position"] == 1
    assert not entered.is_set()

    queue.release("first")
    assert entered.wait(1)
    assert queue.snapshot()["active"]["job_id"] == "second"
    queue.release("second")
    thread.join(timeout=1)


def test_heavy_queue_rejects_requests_beyond_capacity():
    queue = _HeavyJobQueue(max_jobs=2)
    queue.acquire("first", "ctkm")

    thread = threading.Thread(target=lambda: queue.acquire("second", "tem_r"), daemon=True)
    thread.start()
    _wait_until(lambda: len(queue.snapshot()["waiting"]) == 1)

    with pytest.raises(RuntimeError, match="Hàng đợi đang đầy"):
        queue.acquire("third", "ctkm")

    queue.release("first")
    _wait_until(lambda: (queue.snapshot()["active"] or {}).get("job_id") == "second")
    queue.release("second")
    thread.join(timeout=1)

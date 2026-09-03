import threading
import time

import pytest

from backend.runtime_contract import ReservedHeavyJobQueue


def _wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("Timed out waiting for queue state")


def test_heavy_queue_runs_reserved_jobs_fifo_one_at_a_time():
    queue = ReservedHeavyJobQueue(max_jobs=3)
    queue.reserve("first", "ctkm")
    queue.reserve("second", "tem_r")
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


def test_heavy_queue_rejects_reservation_beyond_capacity_before_worker_start():
    queue = ReservedHeavyJobQueue(max_jobs=2)
    queue.reserve("first", "ctkm")
    queue.reserve("second", "tem_r")

    with pytest.raises(RuntimeError, match="Hàng đợi đang đầy"):
        queue.reserve("third", "ctkm")

    snapshot = queue.snapshot()
    assert [entry["job_id"] for entry in snapshot["waiting"]] == ["first", "second"]


def test_heavy_queue_cancel_releases_reserved_capacity():
    queue = ReservedHeavyJobQueue(max_jobs=1)
    queue.reserve("first", "ctkm")
    with pytest.raises(RuntimeError, match="Hàng đợi đang đầy"):
        queue.reserve("second", "tem_r")

    queue.cancel("first")
    queue.reserve("second", "tem_r")
    assert queue.snapshot()["waiting"][0]["job_id"] == "second"

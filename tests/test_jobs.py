"""Exercise the watchdog against real child processes, independently of Qiskit."""
import time

import pytest

from quantum_jobs import Jobs


def wait_reaped(manager, child):
    until = time.monotonic() + 8
    while manager.active and time.monotonic() < until:
        time.sleep(0.02)
    assert manager.active is None
    assert child.poll() is not None


def test_timeout_reaps_real_worker():
    manager = Jobs(timeout=0.05)
    job_id, cached = manager.submit({})
    child = manager.active[1]
    assert not cached
    wait_reaped(manager, child)
    assert manager.read(job_id)["status"] == "timed_out"


def test_cancel_reaps_real_worker_and_rejects_concurrent_work():
    manager = Jobs()
    job_id, _ = manager.submit({})
    child = manager.active[1]
    with pytest.raises(RuntimeError):
        manager.submit({})
    assert manager.cancel(job_id)["status"] == "canceled"
    wait_reaped(manager, child)
    assert manager.read(job_id)["status"] == "canceled"


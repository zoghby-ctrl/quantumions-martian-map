"""One cancelable QAOA subprocess per server, with an independent wall-clock watchdog."""

import atexit
import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path

LIMIT_SECONDS = 45
CAPACITY = 24
logger = logging.getLogger("uvicorn.error")


class Jobs:
    def __init__(self, timeout=LIMIT_SECONDS):
        self.timeout = timeout
        self.lock = threading.Lock()
        self.results = OrderedDict()
        self.completed = {}
        self.active = None

    def submit(self, payload):
        key = json.dumps(payload, sort_keys=True)
        with self.lock:
            previous = self.completed.get(key)
            if previous:
                return previous, True
            if self.active:
                raise RuntimeError("Another quantum comparison is running")
            job_id = uuid.uuid4().hex
            env = {
                **os.environ,
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "RAYON_NUM_THREADS": "1",
                "PYTHONIOENCODING": "utf-8",
            }
            proc = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.active = (job_id, proc)
            self.results[job_id] = {"status": "running"}
            while len(self.results) > CAPACITY:
                expired, _ = self.results.popitem(last=False)
                self.completed = {
                    k: v for k, v in self.completed.items() if v != expired
                }
            threading.Thread(
                target=self._watch, args=(job_id, proc, payload, key), daemon=True
            ).start()
            return job_id, False

    def _watch(self, job_id, proc, payload, key):
        started = time.monotonic()
        try:
            stdout, stderr = proc.communicate(json.dumps(payload), timeout=self.timeout)
            if proc.returncode:
                raise RuntimeError(stderr[-1200:] or "Worker exited")
            result = {"status": "complete", "result": json.loads(stdout)}
            reason = result["result"]["meta"]["quantum"].get("fallback_reason")
            if reason:
                logger.warning(
                    "Quantum job %s returned a classical fallback: %s", job_id, reason
                )
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            result = {
                "status": "timed_out",
                "detail": f"Worker stopped at the {self.timeout} second limit",
            }
        except Exception as exc:
            with self.lock:
                canceled = self.results[job_id]["status"] == "canceled"
            if not canceled:
                logger.error("Quantum worker %s failed: %s", job_id, exc)
            result = {
                "status": "failed",
                "detail": "Quantum worker failed. The full-grid route is available.",
            }
        with self.lock:
            if self.results[job_id]["status"] != "canceled":
                self.results[job_id] = {
                    **result,
                    "worker_wall_ms": round((time.monotonic() - started) * 1000, 1),
                }
                if (
                    result["status"] == "complete"
                    and result["result"]["features"][-1]["properties"]["solver"]
                    == "qaoa_waypoint_subgraph"
                ):
                    self.completed[key] = job_id
            self.active = None

    def read(self, job_id):
        with self.lock:
            return self.results.get(job_id)

    def cancel(self, job_id):
        with self.lock:
            if self.active and self.active[0] == job_id:
                self.active[1].kill()
                self.results[job_id] = {"status": "canceled"}
            return self.results.get(job_id)

    def shutdown(self):
        with self.lock:
            if self.active:
                self.active[1].kill()


jobs = Jobs()
atexit.register(jobs.shutdown)

if __name__ == "__main__":
    from contextlib import redirect_stdout
    from main import RouteRequest, make_result

    with redirect_stdout(sys.stderr):
        answer = make_result(
            RouteRequest.model_validate_json(sys.stdin.read()), quantum=True
        )
    print(json.dumps(answer, allow_nan=False))

"""What `/api/health` checks (issue 19): the things this deployment leans on, each within a second.

- `db`: a `SELECT 1` round trip to the database (OCI MySQL HeatWave).
- `worker`: the PDF worker's heartbeat (`manage.py pdf_worker` also runs the retention prune and
  the Shorts sync). The worker writes `WORKER_HEARTBEAT_KEY` to `django_cache` every
  `WORKER_BEAT_SECONDS` with a `WORKER_HEARTBEAT_TTL` expiry, so a dead worker shows up as a missing
  key within the TTL. The same beat touches `WORKER_HEARTBEAT_FILE` for the worker container's own
  compose healthcheck.

There is no Redis. The ready scope (`?scope=ready`) checks only `db`: the web container's
healthcheck, the deploy's health wait and rollback use it, so a dead worker never takes web out.

Each check runs on its own thread with `CHECK_TIMEOUT` seconds; a check that raises or does not
answer in time is failed. Results carry only the check names, never hosts or error text.
"""

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path

from django.core.cache import cache
from django.db import connection

logger = logging.getLogger(__name__)

CHECK_TIMEOUT = 1.0
WORKER_HEARTBEAT_KEY = "health:pdf-worker"
WORKER_BEAT_SECONDS = 15.0
WORKER_HEARTBEAT_TTL = 90
WORKER_HEARTBEAT_FILE = Path("/tmp/pdf-worker-alive")


def _on_own_connection(check: Callable[[], bool]) -> Callable[[], bool]:
    """A thread opens its own database connection; close it so health hits do not leak them."""

    def run() -> bool:
        try:
            return check()
        finally:
            connection.close()

    return run


def db_ok() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
    return row is not None and row[0] == 1


def worker_alive() -> bool:
    return cache.get(WORKER_HEARTBEAT_KEY) is not None


def beat_worker() -> None:
    """Called by the worker every WORKER_BEAT_SECONDS. The file goes first: it needs no database."""
    try:
        WORKER_HEARTBEAT_FILE.touch()
    except OSError:
        logger.exception("worker heartbeat file not touched")
    cache.set(WORKER_HEARTBEAT_KEY, int(time.time()), WORKER_HEARTBEAT_TTL)


CHECKS: dict[str, Callable[[], bool]] = {"db": db_ok, "worker": worker_alive}
READY_CHECKS = ("db",)


def failed_checks(names: tuple[str, ...] | None = None) -> list[str]:
    """The names of the checks that failed, in CHECKS order (empty = healthy)."""
    chosen = [n for n in CHECKS if names is None or n in names]
    pool = ThreadPoolExecutor(max_workers=len(chosen), thread_name_prefix="health")
    try:
        futures = {n: pool.submit(_on_own_connection(CHECKS[n])) for n in chosen}
        deadline = time.monotonic() + CHECK_TIMEOUT
        failed = []
        for name, future in futures.items():
            try:
                ok = future.result(timeout=max(0.0, deadline - time.monotonic()))
            except FutureTimeout:
                logger.warning("health check %s timed out", name)
                ok = False
            except Exception:
                logger.warning("health check %s failed", name, exc_info=True)
                ok = False
            if not ok:
                failed.append(name)
        return failed
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

"""`manage.py pdf_worker`: the revision PDF worker (compose service `worker`).

Processes due PDF jobs one at a time and sleeps `--poll` seconds when there are none. SIGTERM
(`docker compose stop`) lets the current job finish before exiting. `--once` handles at most one
job and returns, for tests and manual runs.

The same loop drops personal data past its retention once a day (services/retention.py, issue
201) and registers the YouTube channel's new Shorts every 30 minutes (services/shorts.py, issue
211): it is the only long-running process of the deployment, so the schedule lives here. Neither
may stop the PDF jobs: their errors are logged and the next check tries again.
"""

import logging
import signal
import time
from argparse import ArgumentParser
from collections.abc import Callable
from types import FrameType

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from services import pdf, retention, shorts

logger = logging.getLogger(__name__)

# How often the loop asks whether today's retention run is done (retention.prune_if_due).
RETENTION_CHECK_SECONDS = 600.0
# How often the loop asks whether the channel sync is due (shorts.sync_if_due, 30 minutes apart).
SHORTS_CHECK_SECONDS = 60.0


class Every:
    """Runs `job` when `tick(now)` comes at least `seconds` after the last run (first tick runs)."""

    def __init__(self, seconds: float, job: Callable[[], None]) -> None:
        self._seconds = seconds
        self._job = job
        self._next = float("-inf")

    def tick(self, now: float) -> None:
        if now >= self._next:
            self._next = now + self._seconds
            self._job()


def prune_if_due() -> None:
    try:
        pruned = retention.prune_if_due()
    except Exception:  # a failed cleanup must not stop the PDF jobs; the next check retries
        logger.exception("retention prune failed")
        return
    if pruned is not None:
        logger.info(
            "retention: %d inquiries deleted, %d proposal events stripped",
            pruned.inquiries,
            pruned.proposal_events,
        )


def sync_shorts_if_due() -> None:
    try:
        created = shorts.sync_if_due()
    except Exception:  # a failed sync must not stop the PDF jobs; the next due check retries
        logger.exception("shorts channel sync failed")
        return
    if created:
        logger.info("shorts: %d new from the channel", created)


def checks() -> list[Every]:
    return [
        Every(RETENTION_CHECK_SECONDS, prune_if_due),
        Every(SHORTS_CHECK_SECONDS, sync_shorts_if_due),
    ]


class Command(BaseCommand):
    help = "리비전 PDF 작업을 하나씩 처리한다"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--once", action="store_true", help="작업 하나만 처리하고 끝낸다")
        parser.add_argument("--poll", type=float, default=5.0, help="일이 없을 때 쉬는 초")

    def handle(self, *args: object, once: bool, poll: float, **options: object) -> None:
        if once:
            pdf.work_once()
            return
        stopping = False

        def stop(signum: int, frame: FrameType | None) -> None:
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        self.stdout.write("PDF worker started")
        scheduled = checks()
        while not stopping:
            close_old_connections()
            for check in scheduled:
                check.tick(time.monotonic())
            if not pdf.work_once():
                slept = 0.0
                while slept < poll and not stopping:
                    time.sleep(0.5)
                    slept += 0.5
        self.stdout.write("PDF worker stopped")

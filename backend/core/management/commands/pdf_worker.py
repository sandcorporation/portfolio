"""`manage.py pdf_worker`: the revision PDF worker (compose service `worker`).

Processes due PDF jobs one at a time and sleeps `--poll` seconds when there are none. SIGTERM
(`docker compose stop`) lets the current job finish before exiting. `--once` handles at most one
job and returns, for tests and manual runs.

The same loop drops personal data past its retention once a day (services/retention.py, issue
201): it is the only long-running process of the deployment, so the schedule lives here.
"""

import logging
import signal
import time
from argparse import ArgumentParser
from types import FrameType

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from services import pdf, retention

logger = logging.getLogger(__name__)

# How often the loop asks whether today's retention run is done (retention.prune_if_due).
RETENTION_CHECK_SECONDS = 600.0


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
        next_retention = 0.0
        while not stopping:
            close_old_connections()
            if time.monotonic() >= next_retention:
                prune_if_due()
                next_retention = time.monotonic() + RETENTION_CHECK_SECONDS
            if not pdf.work_once():
                slept = 0.0
                while slept < poll and not stopping:
                    time.sleep(0.5)
                    slept += 0.5
        self.stdout.write("PDF worker stopped")

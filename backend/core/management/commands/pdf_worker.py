"""`manage.py pdf_worker`: the revision PDF worker (compose service `worker`).

Processes due PDF jobs one at a time and sleeps `--poll` seconds when there are none. SIGTERM
(`docker compose stop`) lets the current job finish before exiting. `--once` handles at most one
job and returns, for tests and manual runs.
"""

import signal
import time
from argparse import ArgumentParser
from types import FrameType

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from services import pdf


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
        while not stopping:
            close_old_connections()
            if not pdf.work_once():
                slept = 0.0
                while slept < poll and not stopping:
                    time.sleep(0.5)
                    slept += 0.5
        self.stdout.write("PDF worker stopped")

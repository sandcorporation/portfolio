"""`manage.py db_backup`: the daily DB backup (compose service `backup`, #19).

Loop mode checks every `--poll` seconds whether a backup is due (see services/backup.py) and
retries a failed one after `--retry` seconds, alerting Discord only on the first failure of a
due slot. `--once` runs one check and returns; `--force` backs up now even if one is recent.
"""

import logging
import signal
import time
from argparse import ArgumentParser
from datetime import UTC, datetime
from types import FrameType

from django.core.management.base import BaseCommand, CommandError

from adapters.notify import get_notifier
from adapters.storage import StorageNotConfigured, get_storage
from services import backup

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "매일 04:00 KST에 DB를 pg_dump해 비공개 버킷에 올리고 30일 지난 백업을 지운다"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--once", action="store_true", help="한 번 확인하고 끝낸다")
        parser.add_argument("--force", action="store_true", help="최근 백업이 있어도 지금 한다")
        parser.add_argument("--poll", type=float, default=300.0, help="확인 간격(초)")
        parser.add_argument("--retry", type=float, default=3600.0, help="실패 뒤 재시도 간격(초)")

    def handle(
        self, *args: object, once: bool, force: bool, poll: float, retry: float, **options: object
    ) -> None:
        notifier = get_notifier()
        if once or force:
            try:
                storage = get_storage()
                now = datetime.now(UTC)
                result = (
                    backup.run_backup(storage, now) if force else backup.backup_if_due(storage, now)
                )
            except StorageNotConfigured as exc:
                raise CommandError(str(exc)) from exc
            except Exception as exc:
                backup.alert_failure(notifier, datetime.now(UTC), exc)
                raise CommandError(f"백업 실패: {exc}") from exc
            self.stdout.write(f"백업: {result.key}" if result else "오늘 몫은 이미 있다")
            return

        stopping = False

        def stop(signum: int, frame: FrameType | None) -> None:
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        self.stdout.write("DB backup loop started")
        alerted_slot: datetime | None = None
        while not stopping:
            now = datetime.now(UTC)
            wait = poll
            try:
                backup.backup_if_due(get_storage(), now)
            except StorageNotConfigured:
                logger.error("스토리지 설정이 없어 백업을 못 한다")
            except Exception as exc:
                wait = retry
                slot = backup.due_since(now)
                if slot != alerted_slot:  # one alert per due slot, not one per hourly retry
                    backup.alert_failure(notifier, now, exc)
                    alerted_slot = slot
            slept = 0.0
            while slept < wait and not stopping:
                time.sleep(0.5)
                slept += 0.5
        self.stdout.write("DB backup loop stopped")

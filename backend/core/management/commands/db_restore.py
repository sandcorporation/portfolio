"""`manage.py db_restore`: restore a backup into an EMPTY database (#19).

No --clean: on a database that already has tables pg_restore stops at the first clash, so live
data is never overwritten.
"""

import tempfile
from argparse import ArgumentParser
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from adapters.storage import Bucket, get_storage
from services import backup


class Command(BaseCommand):
    help = "백업(기본: 가장 최근)을 빈 DB에 복원한다"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--dbname", help="복원할 (빈) 데이터베이스 이름")
        parser.add_argument("--key", help="복원할 객체 키. 없으면 가장 최근 백업")
        parser.add_argument("--list", action="store_true", help="백업 목록만 보여 준다")

    def handle(
        self,
        *args: object,
        dbname: str | None,
        key: str | None,
        list: bool,
        **options: object,  # noqa: A002
    ) -> None:
        storage = get_storage()
        if list:
            for k in storage.list_keys(Bucket.PRIVATE, backup.PREFIX):
                self.stdout.write(k)
            return
        if not dbname:
            raise CommandError("--dbname 이 필요하다")
        key = key or backup.latest_key(storage)
        if key is None:
            raise CommandError("백업이 없다")
        with tempfile.TemporaryDirectory(prefix="restore-") as tmp:
            path = Path(tmp) / "portfolio.dump"
            storage.download_file(Bucket.PRIVATE, key, path)
            try:
                backup.pg_restore(path, dbname)
            except Exception as exc:
                detail = getattr(exc, "stderr", "") or str(exc)
                raise CommandError(f"복원 실패: {detail.strip()[-800:]}") from exc
        self.stdout.write(f"복원 완료: {key} -> {dbname}")

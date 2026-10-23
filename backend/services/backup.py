"""Daily database backup (#19): `mysqldump` (gzipped) to a temp file, then up to the private bucket.

Key: `backups/YYYY/MM/DD/portfolio-<UTC YYYYMMDDTHHMMSSZ>.sql.gz` (the date is UTC and is also what
retention and the once-a-day check read, so no object metadata is needed). A temp file rather
than a stream: the upload retries and multipart need a known length, and OCI's S3 API rejects
unsized chunked bodies; the dump is small and the file never sits in memory.

The schedule is "once per 04:00 KST": a backup is due when the newest one is older than the most
recent 04:00 KST. A container restart therefore never backs up twice, and a missed run is made
up at the next start. Old backups (> RETENTION_DAYS) are deleted after a successful upload.
Keys ending in `.dump` are the Postgres-era `pg_dump -Fc` backups (#63): they still count for
the schedule and are pruned the same way, but cannot be restored into MySQL.
"""

import gzip
import logging
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from django.conf import settings

from adapters.notify import Field, Notification, Notifier
from adapters.storage import Bucket, ObjectStorage

logger = logging.getLogger(__name__)

PREFIX = "backups/"
RETENTION_DAYS = 30
KST = timezone(timedelta(hours=9))  # no DST, so no tzdata needed in the slim image
RUN_AT_HOUR_KST = 4
DUMP_TIMEOUT_SECONDS = 30 * 60

SUFFIX = ".sql.gz"
POSTGRES_SUFFIX = ".dump"  # before #63
_KEY_RE = re.compile(r"^backups/\d{4}/\d{2}/\d{2}/portfolio-(\d{8}T\d{6}Z)\.(?:sql\.gz|dump)$")

DumpFn = Callable[[Path], None]


def backup_key(now: datetime) -> str:
    utc = now.astimezone(UTC)
    return f"{PREFIX}{utc:%Y/%m/%d}/portfolio-{utc:%Y%m%dT%H%M%SZ}{SUFFIX}"


def key_time(key: str) -> datetime | None:
    found = _KEY_RE.match(key)
    if found is None:
        return None
    return datetime.strptime(found.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def latest_key(storage: ObjectStorage) -> str | None:
    keys = [k for k in storage.list_keys(Bucket.PRIVATE, PREFIX) if key_time(k)]
    return max(keys, key=lambda k: key_time(k) or datetime.min.replace(tzinfo=UTC), default=None)


def due_since(now: datetime) -> datetime:
    """The most recent 04:00 KST at or before `now`."""
    local = now.astimezone(KST)
    slot = local.replace(hour=RUN_AT_HOUR_KST, minute=0, second=0, microsecond=0)
    return (slot if slot <= local else slot - timedelta(days=1)).astimezone(UTC)


def is_due(storage: ObjectStorage, now: datetime) -> bool:
    newest = latest_key(storage)
    taken = key_time(newest) if newest else None
    return taken is None or taken < due_since(now)


def _client_args() -> tuple[list[str], dict[str, str]]:
    """Connection flags for the mysql/mysqldump clients; the password goes in the environment
    (MYSQL_PWD) so it never shows in the process list."""
    db = settings.DATABASES["default"]
    args = [
        f"--host={db['HOST']}",
        f"--port={db['PORT']}",
        f"--user={db['USER']}",
        "--default-character-set=utf8mb4",
    ]
    return args, {**os.environ, "MYSQL_PWD": str(db["PASSWORD"])}


def mysql_dump(path: Path) -> None:
    """A consistent (`--single-transaction`) gzipped SQL dump of the default database.

    No DROP TABLE and no CREATE DATABASE in it, so it only ever loads into an empty database.
    """
    name = str(settings.DATABASES["default"]["NAME"])
    args, env = _client_args()
    with tempfile.TemporaryDirectory(prefix="dump-") as tmp:
        raw = Path(tmp) / "dump.sql"
        subprocess.run(  # noqa: S603
            [
                "mysqldump",
                *args,
                "--single-transaction",
                "--skip-add-drop-table",
                "--no-tablespaces",
                "--skip-routines",
                "--skip-triggers",
                "--hex-blob",
                f"--result-file={raw}",
                name,
            ],  # noqa: S607
            env=env,
            check=True,
            timeout=DUMP_TIMEOUT_SECONDS,
            capture_output=True,
            text=True,
        )
        with raw.open("rb") as src, gzip.open(path, "wb") as dst:
            shutil.copyfileobj(src, dst)


def mysql_restore(path: Path, dbname: str) -> None:
    """Load a backup made by `mysql_dump` into `dbname`, which must exist and be empty."""
    args, env = _client_args()
    with tempfile.TemporaryDirectory(prefix="restore-sql-") as tmp:
        raw = Path(tmp) / "dump.sql"
        with gzip.open(path, "rb") as src, raw.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        with raw.open("rb") as sql:
            subprocess.run(  # noqa: S603
                ["mysql", *args, dbname],  # noqa: S607
                stdin=sql,
                env=env,
                check=True,
                timeout=DUMP_TIMEOUT_SECONDS,
                capture_output=True,
                text=True,
            )


@dataclass(frozen=True)
class BackupResult:
    key: str
    size: int
    deleted: tuple[str, ...]


def prune(storage: ObjectStorage, now: datetime) -> tuple[str, ...]:
    cutoff = now.astimezone(UTC) - timedelta(days=RETENTION_DAYS)
    old = [
        k
        for k in storage.list_keys(Bucket.PRIVATE, PREFIX)
        if (t := key_time(k)) is not None and t < cutoff
    ]
    for key in old:
        storage.delete(Bucket.PRIVATE, key)
    return tuple(old)


def run_backup(storage: ObjectStorage, now: datetime, dump: DumpFn | None = None) -> BackupResult:
    """Dump, upload, then prune. Raises on any failure (the caller alerts)."""
    key = backup_key(now)
    with tempfile.TemporaryDirectory(prefix="backup-") as tmp:
        path = Path(tmp) / f"portfolio{SUFFIX}"
        (dump or mysql_dump)(path)
        size = path.stat().st_size
        if size == 0:
            raise RuntimeError("mysqldump가 빈 파일을 만들었다")
        storage.upload_file(Bucket.PRIVATE, key, path, "application/gzip")
    return BackupResult(key=key, size=size, deleted=prune(storage, now))


def alert_failure(notifier: Notifier, now: datetime, exc: Exception) -> None:
    logger.error("DB backup failed", exc_info=exc)
    detail = (exc.stderr if isinstance(exc, subprocess.CalledProcessError) else "") or str(exc)
    notifier.send(
        Notification(
            title="DB 백업 실패",
            text=detail.strip()[-1000:],
            fields=(Field("시각(UTC)", now.astimezone(UTC).strftime("%Y-%m-%d %H:%M")),),
            severity="alert",
        )
    )


def backup_if_due(
    storage: ObjectStorage, now: datetime, dump: DumpFn | None = None
) -> BackupResult | None:
    """One scheduler tick. None when nothing was due; failures propagate (see alert_failure)."""
    if not is_due(storage, now):
        return None
    result = run_backup(storage, now, dump)
    logger.info(
        "DB backup done: %s (%d bytes), pruned %d", result.key, result.size, len(result.deleted)
    )
    return result

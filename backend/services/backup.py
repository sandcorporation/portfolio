"""Daily database backup (#19): `pg_dump -Fc` to a temp file, then up to the private bucket.

Key: `backups/YYYY/MM/DD/portfolio-<UTC YYYYMMDDTHHMMSSZ>.dump` (the date is UTC and is also what
retention and the once-a-day check read, so no object metadata is needed). A temp file rather
than a stream: the upload retries and multipart need a known length, and OCI's S3 API rejects
unsized chunked bodies; the dump is small and the file never sits in memory.

The schedule is "once per 04:00 KST": a backup is due when the newest one is older than the most
recent 04:00 KST. A container restart therefore never backs up twice, and a missed run is made
up at the next start. Old backups (> RETENTION_DAYS) are deleted after a successful upload.
"""

import logging
import os
import re
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

_KEY_RE = re.compile(r"^backups/\d{4}/\d{2}/\d{2}/portfolio-(\d{8}T\d{6}Z)\.dump$")

DumpFn = Callable[[Path], None]


def backup_key(now: datetime) -> str:
    utc = now.astimezone(UTC)
    return f"{PREFIX}{utc:%Y/%m/%d}/portfolio-{utc:%Y%m%dT%H%M%SZ}.dump"


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


def _pg_env() -> dict[str, str]:
    db = settings.DATABASES["default"]
    return {
        **os.environ,
        "PGHOST": str(db["HOST"]),
        "PGPORT": str(db["PORT"]),
        "PGUSER": str(db["USER"]),
        "PGPASSWORD": str(db["PASSWORD"]),
    }


def pg_dump(path: Path) -> None:
    """Custom-format dump (already compressed) of the default database into `path`."""
    name = str(settings.DATABASES["default"]["NAME"])
    subprocess.run(  # noqa: S603
        ["pg_dump", "-Fc", "--no-owner", "--no-acl", "-f", str(path), name],  # noqa: S607
        env=_pg_env(),
        check=True,
        timeout=DUMP_TIMEOUT_SECONDS,
        capture_output=True,
        text=True,
    )


def pg_restore(path: Path, dbname: str) -> None:
    subprocess.run(  # noqa: S603
        ["pg_restore", "--no-owner", "--no-acl", "--exit-on-error", "-d", dbname, str(path)],  # noqa: S607
        env=_pg_env(),
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
        path = Path(tmp) / "portfolio.dump"
        (dump or pg_dump)(path)
        size = path.stat().st_size
        if size == 0:
            raise RuntimeError("pg_dump가 빈 파일을 만들었다")
        storage.upload_file(Bucket.PRIVATE, key, path, "application/octet-stream")
    return BackupResult(key=key, size=size, deleted=prune(storage, now))


def alert_failure(notifier: Notifier, now: datetime, exc: Exception) -> None:
    logger.error("DB backup failed", exc_info=exc)
    detail = (exc.stderr if isinstance(exc, subprocess.CalledProcessError) else "") or str(exc)
    notifier.send(
        Notification(
            title="DB 백업 실패",
            text=detail.strip()[-1000:],
            fields=(Field("시각(UTC)", now.astimezone(UTC).strftime("%Y-%m-%d %H:%M")),),
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

"""Daily DB backup (#19) against a fake storage and notifier: key shape, once per 04:00 KST slot,
30-day pruning, and an alert when the dump or upload fails."""

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from adapters.fake_notify import FakeNotifier
from adapters.fake_storage import FakeObjectStorage
from adapters.storage import Bucket
from services import backup


def fake_dump(path: Path) -> None:
    path.write_bytes(b"PGDMP-fake")


def utc(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0
) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


def put(storage: FakeObjectStorage, when: datetime) -> str:
    key = backup.backup_key(when)
    storage.objects[(Bucket.PRIVATE, key)] = (b"x", "application/octet-stream")
    return key


def test_uploads_to_dated_key_in_private_bucket() -> None:
    storage = FakeObjectStorage()
    result = backup.backup_if_due(storage, utc(2026, 5, 3, 19, 5, 9), fake_dump)
    assert result is not None
    assert result.key == "backups/2026/05/03/portfolio-20260503T190509Z.dump"
    assert storage.objects[(Bucket.PRIVATE, result.key)][0] == b"PGDMP-fake"
    assert not [c for c in storage.calls if c[1] == Bucket.PUBLIC]


def test_runs_once_per_slot_even_when_restarted() -> None:
    storage = FakeObjectStorage()
    first = utc(2026, 5, 3, 19, 0)  # 04:00 KST on the 4th
    assert backup.backup_if_due(storage, first, fake_dump) is not None
    # restarts / later polls the same day do nothing
    assert backup.backup_if_due(storage, first + timedelta(minutes=5), fake_dump) is None
    assert backup.backup_if_due(storage, first + timedelta(hours=18), fake_dump) is None
    # the next 04:00 KST slot is due again
    assert backup.backup_if_due(storage, first + timedelta(hours=24), fake_dump) is not None
    assert len(storage.list_keys(Bucket.PRIVATE, backup.PREFIX)) == 2


def test_not_due_before_the_morning_slot_when_yesterdays_exists() -> None:
    storage = FakeObjectStorage()
    put(storage, utc(2026, 5, 2, 19, 0))  # 04:00 KST on the 3rd
    assert backup.backup_if_due(storage, utc(2026, 5, 3, 18, 59), fake_dump) is None


def test_prunes_backups_older_than_30_days_only() -> None:
    storage = FakeObjectStorage()
    now = utc(2026, 6, 15, 19, 0)
    old = put(storage, now - timedelta(days=31))
    edge = put(storage, now - timedelta(days=29))
    storage.objects[(Bucket.PRIVATE, "backups/notes.txt")] = (b"keep", "text/plain")
    result = backup.backup_if_due(storage, now, fake_dump)
    assert result is not None and result.deleted == (old,)
    assert (Bucket.PRIVATE, edge) in storage.objects
    assert (Bucket.PRIVATE, "backups/notes.txt") in storage.objects


def test_failed_dump_uploads_and_prunes_nothing() -> None:
    storage = FakeObjectStorage()
    now = utc(2026, 6, 15, 19, 0)
    old = put(storage, now - timedelta(days=40))

    def broken(path: Path) -> None:
        raise subprocess.CalledProcessError(1, "pg_dump", stderr="connection refused")

    with pytest.raises(subprocess.CalledProcessError):
        backup.backup_if_due(storage, now, broken)
    assert (Bucket.PRIVATE, old) in storage.objects
    assert not [c for c in storage.calls if c[0] in {"upload_file", "delete"}]


def test_empty_dump_is_a_failure() -> None:
    def empty_dump(path: Path) -> None:
        path.write_bytes(b"")

    with pytest.raises(RuntimeError):
        backup.run_backup(FakeObjectStorage(), utc(2026, 6, 15), empty_dump)


def test_alert_names_the_failure() -> None:
    notifier = FakeNotifier()
    exc = subprocess.CalledProcessError(1, "pg_dump", stderr="connection refused\n")
    backup.alert_failure(notifier, utc(2026, 6, 15, 19, 0), exc)
    assert notifier.sent[0].title == "DB 백업 실패"
    assert "connection refused" in notifier.sent[0].text
    assert notifier.sent[0].severity == "alert"


def test_command_force_alerts_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = FakeObjectStorage()
    notifier = FakeNotifier()
    monkeypatch.setattr("core.management.commands.db_backup.get_storage", lambda: storage)
    monkeypatch.setattr("core.management.commands.db_backup.get_notifier", lambda: notifier)

    def broken(path: Path) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(backup, "pg_dump", broken)
    with pytest.raises(CommandError):
        call_command("db_backup", "--force")
    assert [n.title for n in notifier.sent] == ["DB 백업 실패"]


def test_restore_command_fetches_latest(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = FakeObjectStorage()
    put(storage, utc(2026, 6, 1))
    newest = put(storage, utc(2026, 6, 2))
    restored: list[tuple[bytes, str]] = []
    monkeypatch.setattr("core.management.commands.db_restore.get_storage", lambda: storage)
    monkeypatch.setattr(
        backup, "pg_restore", lambda path, db: restored.append((path.read_bytes(), db))
    )
    call_command("db_restore", "--dbname", "scratch")
    assert restored == [(b"x", "scratch")]
    assert ("download_file", Bucket.PRIVATE, newest) in storage.calls

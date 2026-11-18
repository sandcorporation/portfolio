"""`/api/health` (core/health.py, issue 19): 503 when the database or the PDF worker is down."""

import time
from pathlib import Path

import pytest
from django.db.utils import OperationalError
from django.test import Client

from core import health
from core.management.commands import pdf_worker


def _fine() -> bool:
    return True


def _down() -> bool:
    raise OperationalError("connection refused to 10.0.0.5")


@pytest.fixture
def worker_beating(monkeypatch: pytest.MonkeyPatch) -> None:
    # The check runs on its own thread and connection, which cannot see a heartbeat written
    # inside the test's transaction; beat_worker/worker_alive are tested together below.
    monkeypatch.setitem(health.CHECKS, "worker", _fine)


@pytest.mark.django_db
def test_healthy_when_database_and_worker_answer(client: Client, worker_beating: None) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_database_down_is_503_without_details(
    client: Client, worker_beating: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(health.CHECKS, "db", _down)

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "failed": ["db"]}
    assert b"10.0.0.5" not in response.content


@pytest.mark.django_db
def test_no_worker_heartbeat_is_503(client: Client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "failed": ["worker"]}


@pytest.mark.django_db
def test_a_check_that_hangs_fails_within_the_limit(
    client: Client, worker_beating: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def hang() -> bool:
        time.sleep(0.5)
        return True

    monkeypatch.setattr(health, "CHECK_TIMEOUT", 0.05)
    monkeypatch.setitem(health.CHECKS, "db", hang)

    started = time.monotonic()
    response = client.get("/api/health")

    assert time.monotonic() - started < 0.4
    assert response.json() == {"status": "error", "failed": ["db"]}


@pytest.mark.django_db
def test_ready_scope_checks_only_the_database(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The container healthcheck and the deploy wait use it: a dead worker must not take web out.
    assert client.get("/api/health?scope=ready").json() == {"status": "ok"}

    monkeypatch.setitem(health.CHECKS, "db", _down)
    response = client.get("/api/health?scope=ready")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "failed": ["db"]}


@pytest.mark.django_db
def test_worker_heartbeat_marks_the_worker_alive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, "WORKER_HEARTBEAT_FILE", tmp_path / "alive")
    assert not health.worker_alive()

    health.beat_worker()

    assert health.worker_alive()
    assert (tmp_path / "alive").exists()


def test_heartbeat_stops_when_the_loop_is_stuck(monkeypatch: pytest.MonkeyPatch) -> None:
    beats: list[int] = []
    heartbeat = pdf_worker.Heartbeat(beat=lambda: beats.append(1))

    assert heartbeat.beat_once()
    monkeypatch.setattr(pdf_worker, "STUCK_AFTER_SECONDS", -1.0)
    assert not heartbeat.beat_once()
    assert beats == [1]


def test_heartbeat_survives_a_database_error() -> None:
    def beat() -> None:
        _down()

    heartbeat = pdf_worker.Heartbeat(beat=beat)

    assert not heartbeat.beat_once()  # logged; the next beat retries

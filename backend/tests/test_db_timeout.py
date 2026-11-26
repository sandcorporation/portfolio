"""A database that stops answering must fail in seconds, not at gunicorn's 30s (issues 70, 74)."""

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

import pytest
from django.db import connections
from django.db.backends.mysql.base import DatabaseWrapper
from django.db.utils import OperationalError

from config.settings import db_options


def test_options_cap_new_connections_and_only_cap_reads_when_asked() -> None:
    assert db_options("3", "0") == {"charset": "utf8mb4", "connect_timeout": 3}
    assert db_options("3", "5") == {
        "charset": "utf8mb4",
        "connect_timeout": 3,
        "read_timeout": 5,
        "write_timeout": 5,
    }


def test_a_database_that_never_answers_fails_after_the_connect_timeout() -> None:
    with socket.socket() as silent:  # listens (the kernel completes the handshake), never accepts
        silent.bind(("127.0.0.1", 0))
        silent.listen(1)
        config: dict[str, Any] = {**connections["default"].settings_dict}
        config["HOST"], config["PORT"] = "127.0.0.1", str(silent.getsockname()[1])
        config["OPTIONS"] = db_options("1", "0")
        wrapper = DatabaseWrapper(config, alias="silent")
        started = time.monotonic()
        with pytest.raises(OperationalError), wrapper.wrap_database_errors:
            wrapper.connect()  # ensure_connection is blocked outside django_db
        assert 0.8 <= time.monotonic() - started < 4


@contextmanager
def _pausable_proxy(host: str, port: int) -> Iterator[tuple[int, threading.Event]]:
    """TCP relay to the real test database; once `stall` is set it swallows bytes both ways."""
    stall = threading.Event()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    sockets: list[socket.socket] = [listener]

    def pump(src: socket.socket, dst: socket.socket) -> None:
        try:
            while data := src.recv(65536):
                if not stall.is_set():
                    dst.sendall(data)
        except OSError:
            pass

    def accept() -> None:
        try:
            client, _ = listener.accept()
        except OSError:
            return
        upstream = socket.create_connection((host, port))
        sockets.extend([client, upstream])
        threading.Thread(target=pump, args=(client, upstream), daemon=True).start()
        threading.Thread(target=pump, args=(upstream, client), daemon=True).start()

    threading.Thread(target=accept, daemon=True).start()
    try:
        yield listener.getsockname()[1], stall
    finally:
        for s in sockets:
            s.close()


@pytest.mark.django_db
def test_a_reused_connection_that_stops_answering_fails_after_the_read_timeout() -> None:
    real = connections["default"].settings_dict
    with _pausable_proxy(str(real["HOST"]), int(real["PORT"])) as (port, stall):
        config: dict[str, Any] = {**real, "HOST": "127.0.0.1", "PORT": str(port)}
        config["OPTIONS"] = db_options("3", "1")
        wrapper = DatabaseWrapper(config, alias="stalls")
        wrapper.connect()
        with closing(wrapper.connection):
            with wrapper.cursor() as cursor:
                cursor.execute("SELECT 1")  # healthy while reused
            stall.set()
            started = time.monotonic()
            with pytest.raises(OperationalError), wrapper.cursor() as cursor:
                cursor.execute("SELECT 1")
            assert 0.8 <= time.monotonic() - started < 4


@pytest.mark.django_db
def test_a_warm_connection_that_stalls_fails_its_health_check_and_the_reconnect_fails_in_time() -> (
    None
):
    """The health-check ping stalls, then the reconnect must be capped too."""
    real = connections["default"].settings_dict
    with _pausable_proxy(str(real["HOST"]), int(real["PORT"])) as (port, stall):
        config: dict[str, Any] = {**real, "HOST": "127.0.0.1", "PORT": str(port)}
        config["OPTIONS"] = db_options("1", "1")
        wrapper = DatabaseWrapper(config, alias="warm")
        wrapper.connect()
        try:
            with wrapper.cursor() as cursor:
                cursor.execute("SELECT 1")
            vars(wrapper)["health_check_done"] = False  # a new request on a reused connection
            stall.set()
            started = time.monotonic()
            wrapper.close_if_health_check_failed()  # ping stalls → read_timeout → closed
            assert wrapper.connection is None
            with pytest.raises(OperationalError), wrapper.wrap_database_errors:
                wrapper.connect()  # nobody accepts the second connection → connect_timeout
            assert 1.5 <= time.monotonic() - started < 5
        finally:
            wrapper.close()


# --- the real path: DATABASES reads the env, the Dockerfile CMD sets it (web only) ---


def _load_settings(monkeypatch: pytest.MonkeyPatch, **env: str | None) -> Any:
    import importlib.util

    from config import settings as real_settings

    for name in ("DB_CONNECT_TIMEOUT", "DB_READ_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        if value is not None:
            monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location("settings_under_test", real_settings.__file__)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_databases_setting_reads_the_timeouts_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web = _load_settings(monkeypatch, DB_READ_TIMEOUT="5")
    assert web.DATABASES["default"]["OPTIONS"]["read_timeout"] == 5
    assert web.DATABASES["default"]["OPTIONS"]["write_timeout"] == 5
    assert web.DATABASES["default"]["OPTIONS"]["connect_timeout"] == 3
    custom = _load_settings(monkeypatch, DB_READ_TIMEOUT="7", DB_CONNECT_TIMEOUT="2")
    assert custom.DATABASES["default"]["OPTIONS"]["read_timeout"] == 7
    assert custom.DATABASES["default"]["OPTIONS"]["connect_timeout"] == 2


def test_without_the_environment_only_new_connections_are_capped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = _load_settings(monkeypatch)  # worker, migrate and management commands
    options = other.DATABASES["default"]["OPTIONS"]
    assert options["connect_timeout"] == 3
    assert "read_timeout" not in options and "write_timeout" not in options
    assert other.DATABASES["default"]["CONN_HEALTH_CHECKS"] is True


def test_only_the_gunicorn_cmd_sets_the_read_timeout() -> None:
    root = Path(__file__).resolve().parents[2]
    cmd = [
        line for line in (root / "Dockerfile").read_text().splitlines() if line.startswith("CMD ")
    ]
    assert len(cmd) == 1
    assert "DB_READ_TIMEOUT=${WEB_DB_READ_TIMEOUT:-5}" in cmd[0]
    assert cmd[0].index("DB_READ_TIMEOUT=") < cmd[0].index("gunicorn")
    # nothing else (worker command, compose files, env example) hands it to other processes
    for name in (
        "docker-compose.yml",
        "docker-compose.prod.yml",
        "docker-compose.local.yml",
        "docker-compose.oracle.yml",
    ):
        text = (root / name).read_text()
        assert "DB_READ_TIMEOUT:" not in text and "DB_READ_TIMEOUT=" not in text.replace(
            "WEB_DB_READ_TIMEOUT", ""
        )

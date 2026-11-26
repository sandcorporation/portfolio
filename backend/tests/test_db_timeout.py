"""A database that stops answering must fail in seconds, not at gunicorn's 30s (issues 70, 74)."""

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
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

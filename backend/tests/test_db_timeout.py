"""A database that accepts the socket but never answers must fail in seconds (issue 70)."""

import socket
import time
from typing import Any, cast

import pytest
from django.conf import settings
from django.db import connections
from django.db.backends.mysql.base import DatabaseWrapper
from django.db.utils import OperationalError


def test_the_connection_gives_up_far_inside_the_gunicorn_timeout() -> None:
    options = cast(dict[str, Any], settings.DATABASES["default"]["OPTIONS"])
    timeout = options["connect_timeout"]
    assert 1 <= timeout <= 5  # gunicorn kills a worker at 30s; the Korean 500 page must come first


def test_a_database_that_never_answers_fails_after_the_connect_timeout() -> None:
    with socket.socket() as silent:  # listens (the kernel completes the handshake), never accepts
        silent.bind(("127.0.0.1", 0))
        silent.listen(1)
        config: dict[str, Any] = {**connections["default"].settings_dict}
        config["HOST"], config["PORT"] = "127.0.0.1", str(silent.getsockname()[1])
        config["OPTIONS"] = {**config["OPTIONS"], "connect_timeout": 1}
        wrapper = DatabaseWrapper(config, alias="silent")
        started = time.monotonic()
        with pytest.raises(OperationalError), wrapper.wrap_database_errors:
            wrapper.connect()  # ensure_connection is blocked outside django_db
        # One attempt ends the request (the view's error goes straight to server_error), so the
        # wait does not stack per cache/session/query.
        assert 0.8 <= time.monotonic() - started < 4

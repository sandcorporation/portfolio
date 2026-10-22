"""Temporary admin login rate limit (issue #25).

Removed with core/admin_ratelimit.py once sandcorp-auth login is live (follow-up to #7).
"""

from collections.abc import Iterator

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache, caches
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import clear_url_caches

LOGIN = "/admin/login/"


@pytest.fixture(autouse=True)
def cache_table(db: None) -> Iterator[None]:
    call_command("createcachetable", verbosity=0)
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def owner(db: None) -> User:
    return User.objects.create_superuser("owner", "o@example.com", "correct-horse-battery")


def attempt(client: Client, username: str, password: str, ip: str = "203.0.113.5") -> int:
    return client.post(
        LOGIN,
        {"username": username, "password": password, "next": "/admin/"},
        headers={"x-forwarded-for": ip},
    ).status_code


def test_default_admin_path_is_404_and_only_the_configured_path_opens() -> None:
    with override_settings(ADMIN_PATH="x7k2-secret/", ROOT_URLCONF="config.urls"):
        from importlib import reload

        import config.urls

        reload(config.urls)
        clear_url_caches()
        client = Client()
        assert client.get("/admin/").status_code == 404
        assert client.get("/x7k2-secret/login/").status_code == 200
    reload(config.urls)
    clear_url_caches()


def test_cache_backend_is_shared_between_processes() -> None:
    assert caches["default"].__class__.__name__ == "DatabaseCache"


def test_locks_after_repeated_failures_and_refuses_the_right_password(owner: User) -> None:
    client = Client()
    for _ in range(5):
        assert attempt(client, "owner", "wrong") == 200
    assert attempt(client, "owner", "correct-horse-battery") == 429
    assert "_auth_user_id" not in client.session


def test_same_user_from_other_ips_is_limited_by_username(owner: User) -> None:
    client = Client()
    for i in range(5):
        assert attempt(client, "owner", "wrong", ip=f"203.0.113.{i + 10}") == 200
    assert attempt(client, "owner", "correct-horse-battery", ip="198.51.100.9") == 429


def test_same_ip_with_other_usernames_is_limited_by_ip(owner: User) -> None:
    client = Client()
    for i in range(5):
        assert attempt(client, f"guess{i}", "wrong") == 200
    assert attempt(client, "owner", "correct-horse-battery") == 429


def test_forged_leading_forwarded_for_entries_do_not_dodge_the_limit(owner: User) -> None:
    client = Client()
    for i in range(5):
        assert attempt(client, f"u{i}", "wrong", ip=f"10.0.0.{i}, 203.0.113.5") == 200
    assert attempt(client, "owner", "correct-horse-battery", ip="10.9.9.9, 203.0.113.5") == 429


def test_success_below_the_limit_logs_in(owner: User) -> None:
    client = Client()
    for _ in range(4):
        attempt(client, "owner", "wrong")
    assert attempt(client, "owner", "correct-horse-battery", ip="198.51.100.7") == 302
    assert client.get("/admin/").status_code == 200


def test_password_validators_enforce_a_minimum_length() -> None:
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        validate_password("short1A!")

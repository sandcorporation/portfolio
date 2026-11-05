"""Admin 「운영 설정」 (#233): DB override > .env, shared snapshot, sealed secrets, call sites."""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from typing import Any

import pytest
from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client as HttpClient
from django.test import override_settings
from django.urls import reverse

from adapters import foresight as foresight_adapter
from adapters import notify
from content.models import RuntimeSetting
from services import proposals, runtime_settings
from services.runtime_settings import REGISTRY, InvalidSetting, UnknownSetting

Capture = Callable[..., AbstractContextManager[list[Callable[[], object]]]]

HOOK = "https://discord.com/api/webhooks/123/secret-token-abcd"
LIST_URL = "admin:content_runtimesetting_changelist"


@pytest.fixture(autouse=True)
def cache_table(db: None) -> Iterator[None]:
    call_command("createcachetable", verbosity=0)
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def commit(django_capture_on_commit_callbacks: Capture) -> Callable[[], Any]:
    """Run the write's on_commit callbacks (the snapshot rebuild) as a real commit would."""
    return lambda: django_capture_on_commit_callbacks(execute=True)


def edit_url(name: str) -> str:
    return reverse("admin:content_runtimesetting_edit", args=[name])


def test_empty_db_answers_env_values() -> None:
    for name in REGISTRY:
        assert runtime_settings.get(name) == getattr(settings, name)


def test_saved_value_is_seen_by_another_process_and_clear_goes_back(
    commit: Callable[[], Any],
) -> None:
    before = runtime_settings.get("FORESIGHT_API_URL")  # the shared snapshot is now cached
    with commit():
        runtime_settings.set_value("FORESIGHT_API_URL", "https://news.example/a", by="owner")
    # another process: no request memo, only the shared cache
    assert runtime_settings.get("FORESIGHT_API_URL") == "https://news.example/a"
    assert cache.get(runtime_settings.SNAPSHOT_KEY)["version"] == 1
    with commit():
        assert runtime_settings.clear("FORESIGHT_API_URL")
    assert runtime_settings.get("FORESIGHT_API_URL") == before == settings.FORESIGHT_API_URL


def test_request_scope_reads_the_shared_snapshot_once(monkeypatch: pytest.MonkeyPatch) -> None:
    reads: list[str] = []
    real_get = cache.get

    def counting_get(key: str, default: object = None) -> object:
        reads.append(key)
        return real_get(key, default)

    monkeypatch.setattr(cache, "get", counting_get)
    with runtime_settings.request_scope():
        runtime_settings.get("METRICS_SITE_KEY")
        runtime_settings.get("SUPPLIER_NAME")
    runtime_settings.get("SUPPLIER_NAME")
    assert reads.count(runtime_settings.SNAPSHOT_KEY) == 2


def test_lost_snapshot_is_rebuilt_from_the_db(commit: Callable[[], Any]) -> None:
    with commit():
        runtime_settings.set_value("SUPPLIER_NAME", "새 이름", by="owner")
    cache.delete(runtime_settings.SNAPSHOT_KEY)
    assert runtime_settings.get("SUPPLIER_NAME") == "새 이름"


def test_empty_override_switches_off_and_some_names_refuse_it(commit: Callable[[], Any]) -> None:
    with commit():
        runtime_settings.set_empty("METRICS_SNIPPET_URL", by="owner")
    assert runtime_settings.get("METRICS_SNIPPET_URL") == ""
    with pytest.raises(InvalidSetting):
        runtime_settings.set_empty("SUPPLIER_NAME", by="owner")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("FORESIGHT_API_URL", "ftp://news.example/a"),
        ("METRICS_API_URL", "not a url"),
        ("YOUTUBE_CHANNEL_ID", "channel"),
        ("METRICS_SITE_KEY", "Bad Key"),
        ("NAVER_SITE_VERIFICATION", "<meta>"),
        ("DISCORD_WEBHOOK_URL", "http://discord.example/plain-http-secret"),
        ("SUPPLIER_NAME", "두\n줄"),
    ],
)
def test_bad_values_are_refused_without_echoing_them(name: str, value: str) -> None:
    with pytest.raises(InvalidSetting) as info:
        runtime_settings.set_value(name, value, by="owner")
    assert value not in str(info.value)
    assert not RuntimeSetting.objects.exists()


def test_unknown_names_are_refused() -> None:
    with pytest.raises(UnknownSetting):
        runtime_settings.set_value("DB_PASSWORD", "x", by="owner")
    with pytest.raises(UnknownSetting):
        runtime_settings.get("DJANGO_SECRET_KEY")


def test_secret_is_sealed_shown_by_its_tail_and_kept_on_blank_save(
    commit: Callable[[], Any],
) -> None:
    with commit():
        runtime_settings.set_value("DISCORD_WEBHOOK_URL", HOOK, by="owner")
    stored = RuntimeSetting.objects.get(name="DISCORD_WEBHOOK_URL")
    assert HOOK not in stored.value and "secret-token" not in stored.value
    assert HOOK not in str(cache.get(runtime_settings.SNAPSHOT_KEY))
    assert HOOK not in repr(stored) and HOOK not in str(stored)
    assert runtime_settings.get("DISCORD_WEBHOOK_URL") == HOOK
    row = runtime_settings.row("DISCORD_WEBHOOK_URL")
    assert row.shown == "설정됨 · …abcd" and row.source == "DB"
    assert HOOK not in repr(row)
    assert runtime_settings.set_value("DISCORD_WEBHOOK_URL", "  ", by="owner") is False
    assert runtime_settings.get("DISCORD_WEBHOOK_URL") == HOOK


@override_settings(DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/env/env-1234")
def test_secret_that_no_longer_opens_falls_back_to_env(commit: Callable[[], Any]) -> None:
    with commit():
        runtime_settings.set_value("DISCORD_WEBHOOK_URL", HOOK, by="owner")
    with override_settings(SECRET_KEY="another-test-only-key"):
        assert runtime_settings.get("DISCORD_WEBHOOK_URL").endswith("env-1234")
        row = runtime_settings.row("DISCORD_WEBHOOK_URL")
    assert row.unreadable and "다시 넣어야 함" in row.shown


def test_foresight_calls_the_new_url_on_the_next_fetch(
    commit: Callable[[], Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[str] = []

    def fake_get_json(url: str, timeout: float) -> object:
        called.append(url)
        return {"items": []}

    monkeypatch.setattr(foresight_adapter, "_get_json", fake_get_json)
    foresight_adapter.set_gateway(None)  # the gateway the settings describe, not the fake
    foresight_adapter.fetch_recent(3)
    with commit():
        runtime_settings.set_value("FORESIGHT_API_URL", "https://news.example/new", by="owner")
    foresight_adapter.fetch_recent(3)  # the old URL's cached answer is not reused
    assert called[0].startswith(settings.FORESIGHT_API_URL)
    assert called[1].startswith("https://news.example/new?")


def test_notifier_supplier_and_shell_read_the_overrides(
    commit: Callable[[], Any], client: HttpClient
) -> None:
    with commit():
        runtime_settings.set_value("DISCORD_ALERTS_WEBHOOK_URL", HOOK, by="owner")
        runtime_settings.set_value("SUPPLIER_NAME", "새 공급자", by="owner")
        runtime_settings.set_value("GOOGLE_SITE_VERIFICATION", "g-from-admin", by="owner")
    notifier = notify.get_notifier()
    assert isinstance(notifier, notify.DiscordNotifier)
    assert notifier._url_for("alert") == HOOK
    assert proposals.supplier().name == "새 공급자"
    assert 'content="g-from-admin"' in client.get("/").content.decode()


def test_admin_page_lists_every_name_hides_secrets_and_is_not_stored(
    admin_client: HttpClient, commit: Callable[[], Any]
) -> None:
    with commit():
        runtime_settings.set_value("DISCORD_WEBHOOK_URL", HOOK, by="owner")
    response = admin_client.get(reverse(LIST_URL))
    page = response.content.decode()
    assert "no-store" in response["Cache-Control"]
    assert all(name in page for name in REGISTRY)
    assert HOOK not in page and "설정됨 · …abcd" in page
    edit = admin_client.get(edit_url("DISCORD_WEBHOOK_URL"))
    assert "no-store" in edit["Cache-Control"] and HOOK not in edit.content.decode()


def test_admin_save_empty_and_clear_are_logged_without_values(
    admin_client: HttpClient, commit: Callable[[], Any]
) -> None:
    with commit():
        admin_client.post(edit_url("DISCORD_WEBHOOK_URL"), {"op": "save", "value": HOOK})
        admin_client.post(edit_url("METRICS_SNIPPET_URL"), {"op": "empty"})
    assert runtime_settings.get("DISCORD_WEBHOOK_URL") == HOOK
    assert runtime_settings.get("METRICS_SNIPPET_URL") == ""
    assert RuntimeSetting.objects.get(name="DISCORD_WEBHOOK_URL").updated_by == "admin"
    with commit():
        admin_client.post(edit_url("DISCORD_WEBHOOK_URL"), {"op": "clear"})
    assert runtime_settings.get("DISCORD_WEBHOOK_URL") == settings.DISCORD_WEBHOOK_URL
    logs = list(LogEntry.objects.values_list("object_repr", "change_message"))
    assert len(logs) == 3
    assert all(HOOK not in repr_ + message for repr_, message in logs)


def test_admin_refuses_a_bad_value(admin_client: HttpClient) -> None:
    response = admin_client.post(
        edit_url("YOUTUBE_CHANNEL_ID"), {"op": "save", "value": "nope"}, follow=True
    )
    assert "채널 ID" in response.content.decode()
    assert not RuntimeSetting.objects.exists()


def test_admin_test_message_only_on_the_button(
    admin_client: HttpClient, commit: Callable[[], Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []

    def fake_send(url: str) -> int:
        sent.append(url)
        return 204

    monkeypatch.setattr("content.admin.send_test", fake_send)
    with commit():
        admin_client.post(edit_url("DISCORD_WEBHOOK_URL"), {"op": "save", "value": HOOK})
    assert sent == []
    response = admin_client.post(edit_url("DISCORD_WEBHOOK_URL"), {"op": "test"})
    page = response.content.decode()
    assert sent == [HOOK] and "HTTP 204" in page and HOOK not in page

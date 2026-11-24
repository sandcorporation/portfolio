"""Which Discord webhook a notification goes to: alerts vs activity, with fallback."""

import json
import urllib.request

import pytest
from django.test import override_settings

from adapters.notify import (
    NOTICE_TIMEOUT_SECONDS,
    TIMEOUT_SECONDS,
    DiscordNotifier,
    NoNotifier,
    Notification,
    discord_payload,
    get_notifier,
)


class _Resp:
    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *a: object) -> None:
        return None


@pytest.fixture
def posted(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    urls: list[str] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _Resp:
        urls.append(request.full_url)
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return urls


def test_default_severity_is_activity() -> None:
    assert Notification(title="t").severity == "activity"


@override_settings(
    DISCORD_WEBHOOK_URL="https://a/act", DISCORD_ALERTS_WEBHOOK_URL="https://a/alert"
)
def test_routes_by_severity(posted: list[str]) -> None:
    n = get_notifier()
    assert n.send(Notification(title="x"))
    assert n.send(Notification(title="y", severity="alert"))
    assert posted == ["https://a/act", "https://a/alert"]


@override_settings(DISCORD_WEBHOOK_URL="https://a/act", DISCORD_ALERTS_WEBHOOK_URL="")
def test_alert_falls_back_to_activity_webhook(posted: list[str]) -> None:
    assert get_notifier().send(Notification(title="y", severity="alert"))
    assert posted == ["https://a/act"]


@override_settings(DISCORD_WEBHOOK_URL="", DISCORD_ALERTS_WEBHOOK_URL="https://a/alert")
def test_activity_skipped_when_only_alerts_webhook(posted: list[str]) -> None:
    n = get_notifier()
    assert isinstance(n, DiscordNotifier)
    assert not n.send(Notification(title="x"))
    assert n.send(Notification(title="y", severity="alert"))
    assert posted == ["https://a/alert"]


@override_settings(
    DISCORD_WEBHOOK_URL="", DISCORD_ALERTS_WEBHOOK_URL="", ALERTS_NOTICE_WEBHOOK_URL=""
)
def test_nothing_configured_skips() -> None:
    assert isinstance(get_notifier(), NoNotifier)


# --- second alert destination (issue 26) ---

ALERT = Notification(title="백업 실패", text="본문", severity="alert")


@pytest.fixture
def bodies(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """url -> posted body; urls in `failing` raise, as if that destination were down."""
    got: dict[str, object] = {"failing": set()}

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _Resp:
        if request.full_url in got["failing"]:  # type: ignore[operator]
            raise OSError("down")
        assert isinstance(request.data, bytes)
        got[request.full_url] = json.loads(request.data)
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return got


@override_settings(
    DISCORD_WEBHOOK_URL="https://a/act",
    DISCORD_ALERTS_WEBHOOK_URL="https://a/alert",
    ALERTS_NOTICE_WEBHOOK_URL="https://b/notice",
)
def test_alert_goes_to_both_with_same_body(bodies: dict[str, object]) -> None:
    assert get_notifier().send(ALERT)
    assert bodies["https://a/alert"] == bodies["https://b/notice"] == discord_payload(ALERT)


@override_settings(
    DISCORD_WEBHOOK_URL="https://a/act",
    DISCORD_ALERTS_WEBHOOK_URL="https://a/alert",
    ALERTS_NOTICE_WEBHOOK_URL="",
)
def test_no_second_destination_is_discord_only(bodies: dict[str, object]) -> None:
    assert get_notifier().send(ALERT)
    assert set(bodies) == {"failing", "https://a/alert"}


@override_settings(
    DISCORD_WEBHOOK_URL="https://a/act",
    DISCORD_ALERTS_WEBHOOK_URL="",
    ALERTS_NOTICE_WEBHOOK_URL="https://b/notice",
)
def test_activity_does_not_go_to_second_destination(bodies: dict[str, object]) -> None:
    assert get_notifier().send(Notification(title="문의 접수"))
    assert set(bodies) == {"failing", "https://a/act"}


@override_settings(
    DISCORD_WEBHOOK_URL="",
    DISCORD_ALERTS_WEBHOOK_URL="https://a/alert",
    ALERTS_NOTICE_WEBHOOK_URL="https://b/notice",
)
def test_second_goes_when_discord_fails(bodies: dict[str, object]) -> None:
    bodies["failing"] = {"https://a/alert"}
    assert get_notifier().send(ALERT)
    assert bodies["https://b/notice"] == discord_payload(ALERT)


@override_settings(
    DISCORD_WEBHOOK_URL="",
    DISCORD_ALERTS_WEBHOOK_URL="https://a/alert",
    ALERTS_NOTICE_WEBHOOK_URL="https://b/notice",
)
def test_second_failure_does_not_break_discord_or_caller(
    bodies: dict[str, object], caplog: pytest.LogCaptureFixture
) -> None:
    bodies["failing"] = {"https://b/notice"}
    assert get_notifier().send(ALERT)
    assert bodies["https://a/alert"] == discord_payload(ALERT)
    assert "b/notice" not in caplog.text


@override_settings(
    DISCORD_WEBHOOK_URL="",
    DISCORD_ALERTS_WEBHOOK_URL="",
    ALERTS_NOTICE_WEBHOOK_URL="https://b/notice",
)
def test_second_destination_alone(bodies: dict[str, object]) -> None:
    n = get_notifier()
    assert isinstance(n, DiscordNotifier)
    assert not n.send(Notification(title="문의 접수"))
    assert n.send(ALERT)
    assert set(bodies) == {"failing", "https://b/notice"}


def test_second_destination_times_out_sooner() -> None:
    assert NOTICE_TIMEOUT_SECONDS <= TIMEOUT_SECONDS

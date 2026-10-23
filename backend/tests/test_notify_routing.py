"""Which Discord webhook a notification goes to: alerts vs activity, with fallback."""

import urllib.request

import pytest
from django.test import override_settings

from adapters.notify import DiscordNotifier, NoNotifier, Notification, get_notifier


class _Resp:
    def __enter__(self) -> "_Resp":
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


@override_settings(DISCORD_WEBHOOK_URL="", DISCORD_ALERTS_WEBHOOK_URL="")
def test_nothing_configured_skips() -> None:
    assert isinstance(get_notifier(), NoNotifier)

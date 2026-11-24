"""Owner alerts behind a narrow interface: a Discord webhook, plus a second alert destination.

A `Notification` is generic (title, optional text, labelled fields) so a new kind of event
(a customer opened a proposal, #18) is just another place that builds one; the adapter does not
know about inquiries. Sending never raises: a failed alert must not fail the request that caused
it. `send` returns whether the alert went out. The fake in `adapters/fake_notify.py` stands in
for tests.

Operational alerts (`severity="alert"`) also go, with the same Discord-shaped body, to a second
alert destination (`ALERTS_NOTICE_WEBHOOK_URL`, issue 26) when it is set. The two posts run side
by side and are independent: one failing or hanging does not stop or delay the other beyond its
own timeout. Neither URL is ever logged.
"""

import json
import logging
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal, Protocol

from services import runtime_settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5
NOTICE_TIMEOUT_SECONDS = 3  # the second alert destination: shorter than Discord's
# Discord's embed limits: title 256, description 4096, field name 256, field value 1024.
_TITLE_MAX = 256
_TEXT_MAX = 4096
_NAME_MAX = 256
_VALUE_MAX = 1024


@dataclass(frozen=True)
class Field:
    name: str
    value: str
    inline: bool = False


Severity = Literal["alert", "activity"]


@dataclass(frozen=True)
class Notification:
    """`severity` picks the channel: "alert" is an operational failure (#sandcorp-alerts),
    "activity" (default) is a visitor or customer event (#sandcorp-activity)."""

    title: str
    text: str = ""
    fields: tuple[Field, ...] = ()
    severity: Severity = "activity"


class Notifier(Protocol):
    def send(self, notification: Notification) -> bool: ...


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def discord_payload(notification: Notification) -> dict[str, object]:
    embed: dict[str, object] = {
        "title": _clip(notification.title, _TITLE_MAX),
        "fields": [
            {
                "name": _clip(f.name, _NAME_MAX) or "-",
                "value": _clip(f.value, _VALUE_MAX) or "-",
                "inline": f.inline,
            }
            for f in notification.fields[:25]
        ],
    }
    if notification.text:
        embed["description"] = _clip(notification.text, _TEXT_MAX)
    # Visitors write this text: never let it ping @everyone or a role.
    return {"embeds": [embed], "allowed_mentions": {"parse": []}}


def _post(url: str, payload: dict[str, object], timeout: float, what: str) -> bool:
    """POST JSON; never raises. Only the failure's type is logged, never the URL or its text."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "sandcorp-portfolio"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout):  # noqa: S310
            return True
    except Exception as e:  # noqa: BLE001 — an alert must never fail its caller
        logger.warning("%s failed: %s", what, type(e).__name__)
        return False


class DiscordNotifier:
    def __init__(self, activity_url: str, alerts_url: str = "", notice_url: str = "") -> None:
        self._activity_url = activity_url
        self._alerts_url = alerts_url
        self._notice_url = notice_url

    def _url_for(self, severity: Severity) -> str:
        if severity == "alert":
            return self._alerts_url or self._activity_url
        return self._activity_url

    def send(self, notification: Notification) -> bool:
        """True when the alert reached at least one destination."""
        payload = discord_payload(notification)
        posts = []
        if url := self._url_for(notification.severity):
            posts.append((url, TIMEOUT_SECONDS, "Discord alert"))
        if notification.severity == "alert" and self._notice_url:
            posts.append((self._notice_url, NOTICE_TIMEOUT_SECONDS, "second alert destination"))
        if not posts:
            return False
        if len(posts) == 1:
            url, timeout, what = posts[0]
            return _post(url, payload, timeout, what)
        with ThreadPoolExecutor(max_workers=len(posts)) as pool:
            futures = [pool.submit(_post, u, payload, t, w) for u, t, w in posts]
            return any([f.result() for f in futures])


class NoNotifier:
    """No webhook configured: alerts are skipped and the site works as before."""

    def send(self, notification: Notification) -> bool:
        return False


def get_notifier() -> Notifier:
    """Alerts go to DISCORD_ALERTS_WEBHOOK_URL, falling back to DISCORD_WEBHOOK_URL, and also to
    ALERTS_NOTICE_WEBHOOK_URL; activity goes to DISCORD_WEBHOOK_URL only. All empty: NoNotifier."""
    activity = runtime_settings.get("DISCORD_WEBHOOK_URL")
    alerts = runtime_settings.get("DISCORD_ALERTS_WEBHOOK_URL")
    notice = runtime_settings.get("ALERTS_NOTICE_WEBHOOK_URL")
    if not activity and not alerts and not notice:
        return NoNotifier()
    return DiscordNotifier(activity, alerts, notice)


def send_test(url: str) -> int | None:
    """Post one short test message to a webhook (admin 「시험 메시지 보내기」, #233).

    The HTTP status, or None when the request did not get an answer. Neither the URL nor the
    error text is logged or returned: the URL is the secret."""
    payload = {"content": "Sandcorp 운영 설정 시험 메시지", "allowed_mentions": {"parse": []}}
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "sandcorp-portfolio"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            status: int = response.status
            return status
    except urllib.error.HTTPError as e:
        return e.code
    except urllib.error.URLError, OSError, ValueError:
        return None

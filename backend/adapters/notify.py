"""Owner alerts behind a narrow interface: a Discord webhook.

A `Notification` is generic (title, optional text, labelled fields) so a new kind of event
(a customer opened a proposal, #18) is just another place that builds one; the adapter does not
know about inquiries. Sending never raises: a failed alert must not fail the request that caused
it. `send` returns whether the alert went out. The fake in `adapters/fake_notify.py` stands in
for tests.
"""

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Literal, Protocol

from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5
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


class DiscordNotifier:
    def __init__(self, activity_url: str, alerts_url: str = "") -> None:
        self._activity_url = activity_url
        self._alerts_url = alerts_url

    def _url_for(self, severity: Severity) -> str:
        if severity == "alert":
            return self._alerts_url or self._activity_url
        return self._activity_url

    def send(self, notification: Notification) -> bool:
        url = self._url_for(notification.severity)
        if not url:
            return False
        request = urllib.request.Request(
            url,
            data=json.dumps(discord_payload(notification)).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "sandcorp-portfolio"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):  # noqa: S310
                return True
        except (urllib.error.URLError, OSError, ValueError):
            logger.warning("Discord alert failed", exc_info=True)
            return False


class NoNotifier:
    """No webhook configured: alerts are skipped and the site works as before."""

    def send(self, notification: Notification) -> bool:
        return False


def get_notifier() -> Notifier:
    """Alerts go to DISCORD_ALERTS_WEBHOOK_URL, falling back to DISCORD_WEBHOOK_URL; activity
    goes to DISCORD_WEBHOOK_URL. Both empty: NoNotifier."""
    activity: str = settings.DISCORD_WEBHOOK_URL
    alerts: str = settings.DISCORD_ALERTS_WEBHOOK_URL
    if not activity and not alerts:
        return NoNotifier()
    return DiscordNotifier(activity, alerts)

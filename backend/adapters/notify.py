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
from typing import Protocol

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


@dataclass(frozen=True)
class Notification:
    title: str
    text: str = ""
    fields: tuple[Field, ...] = ()


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
    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url

    def send(self, notification: Notification) -> bool:
        request = urllib.request.Request(
            self._url,
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
    url: str = settings.DISCORD_WEBHOOK_URL
    return DiscordNotifier(url) if url else NoNotifier()

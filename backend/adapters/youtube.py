"""YouTube oEmbed: a Short's title without an API key (issue 207).

`GET https://www.youtube.com/oembed?url=https://www.youtube.com/shorts/<id>&format=json` answers
`{"title": ..., "author_name": ..., "thumbnail_url": ...}`. Registering a Short must never fail
because YouTube is slow or down: one request with a 3-second timeout, and on any failure an empty
title plus one log line (the home page then says 「Sandcorp 쇼츠」).

Only registration calls this (services/shorts.py); the home page never does. Tests swap the
gateway with `set_gateway(FakeYoutube())` (`adapters/fake_youtube.py`, autouse in conftest).
"""

import json
import logging
import urllib.error
import urllib.request
from typing import Protocol
from urllib.parse import urlencode

from django.conf import settings

logger = logging.getLogger(__name__)

TITLE_MAX = 200  # Short.title's max_length


class YoutubeUnavailable(Exception):
    """oEmbed could not be read (unreachable, error status, bad JSON or switched off)."""


class YoutubeGateway(Protocol):
    def title(self, youtube_id: str) -> str:
        """The video's title from oEmbed. Raises YoutubeUnavailable."""
        ...


def short_url(youtube_id: str) -> str:
    return f"https://www.youtube.com/shorts/{youtube_id}"


def parse_title(payload: object) -> str:
    title = payload.get("title") if isinstance(payload, dict) else None
    if not isinstance(title, str) or not title.strip():
        raise YoutubeUnavailable("응답에 title이 없음")
    return title.strip()[:TITLE_MAX]


class HttpYoutube:
    def __init__(self, oembed_url: str, timeout_seconds: float) -> None:
        self._oembed_url = oembed_url
        self._timeout = timeout_seconds

    def title(self, youtube_id: str) -> str:
        query = urlencode({"url": short_url(youtube_id), "format": "json"})
        request = urllib.request.Request(
            f"{self._oembed_url}?{query}",
            headers={"Accept": "application/json", "User-Agent": "sandcorp-portfolio"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                body: bytes = response.read(200_000)
        except urllib.error.HTTPError as e:
            raise YoutubeUnavailable(f"HTTP {e.code}") from None
        except (urllib.error.URLError, OSError) as e:
            raise YoutubeUnavailable(f"닿지 못함: {e}") from None
        try:
            payload: object = json.loads(body)
        except ValueError:
            raise YoutubeUnavailable("JSON이 아닌 응답") from None
        return parse_title(payload)


class DisabledYoutube:
    """YOUTUBE_OEMBED_URL is empty: titles are never looked up."""

    def title(self, youtube_id: str) -> str:
        raise YoutubeUnavailable("꺼져 있음")


_gateway: YoutubeGateway | None = None


def set_gateway(gateway: YoutubeGateway | None) -> None:
    """Replace the gateway (tests); None goes back to the one the settings describe."""
    global _gateway
    _gateway = gateway


def get_gateway() -> YoutubeGateway:
    if _gateway is not None:
        return _gateway
    url: str = settings.YOUTUBE_OEMBED_URL
    if not url:
        return DisabledYoutube()
    return HttpYoutube(url, settings.YOUTUBE_TIMEOUT_SECONDS)


def fetch_title(youtube_id: str) -> str:
    """The title, or "" when oEmbed cannot be read (logged, never raised)."""
    try:
        return get_gateway().title(youtube_id)
    except YoutubeUnavailable as e:
        logger.warning("YouTube oEmbed 제목을 못 읽음 (%s): %s", youtube_id, e)
        return ""

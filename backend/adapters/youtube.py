"""YouTube without an API key: a Short's title (oEmbed, issue 207) and the channel's newest
videos (the channel's Atom feed, issue 211).

`GET https://www.youtube.com/oembed?url=https://www.youtube.com/shorts/<id>&format=json` answers
`{"title": ..., "author_name": ..., "thumbnail_url": ...}`. Registering a Short must never fail
because YouTube is slow or down: one request with a 3-second timeout, and on any failure an empty
title plus one log line (the home page then says 「Sandcorp 쇼츠」).

The channel feed (`https://www.youtube.com/feeds/videos.xml?channel_id=<YOUTUBE_CHANNEL_ID>`, the
15 newest uploads) is read by `services/shorts.sync_from_channel()` from the worker loop: 3-second
timeout, parsed with the standard library after refusing any DTD (an Atom feed has none, so no
entity can be declared or expanded). On any failure: an empty list and one log line. The feed does
not say which videos are Shorts; `is_short()` asks `youtube.com/shorts/<id>` once without
following redirects (200: a Short, 3xx: a regular video sent to /watch) and says True when it
cannot tell, since the channel uploads Shorts only.

Only registration and the worker call this (services/shorts.py); the home page never does.
Tests swap the gateway with `set_gateway(FakeYoutube())` (`adapters/fake_youtube.py`, autouse in
conftest).
"""

import json
import logging
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlencode

from django.conf import settings

logger = logging.getLogger(__name__)

TITLE_MAX = 200  # Short.title's max_length


FEED_BYTES_MAX = 2_000_000
_ATOM = "{http://www.w3.org/2005/Atom}"
_YT = "{http://www.youtube.com/xml/schemas/2015}"


class YoutubeUnavailable(Exception):
    """YouTube could not be read (unreachable, error status, bad JSON/XML or switched off)."""


@dataclass(frozen=True)
class FeedEntry:
    youtube_id: str
    title: str
    published: datetime


class YoutubeGateway(Protocol):
    def title(self, youtube_id: str) -> str:
        """The video's title from oEmbed. Raises YoutubeUnavailable."""
        ...

    def channel_feed(self) -> bytes:
        """The channel's Atom feed as it came. Raises YoutubeUnavailable."""
        ...

    def is_short(self, youtube_id: str) -> bool:
        """True for a Short, False for a regular video. Raises YoutubeUnavailable."""
        ...


def short_url(youtube_id: str) -> str:
    return f"https://www.youtube.com/shorts/{youtube_id}"


def parse_feed(body: bytes) -> list[FeedEntry]:
    """The entries of a channel's Atom feed, in feed order; entries missing a field are skipped.
    Raises YoutubeUnavailable on anything that is not a well-formed feed without a DTD."""
    if b"<!DOCTYPE" in body or b"<!ENTITY" in body:
        raise YoutubeUnavailable("DTD가 있는 피드")
    try:
        root = ET.fromstring(body)  # noqa: S314 — no DTD (checked above), so no entities
    except ET.ParseError as e:
        raise YoutubeUnavailable(f"XML이 아닌 응답: {e}") from None
    if root.tag != f"{_ATOM}feed":
        raise YoutubeUnavailable("Atom 피드가 아님")
    entries: list[FeedEntry] = []
    for entry in root.iter(f"{_ATOM}entry"):
        video_id = (entry.findtext(f"{_YT}videoId") or "").strip()
        title = (entry.findtext(f"{_ATOM}title") or "").strip()[:TITLE_MAX]
        published_text = (entry.findtext(f"{_ATOM}published") or "").strip()
        try:
            published = datetime.fromisoformat(published_text)
        except ValueError:
            continue
        if len(video_id) != 11 or published.tzinfo is None:
            continue
        entries.append(FeedEntry(youtube_id=video_id, title=title, published=published))
    return entries


def parse_title(payload: object) -> str:
    title = payload.get("title") if isinstance(payload, dict) else None
    if not isinstance(title, str) or not title.strip():
        raise YoutubeUnavailable("응답에 title이 없음")
    return title.strip()[:TITLE_MAX]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(  # noqa: PLR0913 — urllib's signature
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        return None  # urllib then raises HTTPError with the 3xx code


class HttpYoutube:
    def __init__(
        self, oembed_url: str, feed_url: str, channel_id: str, timeout_seconds: float
    ) -> None:
        self._oembed_url = oembed_url
        self._feed_url = feed_url
        self._channel_id = channel_id
        self._timeout = timeout_seconds

    def _get(self, url: str, accept: str, limit: int) -> bytes:
        request = urllib.request.Request(
            url, headers={"Accept": accept, "User-Agent": "sandcorp-portfolio"}
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                body: bytes = response.read(limit)
        except urllib.error.HTTPError as e:
            raise YoutubeUnavailable(f"HTTP {e.code}") from None
        except (urllib.error.URLError, OSError) as e:
            raise YoutubeUnavailable(f"닿지 못함: {e}") from None
        return body

    def title(self, youtube_id: str) -> str:
        if not self._oembed_url:
            raise YoutubeUnavailable("꺼져 있음")
        query = urlencode({"url": short_url(youtube_id), "format": "json"})
        body = self._get(f"{self._oembed_url}?{query}", "application/json", 200_000)
        try:
            payload: object = json.loads(body)
        except ValueError:
            raise YoutubeUnavailable("JSON이 아닌 응답") from None
        return parse_title(payload)

    def channel_feed(self) -> bytes:
        if not self._feed_url or not self._channel_id:
            raise YoutubeUnavailable("꺼져 있음")
        query = urlencode({"channel_id": self._channel_id})
        return self._get(f"{self._feed_url}?{query}", "application/atom+xml", FEED_BYTES_MAX)

    def is_short(self, youtube_id: str) -> bool:
        request = urllib.request.Request(
            short_url(youtube_id), method="HEAD", headers={"User-Agent": "sandcorp-portfolio"}
        )
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(request, timeout=self._timeout) as response:
                status: int = response.status
        except urllib.error.HTTPError as e:
            if 300 <= e.code < 400:
                return False
            raise YoutubeUnavailable(f"HTTP {e.code}") from None
        except (urllib.error.URLError, OSError) as e:
            raise YoutubeUnavailable(f"닿지 못함: {e}") from None
        if status == 200:
            return True
        raise YoutubeUnavailable(f"HTTP {status}")


_gateway: YoutubeGateway | None = None


def set_gateway(gateway: YoutubeGateway | None) -> None:
    """Replace the gateway (tests); None goes back to the one the settings describe."""
    global _gateway
    _gateway = gateway


def get_gateway() -> YoutubeGateway:
    if _gateway is not None:
        return _gateway
    return HttpYoutube(
        settings.YOUTUBE_OEMBED_URL,
        settings.YOUTUBE_FEED_URL,
        settings.YOUTUBE_CHANNEL_ID,
        settings.YOUTUBE_TIMEOUT_SECONDS,
    )


def fetch_title(youtube_id: str) -> str:
    """The title, or "" when oEmbed cannot be read (logged, never raised)."""
    try:
        return get_gateway().title(youtube_id)
    except YoutubeUnavailable as e:
        logger.warning("YouTube oEmbed 제목을 못 읽음 (%s): %s", youtube_id, e)
        return ""


def fetch_channel_feed() -> list[FeedEntry]:
    """The channel's newest videos, or [] when the feed cannot be read (logged, never raised)."""
    try:
        return parse_feed(get_gateway().channel_feed())
    except YoutubeUnavailable as e:
        logger.warning("YouTube 채널 피드를 못 읽음: %s", e)
        return []


def check_is_short(youtube_id: str) -> bool:
    """Whether the video is a Short; True when YouTube cannot tell us (logged)."""
    try:
        return get_gateway().is_short(youtube_id)
    except YoutubeUnavailable as e:
        logger.warning("YouTube 쇼츠 여부를 못 읽음 (%s), 쇼츠로 봄: %s", youtube_id, e)
        return True

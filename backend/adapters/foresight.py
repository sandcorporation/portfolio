"""Foresight (news.sandcorp.co.kr) recent articles, read from the news site's public JSON.

`GET {FORESIGHT_API_URL}?limit=N` answers `{"items": [{slug, title, summary, category: {name,
slug}, image_url, published_at, url, ...}], "site": {...}}` (AI-Trend-News #73). The home page
shows them, so a slow or broken news site must never break ours: one request with a 3-second
timeout, the answer cached 10 minutes, and on failure the last good answer (kept 24 hours) or an
empty list plus one log line.

Tests swap the gateway with `set_gateway(FakeForesight())` (`adapters/fake_foresight.py`).
"""

import json
import logging
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_SECONDS = 10 * 60
LAST_GOOD_SECONDS = 24 * 60 * 60
MAX_LIMIT = 20


@dataclass(frozen=True)
class ForesightArticle:
    slug: str
    title: str
    summary: str
    category: str  # the category's display name ("" when the article has none)
    image_url: str
    published_at: datetime
    url: str


class ForesightUnavailable(Exception):
    """The news site could not be read (unreachable, error status, bad JSON or switched off)."""


class ForesightGateway(Protocol):
    def recent(self, limit: int) -> list[ForesightArticle]:
        """The newest `limit` published articles. Raises ForesightUnavailable."""
        ...


def parse_items(payload: object) -> list[ForesightArticle]:
    """Articles from the endpoint's JSON body; raises ForesightUnavailable on a wrong shape."""
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ForesightUnavailable("응답에 items 목록이 없음")
    articles: list[ForesightArticle] = []
    for raw in items:
        if not isinstance(raw, dict):
            raise ForesightUnavailable("items 항목이 객체가 아님")
        category = raw.get("category")
        try:
            articles.append(
                ForesightArticle(
                    slug=str(raw["slug"]),
                    title=str(raw["title"]),
                    summary=str(raw.get("summary") or ""),
                    category=str(category.get("name") or "")
                    if isinstance(category, dict)
                    else str(category or ""),
                    image_url=str(raw.get("image_url") or ""),
                    published_at=datetime.fromisoformat(str(raw["published_at"])),
                    url=str(raw["url"]),
                )
            )
        except (KeyError, ValueError) as e:
            raise ForesightUnavailable(f"items 항목 모양이 다름: {e}") from None
    return articles


class HttpForesight:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._base_url = base_url
        self._timeout = timeout_seconds

    def recent(self, limit: int) -> list[ForesightArticle]:
        sep = "&" if "?" in self._base_url else "?"
        request = urllib.request.Request(
            f"{self._base_url}{sep}{urlencode({'limit': limit})}",
            headers={"Accept": "application/json", "User-Agent": "sandcorp-portfolio"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                body: bytes = response.read(1_000_000)
        except urllib.error.HTTPError as e:
            raise ForesightUnavailable(f"HTTP {e.code}") from None
        except (urllib.error.URLError, OSError) as e:
            raise ForesightUnavailable(f"닿지 못함: {e}") from None
        try:
            payload: object = json.loads(body)
        except ValueError:
            raise ForesightUnavailable("JSON이 아닌 응답") from None
        return parse_items(payload)


class DisabledForesight:
    """FORESIGHT_API_URL is empty: the section is switched off."""

    def recent(self, limit: int) -> list[ForesightArticle]:
        return []


_gateway: ForesightGateway | None = None


def set_gateway(gateway: ForesightGateway | None) -> None:
    """Replace the gateway (tests); None goes back to the one the settings describe."""
    global _gateway
    _gateway = gateway


def get_gateway() -> ForesightGateway:
    if _gateway is not None:
        return _gateway
    url: str = settings.FORESIGHT_API_URL
    if not url:
        return DisabledForesight()
    return HttpForesight(url, settings.FORESIGHT_TIMEOUT_SECONDS)


def _key(limit: int) -> str:
    return f"foresight:recent:{limit}"


def _last_good_key(limit: int) -> str:
    return f"foresight:last-good:{limit}"


def _dump(articles: list[ForesightArticle]) -> list[dict[str, str]]:
    return [{**asdict(a), "published_at": a.published_at.isoformat()} for a in articles]


def _load(rows: object) -> list[ForesightArticle] | None:
    if not isinstance(rows, list):
        return None
    try:
        return parse_items({"items": rows})
    except ForesightUnavailable:
        return None


def fetch_recent(limit: int = 5) -> list[ForesightArticle]:
    """The newest Foresight articles for the home page, never raising.

    Fresh answers are cached 10 minutes. When the news site fails, the last good answer
    (24 hours) is served again — and re-cached for 10 minutes so a dead site is not asked on
    every page view — or an empty list."""
    limit = max(1, min(limit, MAX_LIMIT))
    cached = _load(cache.get(_key(limit)))
    if cached is not None:
        return cached
    try:
        articles = get_gateway().recent(limit)[:limit]
    except ForesightUnavailable as e:
        logger.warning("Foresight 최근 기사를 받지 못함: %s", e)
        articles = _load(cache.get(_last_good_key(limit))) or []
        cache.set(_key(limit), _dump(articles), CACHE_SECONDS)
        return articles
    rows = _dump(articles)
    cache.set(_key(limit), rows, CACHE_SECONDS)
    cache.set(_last_good_key(limit), rows, LAST_GOOD_SECONDS)
    return articles

"""Foresight (news.sandcorp.co.kr) recent articles, read from the news site's public JSON.

`GET {FORESIGHT_API_URL}?limit=N&commentary=true` (only published articles with a public AI
commentary, AI-Trend-News #82; an older news site ignores the flag)
answers `{"items": [{slug, title, summary, category: {name,
slug}, image_url, published_at, url, ...}], "site": {...}}` (AI-Trend-News #73). The home page
shows them, so a slow or broken news site must never break ours: one request with a 3-second
timeout, the answer cached 10 minutes, and on failure the last good answer (kept 24 hours) or an
empty list plus one log line.

`GET {FORESIGHT_STATS_URL}` answers `{"articles_per_day_7d", "articles_total", "published_since",
"predictions": {"hit_rate"}}` (AI-Trend-News #77); `fetch_stats()` reads it the same way (3 s,
10 minutes, the last good answer 24 hours, else None). The home page uses only
`articles_per_day_7d`.

Tests swap the gateway with `set_gateway(FakeForesight())` (`adapters/fake_foresight.py`).
"""

import hashlib
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

from services import runtime_settings

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


@dataclass(frozen=True)
class ForesightStats:
    articles_per_day_7d: float
    articles_total: int | None
    published_since: str  # "" when the answer has none
    hit_rate: float | None  # predictions.hit_rate


class ForesightUnavailable(Exception):
    """The news site could not be read (unreachable, error status, bad JSON or switched off)."""


class ForesightGateway(Protocol):
    def recent(self, limit: int) -> list[ForesightArticle]:
        """The newest `limit` published articles that carry a public AI commentary
        (`commentary=true`). Raises ForesightUnavailable."""
        ...

    def stats(self) -> ForesightStats | None:
        """The aggregate numbers; None when switched off. Raises ForesightUnavailable."""
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


def parse_stats(payload: object) -> ForesightStats:
    """The stats endpoint's JSON body; raises ForesightUnavailable on a wrong shape."""
    if not isinstance(payload, dict):
        raise ForesightUnavailable("stats 응답이 객체가 아님")
    per_day = payload.get("articles_per_day_7d")
    if isinstance(per_day, bool) or not isinstance(per_day, int | float) or per_day < 0:
        raise ForesightUnavailable("articles_per_day_7d 가 숫자가 아님")
    total = payload.get("articles_total")
    predictions = payload.get("predictions")
    hit_rate = predictions.get("hit_rate") if isinstance(predictions, dict) else None
    since = payload.get("published_since")
    return ForesightStats(
        articles_per_day_7d=float(per_day),
        articles_total=total if isinstance(total, int) and not isinstance(total, bool) else None,
        published_since=since if isinstance(since, str) else "",
        hit_rate=float(hit_rate)
        if isinstance(hit_rate, int | float) and not isinstance(hit_rate, bool)
        else None,
    )


def _get_json(url: str, timeout: float) -> object:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "sandcorp-portfolio"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body: bytes = response.read(1_000_000)
    except urllib.error.HTTPError as e:
        raise ForesightUnavailable(f"HTTP {e.code}") from None
    except (urllib.error.URLError, OSError) as e:
        raise ForesightUnavailable(f"닿지 못함: {e}") from None
    try:
        payload: object = json.loads(body)
    except ValueError:
        raise ForesightUnavailable("JSON이 아닌 응답") from None
    return payload


class HttpForesight:
    """An empty URL switches that one read off (articles: no rows; stats: None)."""

    def __init__(self, base_url: str, timeout_seconds: float, stats_url: str = "") -> None:
        self._base_url = base_url
        self._stats_url = stats_url
        self._timeout = timeout_seconds

    def stats(self) -> ForesightStats | None:
        if not self._stats_url:
            return None
        return parse_stats(_get_json(self._stats_url, self._timeout))

    def recent(self, limit: int) -> list[ForesightArticle]:
        if not self._base_url:
            return []
        sep = "&" if "?" in self._base_url else "?"
        url = f"{self._base_url}{sep}{urlencode({'limit': limit, 'commentary': 'true'})}"
        return parse_items(_get_json(url, self._timeout))


class DisabledForesight:
    """FORESIGHT_API_URL and FORESIGHT_STATS_URL are both empty: Foresight is switched off."""

    def recent(self, limit: int) -> list[ForesightArticle]:
        return []

    def stats(self) -> ForesightStats | None:
        return None


_gateway: ForesightGateway | None = None


def set_gateway(gateway: ForesightGateway | None) -> None:
    """Replace the gateway (tests); None goes back to the one the settings describe."""
    global _gateway
    _gateway = gateway


def get_gateway() -> ForesightGateway:
    if _gateway is not None:
        return _gateway
    url = runtime_settings.get("FORESIGHT_API_URL")
    stats_url = runtime_settings.get("FORESIGHT_STATS_URL")
    if not url and not stats_url:
        return DisabledForesight()
    return HttpForesight(url, settings.FORESIGHT_TIMEOUT_SECONDS, stats_url)


def _tag(setting: str) -> str:
    """The URL in force, hashed into the cache keys: a URL changed in the admin (#233) is
    never answered from the old site's cache."""
    return hashlib.sha256(runtime_settings.get(setting).encode()).hexdigest()[:10]


def _key(limit: int) -> str:
    return f"foresight:recent:commentary:{limit}:{_tag('FORESIGHT_API_URL')}"


def _last_good_key(limit: int) -> str:
    return f"foresight:last-good:commentary:{limit}:{_tag('FORESIGHT_API_URL')}"


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


def _stats_key() -> str:
    return f"foresight:stats:{_tag('FORESIGHT_STATS_URL')}"


def _stats_last_good_key() -> str:
    return f"foresight:stats-last-good:{_tag('FORESIGHT_STATS_URL')}"


def _dump_stats(stats: ForesightStats | None) -> dict[str, object]:
    if stats is None:
        return {"stats": None}
    return {  # the endpoint's own shape, so `parse_stats` reads it back
        "stats": {
            "articles_per_day_7d": stats.articles_per_day_7d,
            "articles_total": stats.articles_total,
            "published_since": stats.published_since,
            "predictions": {"hit_rate": stats.hit_rate},
        }
    }


def _load_stats(row: object) -> tuple[bool, ForesightStats | None]:
    """(found, stats) from a cached `{"stats": {...} | None}`."""
    if not isinstance(row, dict) or "stats" not in row:
        return False, None
    try:
        return True, parse_stats(row["stats"]) if row["stats"] is not None else None
    except ForesightUnavailable:
        return False, None


def fetch_stats() -> ForesightStats | None:
    """The Foresight aggregate numbers for the home page's evidence row, never raising.

    Same rules as `fetch_recent`: 10 minutes cached; on failure the last good answer (24 hours,
    re-cached 10 minutes) or None."""
    found, cached = _load_stats(cache.get(_stats_key()))
    if found:
        return cached
    try:
        stats = get_gateway().stats()
    except ForesightUnavailable as e:
        logger.warning("Foresight 통계를 받지 못함: %s", e)
        _, stats = _load_stats(cache.get(_stats_last_good_key()))
        cache.set(_stats_key(), _dump_stats(stats), CACHE_SECONDS)
        return stats
    cache.set(_stats_key(), _dump_stats(stats), CACHE_SECONDS)
    if stats is not None:
        cache.set(_stats_last_good_key(), _dump_stats(stats), LAST_GOOD_SECONDS)
    return stats

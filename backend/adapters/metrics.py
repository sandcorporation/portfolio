"""Visit counts of the four sites, read from sandcorp-metrics' public totals (#81).

`GET {METRICS_API_URL}` answers `{"sites": [{key, name, total_visitors, total_pageviews,
today_visitors, today_pageviews, live_visitors, since}], "total": {same fields}, "generated_at"}`
(sandcorporation/sandcorp-metrics#4). The home page shows them, so a slow or broken metrics
service must never break ours: one request with a 3-second timeout, the answer cached 60
seconds, and on failure the last good answer (kept 24 hours) or None plus one log line.

Tests swap the gateway with `set_gateway(FakeMetrics())` (`adapters/fake_metrics.py`).
"""

import json
import logging
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Protocol

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_SECONDS = 60
LAST_GOOD_SECONDS = 24 * 60 * 60
_KEY = "metrics:stats"
_LAST_GOOD_KEY = "metrics:last-good"
_MISSING = "missing"  # cached for CACHE_SECONDS when the service failed and nothing good is kept


@dataclass(frozen=True)
class SiteStats:
    key: str
    name: str
    total_visitors: int
    total_pageviews: int
    today_visitors: int
    today_pageviews: int
    live_visitors: int  # people on the site right now
    since: str  # ISO 8601 of the first count ("" when unknown)


@dataclass(frozen=True)
class Stats:
    sites: list[SiteStats]
    total: SiteStats  # all sites together
    generated_at: str

    def site(self, key: str) -> SiteStats | None:
        return next((s for s in self.sites if s.key == key), None)


class MetricsUnavailable(Exception):
    """The metrics service could not be read (unreachable, error status, bad JSON)."""


class MetricsGateway(Protocol):
    def stats(self) -> Stats | None:
        """The current counts; None when switched off. Raises MetricsUnavailable."""
        ...


def _count(raw: dict[str, object], field: str) -> int:
    value = raw.get(field, 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise MetricsUnavailable(f"{field}가 정수가 아님")
    return value


def parse_site(raw: object) -> SiteStats:
    if not isinstance(raw, dict):
        raise MetricsUnavailable("사이트 항목이 객체가 아님")
    try:
        return SiteStats(
            key=str(raw.get("key") or ""),
            name=str(raw.get("name") or ""),
            total_visitors=_count(raw, "total_visitors"),
            total_pageviews=_count(raw, "total_pageviews"),
            today_visitors=_count(raw, "today_visitors"),
            today_pageviews=_count(raw, "today_pageviews"),
            live_visitors=_count(raw, "live_visitors"),
            since=str(raw.get("since") or ""),
        )
    except (TypeError, ValueError) as e:
        raise MetricsUnavailable(f"사이트 항목 모양이 다름: {e}") from None


def parse_stats(payload: object) -> Stats:
    """Stats from the endpoint's JSON body; raises MetricsUnavailable on a wrong shape."""
    if not isinstance(payload, dict):
        raise MetricsUnavailable("응답이 객체가 아님")
    sites = payload.get("sites")
    if not isinstance(sites, list) or "total" not in payload:
        raise MetricsUnavailable("응답에 sites·total이 없음")
    return Stats(
        sites=[parse_site(s) for s in sites],
        total=parse_site(payload["total"]),
        generated_at=str(payload.get("generated_at") or ""),
    )


class HttpMetrics:
    def __init__(self, url: str, timeout_seconds: float) -> None:
        self._url = url
        self._timeout = timeout_seconds

    def stats(self) -> Stats | None:
        request = urllib.request.Request(
            self._url,
            headers={"Accept": "application/json", "User-Agent": "sandcorp-portfolio"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                body: bytes = response.read(1_000_000)
        except urllib.error.HTTPError as e:
            raise MetricsUnavailable(f"HTTP {e.code}") from None
        except (urllib.error.URLError, OSError) as e:
            raise MetricsUnavailable(f"닿지 못함: {e}") from None
        try:
            payload: object = json.loads(body)
        except ValueError:
            raise MetricsUnavailable("JSON이 아닌 응답") from None
        return parse_stats(payload)


class DisabledMetrics:
    """METRICS_API_URL is empty: the numbers are switched off."""

    def stats(self) -> Stats | None:
        return None


_gateway: MetricsGateway | None = None


def set_gateway(gateway: MetricsGateway | None) -> None:
    """Replace the gateway (tests); None goes back to the one the settings describe."""
    global _gateway
    _gateway = gateway


def get_gateway() -> MetricsGateway:
    if _gateway is not None:
        return _gateway
    url: str = settings.METRICS_API_URL
    if not url:
        return DisabledMetrics()
    return HttpMetrics(url, settings.METRICS_TIMEOUT_SECONDS)


def _load(row: object) -> Stats | None:
    if not isinstance(row, dict):
        return None
    try:
        return parse_stats(row)
    except MetricsUnavailable:
        return None


def fetch_stats() -> Stats | None:
    """The counts for the home page, never raising; None means "show no numbers".

    Fresh answers are cached 60 seconds. When the service fails, the last good answer (24 hours)
    is served again — and re-cached for 60 seconds so a dead service is not asked on every page
    view — or None."""
    cached = cache.get(_KEY)
    if cached == _MISSING:
        return None
    stats = _load(cached)
    if stats is not None:
        return stats
    try:
        stats = get_gateway().stats()
    except MetricsUnavailable as e:
        logger.warning("방문 메트릭을 받지 못함: %s", e)
        stats = _load(cache.get(_LAST_GOOD_KEY))
        cache.set(_KEY, asdict(stats) if stats else _MISSING, CACHE_SECONDS)
        return stats
    if stats is None:  # switched off
        return None
    cache.set(_KEY, asdict(stats), CACHE_SECONDS)
    cache.set(_LAST_GOOD_KEY, asdict(stats), LAST_GOOD_SECONDS)
    return stats

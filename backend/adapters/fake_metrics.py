"""MetricsGateway for tests: serves `data`, counts calls and can fail on demand."""

from dataclasses import dataclass, field

from adapters.metrics import MetricsUnavailable, SiteStats, Stats


def sample_site(key: str, n: int) -> SiteStats:
    return SiteStats(
        key=key,
        name=key,
        total_visitors=n * 1000 + 234,
        total_pageviews=n * 3000,
        today_visitors=n * 10 + 2,
        today_pageviews=n * 30,
        live_visitors=n % 3,
        since="2026-10-01T00:00:00+09:00",
    )


def sample_stats() -> Stats:
    sites = [
        sample_site(k, n) for n, k in enumerate(["codemit", "daypage", "foresight", "sandcorp"], 1)
    ]
    total = SiteStats(
        key="total",
        name="전체",
        total_visitors=sum(s.total_visitors for s in sites),
        total_pageviews=sum(s.total_pageviews for s in sites),
        today_visitors=sum(s.today_visitors for s in sites),
        today_pageviews=sum(s.today_pageviews for s in sites),
        live_visitors=sum(s.live_visitors for s in sites),
        since="2026-10-01T00:00:00+09:00",
    )
    return Stats(sites=sites, total=total, generated_at="2026-10-23T12:00:00+09:00")


@dataclass
class FakeMetrics:
    data: Stats = field(default_factory=sample_stats)
    failing: bool = False
    calls: int = 0

    def stats(self) -> Stats | None:
        self.calls += 1
        if self.failing:
            raise MetricsUnavailable("가짜 metrics 장애")
        return self.data

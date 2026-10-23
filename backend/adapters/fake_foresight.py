"""ForesightGateway for tests: serves `articles`, counts calls and can fail on demand."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from adapters.foresight import ForesightArticle, ForesightUnavailable

SEOUL = ZoneInfo("Asia/Seoul")


def sample_article(n: int) -> ForesightArticle:
    return ForesightArticle(
        slug=f"article-{n}",
        title=f"기사 {n}",
        summary=f"요약 {n}",
        category="모델",
        image_url=f"https://img.example/{n}.jpg",
        published_at=datetime(2026, 10, 23, 9, 0, tzinfo=SEOUL) - timedelta(hours=n),
        url=f"https://news.sandcorp.co.kr/a/article-{n}",
    )


@dataclass
class FakeForesight:
    articles: list[ForesightArticle] = field(
        default_factory=lambda: [sample_article(n) for n in range(1, 8)]
    )
    failing: bool = False
    calls: list[int] = field(default_factory=list)

    def recent(self, limit: int) -> list[ForesightArticle]:
        self.calls.append(limit)
        if self.failing:
            raise ForesightUnavailable("가짜 Foresight 장애")
        return self.articles[:limit]

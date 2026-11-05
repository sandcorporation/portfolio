"""Foresight adapter (#74): cached 10 minutes, the last good answer when the news site fails.

Only the fake gateway (autouse `foresight` in conftest) is used; nothing reaches
news.sandcorp.co.kr."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.core.management import call_command
from pytest_django.fixtures import Settings

from adapters import foresight as adapter
from adapters.fake_foresight import FakeForesight

pytestmark = pytest.mark.django_db

# The shape AI-Trend-News #73 answers on GET /api/public/articles.
NEWS_JSON = {
    "items": [
        {
            "slug": "gpt-6",
            "title": "제목",
            "summary": "요약",
            "category": {"name": "모델", "slug": "models"},
            "image_url": None,
            "published_at": "2026-10-23T09:00:00+09:00",
            "url": "https://news.sandcorp.co.kr/a/gpt-6",
            "featured": False,
            "has_commentary": True,
        }
    ],
    "site": {"name": "Foresight", "url": "https://news.sandcorp.co.kr"},
}


@pytest.fixture(autouse=True)
def cache_table(db: None) -> Iterator[None]:
    call_command("createcachetable", verbosity=0)
    cache.clear()
    yield
    cache.clear()


def test_recent_articles_are_cached(foresight: FakeForesight) -> None:
    first = adapter.fetch_recent(5)
    assert first == foresight.articles[:5]
    assert adapter.fetch_recent(5) == first
    assert foresight.calls == [5]  # the second read came from the cache
    adapter.fetch_recent(3)
    assert foresight.calls == [5, 3]  # each limit has its own key


def test_a_failure_serves_the_last_good_answer(foresight: FakeForesight) -> None:
    good = adapter.fetch_recent(5)
    cache.delete(adapter._key(5))  # the 10 minutes are over
    foresight.failing = True

    assert adapter.fetch_recent(5) == good
    assert adapter.fetch_recent(5) == good
    assert len(foresight.calls) == 2  # the fallback is cached too: a dead site is asked once


def test_a_failure_without_a_last_good_answer_is_empty(
    foresight: FakeForesight, caplog: pytest.LogCaptureFixture
) -> None:
    foresight.failing = True
    assert adapter.fetch_recent() == []
    assert "Foresight" in caplog.text


def test_the_news_json_shape_is_read() -> None:
    [article] = adapter.parse_items(NEWS_JSON)
    assert article.category == "모델"
    assert article.image_url == ""
    assert article.published_at.utcoffset() == timedelta(hours=9)
    assert article.url == "https://news.sandcorp.co.kr/a/gpt-6"


def test_a_wrong_shape_is_unavailable() -> None:
    with pytest.raises(adapter.ForesightUnavailable):
        adapter.parse_items({"articles": []})
    with pytest.raises(adapter.ForesightUnavailable):
        adapter.parse_items({"items": [{"slug": "x"}]})


def test_an_empty_url_switches_it_off(settings: Settings) -> None:
    adapter.set_gateway(None)
    settings.FORESIGHT_API_URL = ""
    settings.FORESIGHT_STATS_URL = ""
    assert isinstance(adapter.get_gateway(), adapter.DisabledForesight)
    assert adapter.fetch_recent() == []
    settings.FORESIGHT_API_URL = "https://news.example/api/public/articles"
    assert isinstance(adapter.get_gateway(), adapter.HttpForesight)


def test_the_request_asks_for_commentary_only(monkeypatch: pytest.MonkeyPatch) -> None:
    urls: list[str] = []

    def fake_get_json(url: str, timeout: float) -> object:
        urls.append(url)
        return NEWS_JSON

    monkeypatch.setattr(adapter, "_get_json", fake_get_json)
    http = adapter.HttpForesight("https://news.example/api/public/articles", 3.0)
    assert len(http.recent(5)) == 1
    assert urls == ["https://news.example/api/public/articles?limit=5&commentary=true"]
    # a base URL that already has a query keeps it
    adapter.HttpForesight("https://news.example/a?x=1", 3.0).recent(2)
    assert urls[1] == "https://news.example/a?x=1&limit=2&commentary=true"

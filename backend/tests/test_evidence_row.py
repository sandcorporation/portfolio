"""The home evidence row (#91): Foresight stats adapter, omission rules, career years."""

from dataclasses import replace
from datetime import date

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client
from pytest_django.fixtures import Settings

from adapters import foresight as adapter
from adapters.fake_foresight import FakeForesight
from adapters.fake_metrics import FakeMetrics, sample_stats
from content.models import SiteProfile
from services.home import career_years, evidence_of, home_page
from services.portfolio import PortfolioCard, card_of
from tests.test_blog_pages import page_data
from tests.test_portfolio import make

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 23)
VISITORS = f"{sample_stats().total.total_visitors:,}"

# The shape AI-Trend-News #77 answers on GET /api/public/stats.
STATS_JSON = {
    "articles_per_day_7d": 41.6,
    "articles_total": 1234,
    "published_since": "2026-08-01",
    "predictions": {"hit_rate": 0.61},
}


@pytest.fixture(autouse=True)
def cache_table(db: None) -> None:
    call_command("createcachetable", verbosity=0)
    cache.clear()


def profile(**fields: object) -> SiteProfile:
    return SiteProfile(**fields)


def keys(items: list[dict[str, str]] | object) -> list[str]:
    assert isinstance(items, list)
    return [i["key"] for i in items]


# ---- adapter -------------------------------------------------------------------------------


def test_stats_are_cached_ten_minutes(foresight: FakeForesight) -> None:
    first = adapter.fetch_stats()
    assert first is not None and first.articles_per_day_7d == 42.4
    assert adapter.fetch_stats() == first
    assert foresight.stats_calls == 1


def test_a_failure_serves_the_last_good_stats_and_asks_once(foresight: FakeForesight) -> None:
    good = adapter.fetch_stats()
    cache.delete(adapter.STATS_KEY)  # the 10 minutes are over
    foresight.failing = True

    assert adapter.fetch_stats() == good
    assert adapter.fetch_stats() == good
    assert foresight.stats_calls == 2  # the fallback is cached too


def test_a_failure_without_a_last_good_answer_is_none(
    foresight: FakeForesight, caplog: pytest.LogCaptureFixture
) -> None:
    foresight.failing = True
    assert adapter.fetch_stats() is None
    assert adapter.fetch_stats() is None
    assert foresight.stats_calls == 1
    assert "Foresight" in caplog.text


def test_the_stats_json_shape_is_read() -> None:
    stats = adapter.parse_stats(STATS_JSON)
    assert stats == adapter.ForesightStats(41.6, 1234, "2026-08-01", 0.61)
    only_needed = adapter.parse_stats({"articles_per_day_7d": 3})
    assert only_needed.articles_total is None and only_needed.hit_rate is None


@pytest.mark.parametrize("bad", [[], {}, {"articles_per_day_7d": "3"}, {"articles_per_day_7d": -1}])
def test_a_wrong_stats_shape_is_unavailable(bad: object) -> None:
    with pytest.raises(adapter.ForesightUnavailable):
        adapter.parse_stats(bad)


def test_an_empty_stats_url_switches_stats_off(settings: Settings) -> None:
    adapter.set_gateway(None)
    settings.FORESIGHT_API_URL = "https://news.example/api/public/articles"
    settings.FORESIGHT_STATS_URL = ""
    assert adapter.fetch_stats() is None
    settings.FORESIGHT_API_URL = ""
    assert isinstance(adapter.get_gateway(), adapter.DisabledForesight)


# ---- career years ----------------------------------------------------------------------------


def test_the_career_year_counts_the_start_year_as_the_first() -> None:
    assert career_years(date(2020, 12, 31), TODAY) == 7
    assert career_years(date(2026, 1, 1), TODAY) == 1
    assert career_years(date(2027, 1, 1), TODAY) is None
    assert career_years(None, TODAY) is None


# ---- omission rules --------------------------------------------------------------------------


def card(status: str) -> PortfolioCard:
    return card_of(make(f"c-{status}", status=status))


def test_all_four_items_in_order(foresight: FakeForesight) -> None:
    make("a", 1, status="live")
    make("b", 2, status="live")
    make("c", 3, status="building")
    row = evidence_of(
        profile(career_started_on=date(2020, 3, 1), response_promise="영업일 1일"),
        home_page().data["portfolio"],
        adapter.fetch_stats(),
        TODAY,
        sample_stats(),
    )
    assert row == [
        {"key": "services", "value": "2", "unit": "", "label": "운영 중인 서비스"},
        {"key": "foresight", "value": "42", "unit": "건/일", "label": "Foresight 자동 편집 기사"},
        {"key": "visitors", "value": VISITORS, "unit": "명", "label": "전체 방문자 · 누적"},
        {"key": "reply", "value": "1일", "unit": "", "label": "첫 회신 · 영업일 기준"},
        {"key": "career", "value": "7", "unit": "년차", "label": "웹·앱 개발 경력"},
    ]


def test_visitors_tile_is_the_metrics_total_and_hides_without_it() -> None:
    base = profile(career_started_on=date(2020, 3, 1), response_promise="영업일 1일")
    total = sample_stats().total
    assert total.total_visitors > 0
    with_visits = evidence_of(base, [], None, TODAY, sample_stats())
    assert keys(with_visits) == ["visitors", "reply", "career"]
    assert with_visits[0]["value"] == f"{total.total_visitors:,}"
    assert keys(evidence_of(base, [], None, TODAY, None)) == ["reply", "career"]
    zero = replace(sample_stats(), total=replace(total, total_visitors=0))
    assert keys(evidence_of(base, [], None, TODAY, zero)) == ["reply", "career"]


def test_the_home_page_carries_the_visitors_tile(foresight: FakeForesight) -> None:
    make("a", 1, status="live")
    assert "visitors" in keys(home_page().data["evidence"])


def test_thousands_get_commas() -> None:
    stats = adapter.ForesightStats(1234.4, None, "", None)
    [item, _] = evidence_of(profile(response_promise="1일"), [], stats, TODAY)
    assert item["value"] == "1,234"


def test_each_item_is_left_out_when_it_has_nothing() -> None:
    stats = adapter.ForesightStats(5.0, None, "", None)
    cards = [card("live")]
    base = profile(career_started_on=date(2020, 1, 1), response_promise="영업일 1일")

    assert keys(evidence_of(base, [card("building")], stats, TODAY)) == [
        "foresight",
        "reply",
        "career",
    ]
    assert keys(evidence_of(base, cards, None, TODAY)) == ["services", "reply", "career"]
    base.response_promise = ""
    assert keys(evidence_of(base, cards, stats, TODAY)) == ["services", "foresight", "career"]
    base.response_promise = "영업일 1일"
    base.career_started_on = None
    assert keys(evidence_of(base, cards, stats, TODAY)) == ["services", "foresight", "reply"]


def test_a_promise_without_the_business_day_prefix_is_shown_as_it_is() -> None:
    stats = adapter.ForesightStats(5.0, None, "", None)
    [_, reply] = evidence_of(profile(response_promise="당일"), [], stats, TODAY)
    assert reply == {"key": "reply", "value": "당일", "unit": "", "label": "첫 회신"}


def test_fewer_than_two_items_leave_the_whole_row_out() -> None:
    assert evidence_of(profile(response_promise="영업일 1일"), [], None, TODAY) == []
    assert evidence_of(profile(response_promise=""), [], None, TODAY) == []


def test_the_home_shell_carries_the_row(
    client: Client, foresight: FakeForesight, metrics: FakeMetrics
) -> None:
    make("a", 1, status="live")
    row = SiteProfile.load()
    row.career_started_on = date(2020, 1, 1)
    row.save()

    data = page_data(client.get("/").content.decode())
    assert keys(data["evidence"]) == [
        "services",
        "foresight",
        "visitors",
        "reply",
        "career",
    ]

    foresight.stats_value = None
    cache.clear()
    row.career_started_on = None
    row.save()
    make("b", 2, status="building")
    SiteProfile.objects.filter(pk=1).update(response_promise="")
    data = page_data(client.get("/").content.decode())
    assert keys(data["evidence"]) == ["services", "visitors"]

    metrics.failing = True
    cache.clear()
    assert page_data(client.get("/").content.decode())["evidence"] == []

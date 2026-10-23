"""Visit metrics (#81): the adapter, the home data, and where the counting snippet goes.

Only the fake gateway (autouse `metrics` in conftest) is used; nothing reaches
metrics.sandcorp.co.kr."""

from collections.abc import Iterator
from dataclasses import replace
from typing import cast

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client
from pytest_django.fixtures import Settings

from adapters import metrics as adapter
from adapters.fake_metrics import FakeMetrics, sample_stats
from adapters.fake_storage import FakeObjectStorage
from tests.test_blog_pages import post
from tests.test_portfolio import make, page_data
from tests.test_print import print_url_of_published
from tests.test_proposals import preview_url

pytestmark = pytest.mark.django_db

SNIPPET = "https://metrics.example/snippet.js"

# The shape sandcorp-metrics #4 answers on GET /api/stats.
STATS_JSON = {
    "sites": [
        {
            "key": "codemit",
            "name": "Codemit",
            "total_visitors": 1500,
            "total_pageviews": 4000,
            "today_visitors": 12,
            "today_pageviews": 30,
            "live_visitors": 2,
            "since": "2026-10-01T00:00:00+09:00",
        }
    ],
    "total": {
        "key": "total",
        "name": "전체",
        "total_visitors": 9000,
        "total_pageviews": 20000,
        "today_visitors": 80,
        "today_pageviews": 200,
        "live_visitors": 0,
        "since": "2026-10-01T00:00:00+09:00",
    },
    "generated_at": "2026-10-23T12:00:00+09:00",
}


@pytest.fixture(autouse=True)
def cache_table(db: None) -> Iterator[None]:
    call_command("createcachetable", verbosity=0)
    cache.clear()
    yield
    cache.clear()


# --- adapter ---


def test_the_answer_is_parsed_from_the_public_json() -> None:
    stats = adapter.parse_stats(STATS_JSON)
    assert stats.total.today_visitors == 80
    site = stats.site("codemit")
    assert site is not None and site.total_visitors == 1500 and site.live_visitors == 2
    assert stats.site("nope") is None


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"sites": []},
        {"sites": {}, "total": {}},
        {"sites": [], "total": {"total_visitors": "x"}},
    ],
)
def test_a_wrong_shape_is_unavailable(payload: object) -> None:
    with pytest.raises(adapter.MetricsUnavailable):
        adapter.parse_stats(payload)


def test_stats_are_cached(metrics: FakeMetrics) -> None:
    first = adapter.fetch_stats()
    assert first == metrics.data
    assert adapter.fetch_stats() == first
    assert metrics.calls == 1


def test_a_failure_serves_the_last_good_answer(metrics: FakeMetrics) -> None:
    good = adapter.fetch_stats()
    cache.delete("metrics:stats")  # the 60 seconds are over
    metrics.failing = True

    assert adapter.fetch_stats() == good
    assert adapter.fetch_stats() == good
    assert metrics.calls == 2  # the failure is cached too: no call per page view


def test_a_failure_with_nothing_kept_is_none(metrics: FakeMetrics) -> None:
    metrics.failing = True
    assert adapter.fetch_stats() is None
    assert adapter.fetch_stats() is None
    assert metrics.calls == 1


def test_an_empty_url_switches_it_off(settings: Settings) -> None:
    adapter.set_gateway(None)
    settings.METRICS_API_URL = ""
    assert isinstance(adapter.get_gateway(), adapter.DisabledMetrics)
    assert adapter.fetch_stats() is None
    settings.METRICS_API_URL = "https://metrics.example/api/stats"
    assert isinstance(adapter.get_gateway(), adapter.HttpMetrics)


# --- home data ---


def test_home_data_carries_the_total_and_each_rows_site(client: Client) -> None:
    make("a", 1, metrics_site_key="codemit")
    make("b", 2, metrics_site_key="sandcorp")
    make("c", 3)  # no site key
    make("d", 4, metrics_site_key="gone")  # not in the counts

    data = page_data(client.get("/").content.decode())
    rows = {p["slug"]: p["visits"] for p in cast(list[dict[str, object]], data["portfolio"])}
    stats = sample_stats()
    codemit, sandcorp = stats.site("codemit"), stats.site("sandcorp")
    assert codemit and sandcorp

    assert data["visits"] == {
        "live": stats.total.live_visitors,
        "today": stats.total.today_visitors,
        "total": stats.total.total_visitors,
    }
    assert rows["a"] == {"today": codemit.today_visitors, "total": codemit.total_visitors}
    assert rows["b"] == {"today": sandcorp.today_visitors, "total": sandcorp.total_visitors}
    assert rows["c"] is None
    assert rows["d"] is None


def test_home_leaves_the_numbers_out_when_metrics_fail(
    client: Client, metrics: FakeMetrics
) -> None:
    make("a", 1, metrics_site_key="codemit")
    metrics.failing = True

    response = client.get("/")
    data = page_data(response.content.decode())

    assert response.status_code == 200
    assert data["visits"] is None
    assert cast(list[dict[str, object]], data["portfolio"])[0]["visits"] is None


def test_home_leaves_the_numbers_out_when_switched_off(client: Client, settings: Settings) -> None:
    adapter.set_gateway(None)
    settings.METRICS_API_URL = ""
    make("a", 1, metrics_site_key="codemit")

    data = page_data(client.get("/").content.decode())

    assert data["visits"] is None
    assert cast(list[dict[str, object]], data["portfolio"])[0]["visits"] is None


def test_a_zero_total_is_still_shown(client: Client, metrics: FakeMetrics) -> None:
    zero = replace(metrics.data.total, live_visitors=0, today_visitors=0, total_visitors=0)
    metrics.data = replace(metrics.data, total=zero)

    data = page_data(client.get("/").content.decode())

    assert data["visits"] == {"live": 0, "today": 0, "total": 0}


def test_the_site_key_is_set_through_the_portfolio_service() -> None:
    from services import portfolio

    item = make("a", 1)
    out = portfolio.update_item("a", portfolio.ItemPatch(metrics_site_key=" codemit "))
    assert out.metrics_site_key == "codemit"
    item.refresh_from_db()
    assert item.metrics_site_key == "codemit"
    assert (
        portfolio.update_item("a", portfolio.ItemPatch(title="새 제목")).metrics_site_key
        == "codemit"
    )
    assert (
        portfolio.update_item("a", portfolio.ItemPatch(metrics_site_key="")).metrics_site_key == ""
    )


# --- the snippet: public pages only ---


def tag_of(html: str) -> str:
    return f'<script defer src="{SNIPPET}" data-site="sandcorp"></script>'


def test_public_pages_load_the_snippet(client: Client, settings: Settings) -> None:
    settings.METRICS_SNIPPET_URL = SNIPPET
    make("a", 1)
    post("hello")

    for path in ["/", "/work/a", "/blog", "/blog/hello"]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert tag_of("") in response.content.decode(), path


def test_the_site_key_of_the_snippet_follows_the_setting(
    client: Client, settings: Settings
) -> None:
    settings.METRICS_SNIPPET_URL = SNIPPET
    settings.METRICS_SITE_KEY = "other"

    assert f'src="{SNIPPET}" data-site="other"' in client.get("/").content.decode()


def test_without_a_snippet_url_nothing_is_added(client: Client) -> None:
    for path in ["/", "/blog"]:
        assert "<script defer" not in client.get(path).content.decode()


def test_print_preview_and_proposal_pages_never_load_the_snippet(
    client: Client, settings: Settings, fake_storage: FakeObjectStorage
) -> None:
    settings.METRICS_SNIPPET_URL = SNIPPET
    print_path, slug, _, _ = print_url_of_published(fake_storage)
    pages = {
        "print": print_path,
        "preview": preview_url(slug),
        "public proposal": f"/p/{slug}",
    }

    for name, path in pages.items():
        response = client.get(path)
        assert response.status_code == 200, name
        assert SNIPPET not in response.content.decode(), name
    assert "<script defer" not in client.get("/admin/login/").content.decode()

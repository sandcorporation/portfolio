"""The blog screens' server side (#75): /blog and /blog/<slug> shells, the home page's two new
sections' data. Foresight is always the fake (see conftest)."""

import json
import re
import time
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from django.test import Client
from django.utils import timezone
from pytest_django.fixtures import Settings

from adapters.fake_foresight import FakeForesight, sample_article
from content.models import BlogPost
from services import blog, home
from services.errors import NotFound

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def post(slug: str, *, ago_hours: int = 1, tags: str = "", published: bool = True) -> BlogPost:
    return BlogPost.objects.create(
        slug=slug,
        title=f"제목 {slug}",
        summary=f"요약 {slug}",
        tags=tags,
        status=BlogPost.Status.PUBLISHED if published else BlogPost.Status.DRAFT,
        published_at=timezone.now() - timedelta(hours=ago_hours) if published else None,
    )


def page_data(html: str) -> dict[str, object]:
    found = re.search(r'<script id="page-data" type="application/json">(.*?)</script>', html, re.S)
    assert found, "no #page-data"
    return cast(dict[str, object], json.loads(found.group(1)))


def json_ld(html: str) -> dict[str, object]:
    found = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert found, "no JSON-LD"
    return cast(dict[str, object], json.loads(found.group(1)))


def meta_content(html: str, prop: str) -> str | None:
    found = re.search(rf'<meta (?:property|name)="{prop}" content="([^"]*)"', html)
    return found.group(1) if found else None


# --- /blog ---


def test_the_list_shows_published_posts_newest_first_with_tags(client: Client) -> None:
    post("old", ago_hours=48, tags="운영")
    post("new", ago_hours=1, tags="운영, 도구")
    post("draft", published=False)

    response = client.get("/blog")
    data = page_data(response.content.decode())

    assert response.status_code == 200
    assert [p["slug"] for p in cast(list[dict[str, object]], data["posts"])] == ["new", "old"]
    assert data["tags"] == [{"tag": "운영", "count": 2}, {"tag": "도구", "count": 1}]
    assert (data["page"], data["pages"], data["total"], data["tag"]) == (1, 1, 2, "")
    assert meta_content(response.content.decode(), "robots") == "index, follow"


def test_the_list_without_posts_is_an_empty_page_not_an_error(client: Client) -> None:
    response = client.get("/blog")

    assert response.status_code == 200
    assert page_data(response.content.decode())["posts"] == []


def test_a_tag_narrows_the_list_and_stays_out_of_the_index(client: Client) -> None:
    post("a", tags="운영")
    post("b", tags="도구")

    response = client.get("/blog", {"tag": "도구"})
    html = response.content.decode()

    assert [p["slug"] for p in cast(list[dict[str, object]], page_data(html)["posts"])] == ["b"]
    assert page_data(html)["tag"] == "도구"
    assert meta_content(html, "robots") == "noindex, follow"


def test_twenty_posts_a_page_and_pages_past_the_end_are_404(client: Client) -> None:
    for n in range(21):
        post(f"p{n:02d}", ago_hours=n + 1)

    first = page_data(client.get("/blog").content.decode())
    second = page_data(client.get("/blog", {"page": "2"}).content.decode())

    assert (len(cast(list[object], first["posts"])), first["pages"]) == (20, 2)
    assert [p["slug"] for p in cast(list[dict[str, object]], second["posts"])] == ["p20"]
    assert client.get("/blog", {"page": "3"}).status_code == 404
    assert client.get("/blog", {"page": "0"}).status_code == 404
    assert client.get("/blog", {"page": "x"}).status_code == 404


def test_the_list_carries_collection_json_ld(client: Client) -> None:
    post("a")

    ld = json_ld(client.get("/blog").content.decode())

    assert ld["@type"] == "CollectionPage"
    assert ld["url"] == "http://testserver/blog"


# --- /blog/<slug> ---


def test_a_post_has_its_data_neighbours_and_blogposting_json_ld(client: Client) -> None:
    post("older", ago_hours=48)
    post("mid", ago_hours=24, tags="운영, 도구")
    post("newer", ago_hours=1)

    response = client.get("/blog/mid")
    html = response.content.decode()
    data = page_data(html)
    ld = json_ld(html)

    assert response.status_code == 200
    assert data["prev"] == {"slug": "older", "title": "제목 older"}
    assert data["next"] == {"slug": "newer", "title": "제목 newer"}
    assert "<title>제목 mid | Sandcorp</title>" in html
    assert meta_content(html, "og:type") == "article"
    assert meta_content(html, "description") == "요약 mid"
    assert ld["@type"] == "BlogPosting"
    assert ld["headline"] == "제목 mid"
    assert ld["keywords"] == "운영, 도구"
    assert ld["url"] == "http://testserver/blog/mid"


def test_a_draft_and_an_unknown_slug_are_404(client: Client) -> None:
    post("draft", published=False)

    assert client.get("/blog/draft").status_code == 404
    assert client.get("/blog/nope").status_code == 404


# --- the draft preview (#147) ---


def test_a_draft_opens_through_its_preview_link_and_nowhere_public(
    client: Client, settings: Settings
) -> None:
    settings.METRICS_SNIPPET_URL = "https://metrics.example/snippet.js"
    draft = post("draft", published=False, tags="운영, 도구")
    BlogPost.objects.filter(pk=draft.pk).update(
        body={"tabs": [{"id": "main", "blocks": [{"id": "a", "type": "markdown", "body": "본문"}]}]}
    )

    url = blog.issue_preview_url("draft").url
    response = client.get(url)
    html = response.content.decode()

    assert url.startswith("/preview/blog/")
    assert response.status_code == 200
    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert response["Cache-Control"] == "no-store"
    assert response["X-Robots-Tag"] == "noindex, nofollow"
    assert "metrics.example" not in html  # not a visit
    assert '<div id="root"></div>' in html  # no server HTML, like the proposal preview
    assert "application/ld+json" not in html
    data = page_data(html)
    card = cast(dict[str, object], data["card"])
    assert (card["title"], card["tags"]) == ("제목 draft", ["운영", "도구"])
    assert (data["prev"], data["next"]) == (None, None)
    assert "본문" in json.dumps(data["body"], ensure_ascii=False)
    assert client.get("/blog/draft").status_code == 404
    assert "Disallow: /preview/" in client.get("/robots.txt").content.decode()


def test_a_blog_preview_link_expires_and_cannot_be_forged(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    post("draft", published=False)
    url = blog.issue_preview_url("draft").url
    token = url.removeprefix("/preview/blog/")
    now = time.time()

    monkeypatch.setattr(time, "time", lambda: now + timedelta(minutes=29).total_seconds())
    assert client.get(url).status_code == 200
    monkeypatch.setattr(time, "time", lambda: now + timedelta(minutes=31).total_seconds())
    expired = client.get(url)
    assert expired.status_code == 410
    assert "만료" in expired.content.decode() and "제목 draft" not in expired.content.decode()
    monkeypatch.undo()

    assert client.get(f"/preview/blog/{token[:-2]}xx").status_code == 404
    assert client.get(f"/preview/blog/other:{token.split(':', 1)[1]}").status_code == 404
    assert client.get(f"/preview/{token}").status_code == 404  # not a proposal's link
    BlogPost.objects.filter(slug="draft").delete()
    assert client.get(url).status_code == 404
    with pytest.raises(NotFound):
        blog.issue_preview_url("draft")


def test_the_feed_is_not_taken_for_a_post(client: Client) -> None:
    post("a")

    response = client.get("/blog/feed.xml")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/rss+xml")


def test_a_title_cannot_close_the_json_ld_script(client: Client) -> None:
    BlogPost.objects.create(
        slug="x",
        title="</script><b>x",
        status=BlogPost.Status.PUBLISHED,
        published_at=timezone.now(),
    )

    html = client.get("/blog/x").content.decode()

    assert "</script><b>" not in html
    assert json_ld(html)["headline"] == "</script><b>x"


# --- home sections ---


def test_home_data_carries_recent_posts_and_news(client: Client, foresight: FakeForesight) -> None:
    for n in range(4):
        post(f"p{n}", ago_hours=n + 1)

    data = page_data(client.get("/").content.decode())
    posts = cast(list[dict[str, object]], data["posts"])
    news = cast(list[dict[str, object]], data["news"])

    assert "ceo_intro" not in data  # #92: the home does not draw it
    assert [p["slug"] for p in posts] == ["p0", "p1", "p2"]
    assert len(news) == 5
    assert foresight.calls == [5]
    assert news[0]["category"] == "모델"
    assert (
        news[0]["url"]
        == "https://news.sandcorp.co.kr/a/article-1?utm_source=sandcorp&utm_medium=home"
    )


def test_home_has_no_rows_when_there_is_nothing_to_show(
    client: Client, foresight: FakeForesight
) -> None:
    foresight.failing = True

    data = page_data(client.get("/").content.decode())

    assert data["posts"] == []
    assert data["news"] == []


def test_a_news_link_keeps_its_own_query_and_replaces_old_marks() -> None:
    assert (
        home.with_utm("https://n.example/a?x=1&utm_source=old")
        == "https://n.example/a?x=1&utm_source=sandcorp&utm_medium=home"
    )


@pytest.mark.parametrize(
    ("ago", "text"),
    [
        (timedelta(seconds=20), "방금 전"),
        (timedelta(minutes=5, seconds=30), "5분 전"),
        (timedelta(hours=3, minutes=59), "3시간 전"),
        (timedelta(days=2, hours=5), "2일 전"),
        (timedelta(days=9), "2026.10.14"),
        (timedelta(seconds=-30), "방금 전"),
    ],
)
def test_relative_time(ago: timedelta, text: str) -> None:
    assert home.relative_time(NOW - ago, NOW) == text


def test_news_items_come_from_the_adapter_articles() -> None:
    article = sample_article(1)

    item = home.news_item(article, article.published_at + timedelta(hours=2))

    assert item["when"] == "2시간 전"
    assert item["image_url"] == "https://img.example/1.jpg"


def test_home_data_carries_tip_pool_and_server_html_draws_three(db: None) -> None:
    from core.public_html import home_body
    from services import home, tips

    assert home.home_page().data["tips"] == []
    for n in range(5):
        tips.create_tip(
            tips.NewTip(slug=f"tip-{n}", title=f"팁 {n}", summary="요약", categories=["testing"])
        )
        tips.publish_tip(f"tip-{n}")
    data = home.home_page().data
    assert len(data["tips"]) == 5
    html = str(home_body(data))
    assert html.count('href="/tips/tip-') == 3
    assert "팁 더 보기" in html

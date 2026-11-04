"""Development tips (issue 203): the service rules, /tips and /tips/<slug> with their server HTML,
SEO, the sitemap, the preview link and the MCP tools."""

import json
import re
from datetime import timedelta
from typing import Any, cast

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.utils import timezone
from pytest_django.fixtures import Settings

from content.models import Tip
from mcpserver.tools import TOOLS
from services import tips
from services.errors import Conflict, NotFound
from tests.site_auth import SiteAuth
from tests.test_blog_pages import json_ld, meta_content, page_data
from tests.test_mcp import McpClient
from tests.test_mcp_proposals import ok, refused
from tests.test_public_html import FRONTEND, root

pytestmark = pytest.mark.django_db

type Data = dict[str, Any]  # Any: tool results and page data are arbitrary JSON

BODY = "### 문제\n\n느리다.\n\n```python\nprint('hi')\n```\n\n<script>alert(1)</script>"


def tip(
    slug: str, *, categories: list[str] | None = None, ago_hours: int = 1, published: bool = True
) -> Tip:
    return Tip.objects.create(
        slug=slug,
        title=f"제목 {slug}",
        summary=f"요약 {slug}",
        categories=categories or [],
        body=BODY,
        status=Tip.Status.PUBLISHED if published else Tip.Status.DRAFT,
        published_at=timezone.now() - timedelta(hours=ago_hours) if published else None,
    )


# --- model and service ---


def test_categories_are_kept_in_the_fixed_order_and_unknown_ones_refused() -> None:
    saved = tip("a", categories=["debugging", "testing", "testing"])
    assert saved.categories == ["testing", "debugging"]
    with pytest.raises(ValidationError):
        tip("b", categories=["nope"])


def test_create_update_publish_keeps_the_first_publication_time() -> None:
    made = tips.create_tip(tips.NewTip(title="Retry with jitter", categories=["performance"]))
    assert (made.slug, made.status, made.published_at) == ("retry-with-jitter", "draft", None)
    assert tips.create_tip(tips.NewTip(title="Retry with jitter")).slug == "retry-with-jitter-2"
    assert tips.create_tip(tips.NewTip(title="한글 제목")).slug.startswith("tip-")
    with pytest.raises(Conflict):
        tips.create_tip(tips.NewTip(title="x", slug="retry-with-jitter"))

    patched = tips.update_tip("retry-with-jitter", tips.TipPatch(body="본문"))
    assert (patched.body, patched.categories) == ("본문", ["performance"])
    first = tips.publish_tip("retry-with-jitter").published_at
    tips.unpublish_tip("retry-with-jitter")
    assert tips.publish_tip("retry-with-jitter").published_at == first
    tips.delete_tip("retry-with-jitter")
    with pytest.raises(NotFound):
        tips.get_tip("retry-with-jitter")


# --- /tips ---


def test_the_list_shows_published_tips_newest_first_and_the_categories_in_use(
    client: Client, settings: Settings
) -> None:
    settings.METRICS_SNIPPET_URL = "https://metrics.example/snippet.js"
    tip("old", categories=["testing"], ago_hours=48)
    tip("new", categories=["testing", "auth"], ago_hours=1)
    tip("draft", categories=["memory"], published=False)

    html = client.get("/tips").content.decode()
    data = page_data(html)

    assert [t["slug"] for t in cast(list[Data], data["tips"])] == ["new", "old"]
    assert data["categories"] == [
        {"value": "testing", "label": "테스트", "count": 2},
        {"value": "auth", "label": "인증", "count": 1},
    ]
    assert (data["category"], data["total"]) == (None, 2)
    assert "metrics.example" in html  # a public page counts the visit
    assert meta_content(html, "robots") == "index, follow"
    assert json_ld(html)["@type"] == "CollectionPage"
    body = root(html)
    assert '<h1 id="tips-title" class="page-section-title">개발 팁</h1>' in body
    assert '<a class="work-row" href="/tips/new">' in body
    assert '<a href="/tips?category=auth">인증 <span aria-hidden="true">1</span></a>' in body
    assert '<a href="/tips" aria-current="page">팁</a>' in body  # the nav marks the page
    assert "/tips/draft" not in html


def test_a_category_narrows_the_list_and_unknown_ones_are_404(client: Client) -> None:
    tip("a", categories=["testing"])
    tip("b", categories=["auth"])

    response = client.get("/tips?category=auth")
    data = page_data(response.content.decode())

    assert [t["slug"] for t in cast(list[Data], data["tips"])] == ["b"]
    assert data["category"] == {"value": "auth", "label": "인증"}
    assert meta_content(response.content.decode(), "robots") == "noindex, follow"
    assert client.get("/tips?category=nope").status_code == 404
    assert client.get("/tips?page=2").status_code == 404
    assert client.get("/tips?page=x").status_code == 404


def test_an_empty_list_is_a_page_with_a_message(client: Client) -> None:
    response = client.get("/tips")
    body = root(response.content.decode())

    assert response.status_code == 200
    assert "아직 올린 팁이 없습니다." in body
    assert '<nav class="tag-filter"' not in body


def test_twenty_tips_a_page(client: Client) -> None:
    for n in range(21):
        tip(f"t{n}", ago_hours=n + 1)

    first = page_data(client.get("/tips").content.decode())
    second = page_data(client.get("/tips?page=2").content.decode())

    assert (len(cast(list[Data], first["tips"])), first["pages"]) == (20, 2)
    assert [t["slug"] for t in cast(list[Data], second["tips"])] == ["t20"]


# --- /tips/<slug> ---


def test_a_tip_has_its_markdown_related_tips_and_tech_article_json_ld(client: Client) -> None:
    tip("main", categories=["testing", "auth"], ago_hours=1)
    for n, category in enumerate(["testing", "auth", "testing", "auth"]):
        tip(f"rel{n}", categories=[category], ago_hours=n + 2)
    tip("other", categories=["memory"])
    tip("draft", categories=["testing"], published=False)

    html = client.get("/tips/main").content.decode()
    data = page_data(html)

    assert [t["slug"] for t in cast(list[Data], data["related"])] == ["rel0", "rel1", "rel2"]
    assert data["body"] == BODY
    ld = json_ld(html)
    assert (ld["@type"], ld["headline"], ld["keywords"]) == (
        "TechArticle",
        "제목 main",
        "테스트, 인증",
    )
    assert meta_content(html, "og:type") == "article"
    assert (meta_content(html, "og:image") or "").endswith("/static/core/og-default.png")
    body = root(html)
    assert '<h1 id="tip-title" class="work-title">제목 main</h1>' in body
    assert '<div class="prose sc-prose"><h3>문제</h3>' in body
    assert '<pre><code class="language-python">' in body
    assert "<script>alert" not in body
    assert '<a class="work-row" href="/tips/rel2">' in body and "/tips/rel3" not in body


def test_a_draft_and_an_unknown_slug_are_404(client: Client) -> None:
    tip("draft", published=False)
    assert client.get("/tips/draft").status_code == 404
    assert client.get("/tips/nope").status_code == 404


def test_the_sitemap_lists_published_tips_only(client: Client) -> None:
    sitemap = client.get("/sitemap.xml").content.decode()
    assert "/tips" not in sitemap  # nothing published yet

    tip("live")
    tip("draft", published=False)
    sitemap = client.get("/sitemap.xml").content.decode()

    assert re.search(r"<loc>[^<]*/tips</loc><lastmod>", sitemap)
    assert "/tips/live</loc>" in sitemap and "/tips/draft" not in sitemap


def test_a_draft_opens_through_its_preview_link_only(client: Client, settings: Settings) -> None:
    settings.METRICS_SNIPPET_URL = "https://metrics.example/snippet.js"
    tip("draft", categories=["auth"], published=False)

    url = tips.issue_preview_url("draft").url
    response = client.get(url)
    html = response.content.decode()

    assert url.startswith("/preview/tips/") and response.status_code == 200
    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert response["Cache-Control"] == "no-store"
    assert "metrics.example" not in html
    assert '<div id="root"></div>' in html
    data = page_data(html)
    assert cast(Data, data["card"])["categories"] == [{"value": "auth", "label": "인증"}]
    assert data["related"] == []
    token = url.removeprefix("/preview/tips/")
    assert client.get(f"/preview/blog/{token}").status_code == 404  # another salt
    assert client.get(f"/preview/tips/{token[:-2]}xx").status_code == 404


def test_fixed_text_of_the_tip_pages_matches_the_app_sources() -> None:
    """The server templates repeat the app's fixed copy; a change on one side fails here."""
    templates = FRONTEND.parents[1] / "backend" / "core" / "templates" / "core" / "public"
    server = (templates / "tips_index.html").read_text() + (templates / "tip.html").read_text()
    app = (FRONTEND / "tips" / "TipsIndexPage.tsx").read_text()
    app += (FRONTEND / "tips" / "TipPage.tsx").read_text()
    lead = re.search(r'TIPS_LEAD = "([^"]+)"', app)
    assert lead and lead.group(1) in server
    for text in [
        "Tips — 팁",
        "개발 팁",
        "아직 올린 팁이 없습니다.",
        "분류의 팁이 없습니다.",
        "← 팁",
        "같은 분류의 다른 팁",
        "문의 →",
    ]:
        assert text in app and text in server, text


# --- MCP ---


TIP_TOOLS = {
    "tip_guide", "list_tips", "get_tip", "create_tip", "update_tip", "issue_tip_preview_url",
    "publish_tip", "unpublish_tip", "delete_tip",
}  # fmt: skip
READ_ONLY = {"tip_guide", "list_tips", "get_tip", "issue_tip_preview_url"}


@pytest.fixture
def mcp(client: Client, auth_server: SiteAuth) -> McpClient:
    return McpClient(client, auth_server)


def test_tip_tools_are_listed_and_writers_point_to_the_guide(mcp: McpClient) -> None:
    init = cast(Data, mcp.request("initialize", {"protocolVersion": "2025-06-18"})["result"])
    assert "tip_guide" in init["instructions"]
    by_name = {t["name"]: t for t in cast(Data, mcp.request("tools/list")["result"])["tools"]}
    for name in TIP_TOOLS:
        assert by_name[name]["annotations"]["readOnlyHint"] is (name in READ_ONLY), name
    for writer in ("whoami", "create_tip", "update_tip"):
        assert "tip_guide" in by_name[writer]["description"], writer
    whoami = by_name["whoami"]["description"]
    tip_part = whoami[whoami.index("tip_guide") :]
    assert tip_part.index("issue_tip_preview_url") < tip_part.index("publish_tip")


def test_tip_guide_names_only_real_tools_fields_and_has_no_hosts(mcp: McpClient) -> None:
    found = ok(mcp, "tip_guide", {})
    guide = found["guide"]
    assert guide.startswith("# 개발 팁 작성 지침")
    assert len(found["categories"]) == 8
    named = set(re.findall(r"`([A-Za-z][\w-]*)`", guide))
    known = set(TOOLS) | set(tips.NewTip.model_fields)
    assert named - known == set()
    assert {"create_tip", "issue_tip_preview_url", "publish_tip", "categories"} <= named
    assert "출처" in guide
    assert re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", guide) is None
    assert re.search(r"https?://|\w+\.(co\.kr|com|dev|net)\b", guide) is None


def test_write_preview_publish_and_delete_a_tip(mcp: McpClient, client: Client) -> None:
    made = ok(mcp, "create_tip", {"title": "Flaky test", "categories": ["testing"], "body": "x"})
    slug = made["slug"]
    assert made["status"] == "draft" and made["url"] == f"/tips/{slug}"
    link = ok(mcp, "issue_tip_preview_url", {"slug": slug})
    assert client.get(link["url"]).status_code == 200
    ok(mcp, "update_tip", {"slug": slug, "summary": "한 줄"})
    assert ok(mcp, "publish_tip", {"slug": slug})["published_at"]
    assert client.get(f"/tips/{slug}").status_code == 200
    listed = ok(mcp, "list_tips", {"category": "testing", "published_only": True})["items"]
    assert [t["slug"] for t in listed] == [slug]
    assert ok(mcp, "get_tip", {"slug": slug})["summary"] == "한 줄"
    ok(mcp, "unpublish_tip", {"slug": slug})
    assert client.get(f"/tips/{slug}").status_code == 404
    assert ok(mcp, "delete_tip", {"slug": slug}) == {"deleted": slug}
    assert "없습니다" in refused(mcp, "get_tip", {"slug": slug})
    bad = refused(mcp, "create_tip", {"title": "x", "categories": ["nope"]})
    assert "categories" in bad
    assert json.dumps(ok(mcp, "list_tips", {})["items"]) == "[]"

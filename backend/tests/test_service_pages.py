"""The service pages (issue 163, in the database since issue 215): /services/<slug> shells,
their meta and Service JSON-LD, the sitemap, the home's 「서비스」 section and nav, the server
HTML against the app source, and the rows' rules, preview link, admin and MCP tools."""

import json
import re
from pathlib import Path
from typing import Any, cast

import pytest
from django.contrib.auth.models import User
from django.test import Client
from pytest_django.fixtures import Settings

from content.models import Inquiry, Service
from core import public_html
from mcpserver.tools import TOOLS
from services import offerings
from services.errors import Conflict, Rejected
from tests.site_auth import SiteAuth
from tests.test_mcp import McpClient
from tests.test_mcp_proposals import ok, refused

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("services")]

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
TEMPLATES = Path(public_html.__file__).parent / "templates" / "core" / "public"
SLUGS = ["mcp-integration", "claude-code-automation", "ai-work-automation"]

type Data = dict[str, Any]  # Any: tool results are arbitrary JSON


def page_data(html: str) -> dict[str, object]:
    found = re.search(r'<script id="page-data" type="application/json">(.*?)</script>', html, re.S)
    assert found, "no #page-data"
    return cast(dict[str, object], json.loads(found.group(1)))


def json_ld(html: str) -> dict[str, object]:
    found = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert found, "no JSON-LD"
    return cast(dict[str, object], json.loads(found.group(1)))


def meta(html: str, prop: str) -> str | None:
    found = re.search(rf'<meta (?:property|name)="{prop}" content="([^"]*)"', html)
    return found.group(1) if found else None


def root(html: str) -> str:
    found = re.search(r'<div id="root">(.*)</div>\s*<script id="page-data"', html, re.S)
    assert found, "no #root"
    return found.group(1)


@pytest.mark.parametrize("slug", SLUGS)
def test_a_service_page_has_its_title_description_and_service_json_ld(
    client: Client, settings: Settings, slug: str
) -> None:
    settings.METRICS_SNIPPET_URL = "https://metrics.example/s.js"
    offering = offerings.get(slug)
    assert offering is not None

    response = client.get(f"/services/{slug}")

    assert response.status_code == 200
    html = response.content.decode()
    assert f"<title>{offering['name']} | Sandcorp</title>" in html
    assert meta(html, "description") == offering["summary"]
    assert meta(html, "robots") == "index, follow"
    assert "og-default.png" in (meta(html, "og:image") or "")
    assert "https://metrics.example/s.js" in html  # a visit, like home, work and blog
    ld = json_ld(html)
    assert ld["@type"] == "Service"
    assert ld["name"] == offering["name"]
    assert ld["description"] == offering["summary"]
    assert ld["serviceType"] == offering["service_type"]
    assert ld["provider"] == {"@id": f"{settings.SITE_URL}/#organization"}
    assert ld["areaServed"] == {"@type": "Country", "name": "KR"}
    assert "offers" not in ld and "price" not in json.dumps(ld)
    assert page_data(html)["offering"] == offering


def test_titles_and_descriptions_differ_between_the_pages(client: Client) -> None:
    pages = [client.get(f"/services/{slug}").content.decode() for slug in SLUGS]
    titles = {re.search(r"<title>(.*?)</title>", html).group(1) for html in pages}  # type: ignore[union-attr]
    assert len(titles) == len(SLUGS)
    assert len({meta(html, "description") for html in pages}) == len(SLUGS)


def test_an_unknown_service_is_404_and_the_bare_path_goes_to_the_home_section(
    client: Client,
) -> None:
    assert client.get("/services/nope").status_code == 404
    response = client.get("/services")
    assert response.status_code == 301
    assert response["Location"] == "/#home-services"


def test_the_sitemap_lists_both_pages_with_the_copy_date(
    client: Client, settings: Settings
) -> None:
    body = client.get("/sitemap.xml").content.decode()
    for slug in SLUGS[:2]:
        assert (
            f"<url><loc>{settings.SITE_URL}/services/{slug}</loc>"
            "<lastmod>2026-10-30</lastmod></url>"  # the copy date, kept by the migration
        ) in body
    assert f"<loc>{settings.SITE_URL}/services/ai-work-automation</loc>" in body  # issue 223


@pytest.mark.parametrize("slug", SLUGS)
def test_the_server_html_draws_every_section_cases_and_one_quote_button(
    client: Client, slug: str
) -> None:
    offering = offerings.get(slug)
    assert offering is not None
    html = root(client.get(f"/services/{slug}").content.decode())

    assert f'<h1 id="service-title" class="work-title">{offering["name"]}</h1>' in html
    assert offering["lead"] in html
    for title in ["이런 분께 맞습니다", "해 드리는 일", "진행 방식", "실제 사례", "문의"]:
        assert f'class="page-section-title">{title}</h2>' in html
    assert all(line in html for line in offering["audience"])
    assert all(f"{s['title']}" in html for s in offering["steps"]) and len(offering["steps"]) == 5
    for case in offering["cases"]:
        assert f'<a class="work-row" href="{case["href"]}">' in html  # same tab: our own pages
    assert html.count('data-style="primary"') == 1
    assert (
        f'<a class="cta-button" data-style="primary" href="/?inquiry={offering["slug"]}'
        '#home-inquiry">견적 문의 →</a>' in html
    )
    assert 'aria-current="page">서비스</a>' in html
    text = re.sub(r"<[^>]+>", "", html).replace("20만 원부터", "")
    assert not re.search(r"\d[\d,]*\s*만?\s*원", text)  # only the starting price (issue 13)


def test_every_case_links_to_a_page_of_this_site() -> None:
    for service in Service.objects.all():
        for case in service.cases:
            assert re.fullmatch(r"/(blog|work)/[a-z0-9-]+", case["href"]), case["href"]


def test_home_has_the_services_section_after_the_company_and_the_nav_link(
    client: Client,
) -> None:
    html = client.get("/").content.decode()
    data = page_data(html)
    assert data["services"] == offerings.cards()
    body = root(html)
    assert '<a href="/#home-services">서비스</a>' in body
    assert '<a href="#home-services">서비스 →</a>' in body
    assert 'class="page-section-title">외주로 맡는 일</h2>' in body
    section = body.index('aria-labelledby="home-services"')
    assert (
        body.index('aria-labelledby="home-company"')
        < section
        < body.index('aria-labelledby="home-inquiry"')
    )
    assert "02 — Services" in body
    for slug in SLUGS:
        assert f'<a class="work-row" href="/services/{slug}">' in body


def test_fixed_text_matches_the_app_sources() -> None:
    """The service pages' copy is data (one copy); the labels around it are written twice."""
    page = (FRONTEND / "services" / "ServicePage.tsx").read_text()
    home = (FRONTEND / "home" / "HomePage.tsx").read_text()
    masthead = (FRONTEND / "brand" / "Masthead.tsx").read_text()
    template = (TEMPLATES / "service.html").read_text()
    for text in [
        "← 서비스",
        "/#home-services",
        "이런 분께 맞습니다",
        "해 드리는 일",
        "진행 방식",
        "실제 사례",
        "견적 문의 →",
        "?inquiry=",
        "Service",
        *(f'"{label}"' for label in ["For", "What", "Process", "Cases", "Contact"]),
    ]:
        assert text in page, text
        assert text.strip('"') in template, text
    assert '"Services"' in home and "서비스" in home
    assert '{ key: "services", href: "/#home-services", label: "서비스" }' in masthead
    assert "— Services</span>" in (TEMPLATES / "home.html").read_text()


def test_the_rag_card_comes_first_and_has_no_page_of_its_own(client: Client) -> None:
    cards = offerings.cards()
    assert [c["slug"] for c in cards] == ["rag-chatbot", *SLUGS]
    assert cards[0]["name"] == "RAG 상담 챗봇 구축"
    assert cards[0]["summary"] == (  # issue 215: the one line changed in the move to the database
        "가진 문서·FAQ로 답하는 상담 챗봇을 만들어 홈페이지에 붙입니다. "
        "직접 운영하는 챗봇 빌더(Flow)에서 쌓은 방식 그대로입니다."
    )
    assert cards[0]["href"] == "/?inquiry=rag-chatbot#home-inquiry"
    assert [c["href"] for c in cards[1:]] == [f"/services/{s}" for s in SLUGS]

    assert client.get("/services/rag-chatbot").status_code == 404
    assert "/services/rag-chatbot" not in client.get("/sitemap.xml").content.decode()
    body = root(client.get("/").content.decode())
    assert 'href="/?inquiry=rag-chatbot#home-inquiry"' in body
    assert body.index("RAG 상담 챗봇 구축") < body.index("사내 MCP 서버")
    assert "메신저에 붙입니다" not in body


# --- issue 215: the rows live in the database ---


RAG_PAGE = {
    "lead": "가진 문서로 답하는 챗봇을 만듭니다.",
    "service_type": "RAG 챗봇 구축",
    "audience": ["문의가 많은 팀"],
    "deliverables": [{"title": "문서 정리", "text": "답할 문서를 고릅니다."}],
    "steps": [{"title": "상담", "text": "듣습니다."}],
    "cases": [
        {
            "title": "Sandcorp Flow",
            "href": "https://flow.sandcorp.co.kr/",
            "kind": "포트폴리오",
            "note": "챗봇 빌더입니다.",
        }
    ],
    "contact": "가격은 범위에 따라 정합니다.",
}


def _card(slug: str) -> offerings.OfferingCard:
    return next(c for c in offerings.cards() if c["slug"] == slug)


def test_unpublishing_closes_the_page_and_the_card_goes_to_the_form(client: Client) -> None:
    offerings.unpublish_service("mcp-integration")

    assert client.get("/services/mcp-integration").status_code == 404
    assert "/services/mcp-integration" not in client.get("/sitemap.xml").content.decode()
    assert _card("mcp-integration")["href"] == "/?inquiry=mcp-integration#home-inquiry"
    assert 'href="/?inquiry=mcp-integration#home-inquiry"' in root(client.get("/").content.decode())


def test_filling_and_publishing_opens_the_page_and_points_the_card_at_it(client: Client) -> None:
    with pytest.raises(Rejected) as refused_publish:
        offerings.publish_service("rag-chatbot")  # nothing to show yet
    assert {e.path for e in refused_publish.value.errors} == set(offerings.PAGE_FIELDS)

    offerings.update_service("rag-chatbot", offerings.ServicePatch.model_validate(RAG_PAGE))
    offerings.publish_service("rag-chatbot")

    html = client.get("/services/rag-chatbot").content.decode()
    assert "가진 문서로 답하는 챗봇을 만듭니다." in root(html)
    assert json_ld(html)["serviceType"] == "RAG 챗봇 구축"
    # another site's case opens in a new tab; our own pages stay in the same tab
    assert (
        '<a class="work-row" href="https://flow.sandcorp.co.kr/" target="_blank" '
        'rel="noopener noreferrer">'
    ) in root(html)
    assert _card("rag-chatbot")["href"] == "/services/rag-chatbot"
    assert "/services/rag-chatbot</loc>" in client.get("/sitemap.xml").content.decode()


def test_hidden_cards_are_left_out_and_position_orders_them() -> None:
    patch = offerings.ServicePatch.model_validate
    offerings.update_service("rag-chatbot", patch({"is_visible": False}))
    offerings.update_service("claude-code-automation", patch({"position": -1}))

    assert [c["slug"] for c in offerings.cards()] == [
        "claude-code-automation",
        "mcp-integration",
        "ai-work-automation",
    ]


def test_the_rules_refuse_what_would_break_the_page() -> None:
    patch = offerings.ServicePatch.model_validate
    with pytest.raises(Rejected, match="inquiry_kind"):
        offerings.update_service("rag-chatbot", patch({"inquiry_kind": "새 구분"}))
    with pytest.raises(Rejected, match="lead"):  # a published page cannot lose its copy
        offerings.update_service("mcp-integration", patch({"lead": ""}))
    with pytest.raises(ValueError):  # Pydantic: too many lines, a host-less or http address
        patch({"audience": ["x"] * 7})
    with pytest.raises(ValueError):
        patch({"cases": [{**RAG_PAGE["cases"][0], "href": "http://example.com/"}]})  # type: ignore[dict-item]
    service = Service.objects.get(slug="mcp-integration")
    service.deliverables = [{"title": "x"}] * 9
    assert {e.path for e in offerings.problems(service)} >= {"deliverables[0].text"}
    service.deliverables = [{"title": "x", "text": "y"}] * 9
    assert [e.path for e in offerings.problems(service)] == ["deliverables"]
    with pytest.raises(Conflict):
        offerings.create_service(
            offerings.NewService(
                slug="rag-chatbot", name="x", summary="y", inquiry_kind="RAG 상담 챗봇"
            )
        )
    assert Service.objects.get(slug="mcp-integration").lead  # nothing was saved


def test_an_unpublished_page_opens_through_its_preview_link_only(
    client: Client, settings: Settings
) -> None:
    settings.METRICS_SNIPPET_URL = "https://metrics.example/s.js"
    with pytest.raises(Rejected, match="lead"):
        offerings.issue_preview_url("rag-chatbot")  # no copy to draw
    offerings.update_service("rag-chatbot", offerings.ServicePatch.model_validate(RAG_PAGE))
    link = offerings.issue_preview_url("rag-chatbot")
    assert link.url.startswith("/preview/services/")

    response = client.get(link.url)

    assert response.status_code == 200
    assert "no-store" in response["Cache-Control"]
    html = response.content.decode()
    assert meta(html, "robots") == "noindex, nofollow"
    assert "metrics.example" not in html
    assert root(html).strip() == ""  # no server HTML, like the other previews
    assert page_data(html)["offering"] == offerings.preview_offering(link.url.rsplit("/", 1)[1])
    assert client.get("/services/rag-chatbot").status_code == 404
    assert client.get("/preview/services/nope").status_code == 404
    tip_link = tips_preview_token()
    assert client.get(f"/preview/services/{tip_link}").status_code == 404  # salts differ


def tips_preview_token() -> str:
    from django.core import signing

    return signing.TimestampSigner(salt="tip-preview").sign("rag-chatbot")


# --- admin ---


@pytest.fixture
def owner_client(client: Client) -> Client:
    User.objects.create_superuser("owner", "o@example.com", "correct-horse-battery")
    client.login(username="owner", password="correct-horse-battery")
    return client


def _changelist_form(services: list[Service], **changed: object) -> dict[str, object]:
    form: dict[str, object] = {
        "form-TOTAL_FORMS": str(len(services)),
        "form-INITIAL_FORMS": str(len(services)),
        "_save": "저장",
    }
    for i, s in enumerate(services):
        form[f"form-{i}-id"] = str(s.pk)
        form[f"form-{i}-position"] = str(s.position)
        if s.is_visible:
            form[f"form-{i}-is_visible"] = "on"
        if s.is_published or (s.slug == changed.get("slug") and changed.get("is_published")):
            form[f"form-{i}-is_published"] = "on"
    return form


def test_admin_lists_services_and_its_saves_run_the_same_rules(owner_client: Client) -> None:
    page = owner_client.get("/admin/content/service/").content.decode()
    assert "RAG 상담 챗봇 구축" in page and "외주 서비스" in page

    rows = list(Service.objects.order_by("position", "id"))
    form = _changelist_form(rows, slug="rag-chatbot", is_published=True)
    response = owner_client.post("/admin/content/service/", form)
    assert response.status_code == 200  # the list again, with the error
    assert "상세 페이지를 공개하려면 채워야 합니다" in response.content.decode()
    assert not Service.objects.get(slug="rag-chatbot").is_published

    rag = Service.objects.get(slug="rag-chatbot")
    change = {
        "name": rag.name,
        "slug": rag.slug,
        "summary": "고친 요약입니다.",
        "inquiry_kind": rag.inquiry_kind,
        "position": "5",
        "is_visible": "on",
        "lead": "",
        "service_type": "",
        "audience": "[]",
        "deliverables": "[]",
        "steps": "[]",
        "cases": "[]",
        "contact": "",
    }
    response = owner_client.post(f"/admin/content/service/{rag.pk}/change/", change)
    assert response.status_code == 302
    assert Service.objects.get(slug="rag-chatbot").summary == "고친 요약입니다."
    bad = {**change, "audience": '["x", "x", "x", "x", "x", "x", "x"]'}
    response = owner_client.post(f"/admin/content/service/{rag.pk}/change/", bad)
    assert response.status_code == 200 and "6개 이하여야 합니다" in response.content.decode()


# --- MCP ---


SERVICE_TOOLS = {
    "service_guide", "list_services", "get_service", "create_service", "update_service",
    "issue_service_preview_url", "publish_service", "unpublish_service",
}  # fmt: skip
READ_ONLY = {"service_guide", "list_services", "get_service", "issue_service_preview_url"}


@pytest.fixture
def mcp(client: Client, auth_server: SiteAuth) -> McpClient:
    return McpClient(client, auth_server)


def test_service_tools_are_listed_and_writers_point_to_the_guide(mcp: McpClient) -> None:
    init = cast(Data, mcp.request("initialize", {"protocolVersion": "2025-06-18"})["result"])
    assert "service_guide" in init["instructions"]
    by_name = {t["name"]: t for t in cast(Data, mcp.request("tools/list")["result"])["tools"]}
    assert not any(name.startswith("delete_service") for name in by_name)
    for name in SERVICE_TOOLS:
        assert by_name[name]["annotations"]["readOnlyHint"] is (name in READ_ONLY), name
    for writer in ("whoami", "create_service", "update_service"):
        assert "service_guide" in by_name[writer]["description"], writer
    whoami = by_name["whoami"]["description"]
    part = whoami[whoami.index("service_guide") :]
    assert part.index("issue_service_preview_url") < part.index("publish_service")


def test_service_guide_names_only_real_tools_and_fields(mcp: McpClient) -> None:
    found = ok(mcp, "service_guide", {})
    guide = found["guide"]
    assert guide.startswith("# 외주 서비스 페이지 작성 지침")
    assert found["inquiry_kinds"] == list(Inquiry.Kind.values)
    named = set(re.findall(r"`([A-Za-z][\w-]*)`", guide))
    known = (
        set(TOOLS)
        | set(offerings.NewService.model_fields)
        | set(offerings.ServicePatch.model_fields)
        | set(offerings.ItemIn.model_fields)
        | set(offerings.CaseIn.model_fields)
    )
    assert named - known == set()
    assert {"inquiry_kind", "publish_service", "cases", "is_visible", "position"} <= named
    assert "범위에 따라 정합니다" in guide
    assert re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", guide) is None


def test_write_preview_publish_and_hide_a_service(mcp: McpClient, client: Client) -> None:
    made = ok(
        mcp,
        "create_service",
        {"slug": "web-app", "name": "웹 앱", "summary": "만듭니다.", "inquiry_kind": "신규 개발"},
    )
    assert made["is_visible"] is False and made["is_published"] is False
    assert made["position"] == 4 and made["url"] == "/?inquiry=web-app#home-inquiry"
    assert "web-app" not in [c["slug"] for c in offerings.cards()]
    assert "lead" in refused(mcp, "publish_service", {"slug": "web-app"})

    ok(mcp, "update_service", {"slug": "web-app", **RAG_PAGE, "is_visible": True})
    link = ok(mcp, "issue_service_preview_url", {"slug": "web-app"})
    assert client.get(link["url"]).status_code == 200
    published = ok(mcp, "publish_service", {"slug": "web-app"})
    assert published["has_page"] is True and published["url"] == "/services/web-app"
    assert client.get("/services/web-app").status_code == 200
    listed = [s["slug"] for s in ok(mcp, "list_services", {})["items"]]
    assert listed == [
        "rag-chatbot",
        "mcp-integration",
        "claude-code-automation",
        "ai-work-automation",
        "web-app",
    ]
    assert ok(mcp, "get_service", {"slug": "web-app"})["lead"] == RAG_PAGE["lead"]

    ok(mcp, "unpublish_service", {"slug": "web-app"})
    assert client.get("/services/web-app").status_code == 404
    ok(mcp, "update_service", {"slug": "web-app", "is_visible": False})
    assert "web-app" not in [c["slug"] for c in offerings.cards()]
    assert "없습니다" in refused(mcp, "get_service", {"slug": "nope"})
    assert "inquiry_kind" in refused(
        mcp, "update_service", {"slug": "web-app", "inquiry_kind": "없는 구분"}
    )

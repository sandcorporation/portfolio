"""The two service pages (issue 163): /services/<slug> shells, their meta and Service JSON-LD,
the sitemap, the home's 「서비스」 section and nav, and the server HTML against the app source."""

import json
import re
from pathlib import Path
from typing import cast

import pytest
from django.test import Client
from pytest_django.fixtures import Settings

from core import public_html
from services import offerings

pytestmark = pytest.mark.django_db

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
TEMPLATES = Path(public_html.__file__).parent / "templates" / "core" / "public"
SLUGS = ["mcp-integration", "claude-code-automation"]


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
    assert len(titles) == 2
    assert len({meta(html, "description") for html in pages}) == 2


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
    for slug in SLUGS:
        assert (
            f"<url><loc>{settings.SITE_URL}/services/{slug}</loc>"
            f"<lastmod>{offerings.UPDATED_ON.isoformat()}</lastmod></url>"
        ) in body


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
    assert [s["title"] for s in offering["steps"]] == [
        "상담",
        "범위 정의",
        "주 단위 시연",
        "납품",
        "운영 지원",
    ]
    for case in offering["cases"]:
        assert f'<a class="work-row" href="{case["href"]}">' in html  # same tab: our own pages
    assert html.count('data-style="primary"') == 1
    assert (
        f'<a class="cta-button" data-style="primary" href="/?inquiry={offering["slug"]}'
        '#home-inquiry">견적 문의 →</a>' in html
    )
    assert 'aria-current="page">서비스</a>' in html
    assert not re.search(r"\d[\d,]*\s*만?\s*원", re.sub(r"<[^>]+>", "", html))  # no price


def test_every_case_links_to_a_page_of_this_site() -> None:
    for offering in offerings.OFFERINGS:
        for case in offering["cases"]:
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
    assert cards[0]["href"] == "/?inquiry=rag-chatbot#home-inquiry"
    assert [c["href"] for c in cards[1:]] == [f"/services/{s}" for s in SLUGS]

    assert client.get("/services/rag-chatbot").status_code == 404
    assert "/services/rag-chatbot" not in client.get("/sitemap.xml").content.decode()
    body = root(client.get("/").content.decode())
    assert 'href="/?inquiry=rag-chatbot#home-inquiry"' in body
    assert body.index("RAG 상담 챗봇 구축") < body.index("사내 MCP 서버")

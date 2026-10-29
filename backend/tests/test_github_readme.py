"""GitHub profile READMEs generated from the site data (#59): renderer, endpoint, MCP fields."""

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import Client
from pydantic import ValidationError

from content.models import PortfolioItem, SiteProfile
from documents.validation import JSON
from services import github_readme
from services.profile import ProfilePatch, update_profile
from tests.site_auth import SiteAuth
from tests.test_mcp import McpClient

pytestmark = pytest.mark.django_db

SITE = "https://sandcorp.co.kr"
UTM_PERSONAL = "utm_source=github&utm_medium=readme&utm_campaign=personal"
UTM_ORG = "utm_source=github&utm_medium=readme&utm_campaign=org"


@pytest.fixture
def mcp(client: Client, auth_server: SiteAuth) -> McpClient:
    return McpClient(client, auth_server)


def doc(*blocks: dict[str, JSON]) -> dict[str, JSON]:
    return {"tabs": [{"id": "main", "title": "소개", "blocks": list(blocks)}]}


def md(block_id: str, title: str | None, body: str) -> dict[str, JSON]:
    return {"id": block_id, "type": "markdown", "title": title, "level": 2, "body": body}


def seed() -> None:
    profile = SiteProfile.load()
    profile.tagline = "기획부터 운영까지, 한 사람이 끝까지 책임지는 1인 개발사"
    profile.ceo_intro = doc(md("about", "김한얼 대표", "소개"))
    profile.company_intro = doc(
        {
            "id": "kpi",
            "type": "kpi",
            "items": [{"label": "경력", "value": "6년차"}, {"label": "서비스", "value": "4개"}],
        },
        md("about", "샌드코프는", f"한 번에 맡습니다. [사이트]({SITE}/work/codemit)"),
        md("ai", "AI 에이전트가 함께 운영합니다", "- **오류 자동 수리**"),
        {
            "id": "services",
            "type": "table",
            "title": "이런 일을 합니다",
            "columns": ["분야", "내용"],
            "rows": [["웹 서비스", "Django | Next.js"], [{"text": "병합", "colspan": 2}]],
        },
        {
            "id": "steps",
            "type": "steps",
            "items": [{"id": "a", "title": "정의"}, {"id": "b", "title": "설계"}],
        },
        md("x", None, "끝"),
    )
    profile.github = {
        "personal_intro": f"1인 개발사 [샌드코프]({SITE})를 운영합니다.\n\n- 🏗️ 백엔드·인프라",
        "stack_badges": ["Python", "Spring Boot", "Mystery-Tool"],
        "public_projects": [
            {"name": "drss", "url": "https://github.com/farrar142/drss", "scope": "personal"},
            {
                "name": "embed-chat",
                "url": "https://github.com/sandcorporation/embed-chat",
                "description": "GraphRAG 챗봇",
                "scope": "both",
            },
            {"name": "internal", "url": "https://github.com/x/internal", "scope": "org"},
        ],
        "contact_note": "문의는 사이트 폼으로.",
    }
    profile.save()
    PortfolioItem.objects.create(
        slug="codemit",
        title="Codemit — 공모전 플랫폼",
        summary="요약",
        tags="Django, Next.js, Celery, PostgreSQL, OpenSearch",
        service_url="https://codemit.kr",
        sort_order=2,
    )
    PortfolioItem.objects.create(
        slug="daypage",
        title="Daypage",
        summary="하루 노트",
        service_url="https://d.example",
        sort_order=1,
    )
    PortfolioItem.objects.create(
        slug="hidden", title="H — x", service_url="https://h.example", is_public=False
    )
    PortfolioItem.objects.create(slug="nourl", title="N — x", sort_order=3)


def test_personal_readme_follows_the_site_data() -> None:
    seed()

    text = github_readme.render_personal()

    lines = text.splitlines()
    assert lines[0] == "<!-- generated from https://sandcorp.co.kr — 손으로 고치지 마세요 -->"
    assert "### 안녕하세요, 김한얼입니다 👋" in text
    assert "**기획부터 운영까지, 한 사람이 끝까지 책임지는 1인 개발사**" in text
    assert f"[샌드코프]({SITE}?{UTM_PERSONAL})" in text
    # services: public + service_url only, sort_order first; one-liner falls back to summary
    assert "| [**Daypage**](https://d.example) | 하루 노트 |  |" in text
    assert (
        "| [**Codemit**](https://codemit.kr) | 공모전 플랫폼 | Django · Next.js · Celery"
        " · PostgreSQL |" in text
    )
    assert text.index("Daypage") < text.index("Codemit")
    assert "h.example" not in text and "nourl" not in text.lower()
    assert f"[sandcorp.co.kr]({SITE}?{UTM_PERSONAL})" in text
    # projects by scope
    assert "- [**drss**](https://github.com/farrar142/drss)" in text
    assert (
        "- [**embed-chat**](https://github.com/sandcorporation/embed-chat) — GraphRAG 챗봇" in text
    )
    assert "internal" not in text
    # badges: known (with logo) and unknown (grey, no logo)
    assert (
        "![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)"
        in text
    )
    assert "Spring_Boot-6DB33F" in text
    assert (
        "![Mystery-Tool](https://img.shields.io/badge/Mystery--Tool-555555?style=flat-square)"
        in text
    )
    assert "#### 📫 연락\n\n문의는 사이트 폼으로." in text


def test_org_readme_blocks_and_scope() -> None:
    seed()

    text = github_readme.render_org()

    assert '<div align="center">' in text and "## Sandcorp" in text
    assert f"[웹사이트]({SITE}?{UTM_ORG})" in text
    assert f"[사이트]({SITE}/work/codemit?{UTM_ORG})" in text
    assert "### 샌드코프는\n\n한 번에 맡습니다." in text
    assert "### AI 에이전트가 함께 운영합니다" in text
    # kpi and steps are left out of the org README
    assert "6년차" not in text and "1. **정의**" not in text
    # service table (two columns), then the site's table block with GFM cells
    assert "| 서비스 | 소개 |" in text
    assert "| 웹 서비스 | Django \\| Next.js |" in text
    assert "| 병합 |  |" in text
    assert text.index("운영 중인 서비스") < text.index("이런 일을 합니다")
    assert "embed-chat" in text and "internal" in text and "drss" not in text
    assert "@farrar142" in text and text.rstrip().endswith("</div>")


def test_block_kinds_to_gfm() -> None:
    from documents.validation import validate_document

    blocks = (
        validate_document(
            doc(
                {
                    "id": "k",
                    "type": "kpi",
                    "items": [
                        {"label": "경력", "value": "6년차"},
                        {"label": "서비스", "value": "4개"},
                    ],
                },
                {
                    "id": "s",
                    "type": "steps",
                    "items": [
                        {"id": "a", "title": "정의", "body": "범위 합의"},
                        {"id": "b", "title": "설계"},
                    ],
                },
                {
                    "id": "c",
                    "type": "cta",
                    "items": [
                        {
                            "label": "GitHub",
                            "style": "primary",
                            "target": {"kind": "url", "href": "https://github.com/x"},
                        },
                        {
                            "label": "아래로",
                            "style": "secondary",
                            "target": {"kind": "block", "block_id": "s"},
                        },
                    ],
                },
                {"id": "d", "type": "details", "summary": "접힘", "body": "본문"},
            )
        )
        .tabs[0]
        .blocks
    )

    rendered = [github_readme.render_block(b) for b in blocks]

    assert rendered[0] == "**6년차** 경력 · **4개** 서비스"
    assert rendered[1] == "1. **정의** — 범위 합의\n2. **설계**"
    assert rendered[2] == "[GitHub](https://github.com/x)"
    assert rendered[3] == ""  # unknown to the README: skipped, no error


def test_empty_site_renders_without_error() -> None:
    assert github_readme.render_personal().startswith("<!-- generated")
    assert "## Sandcorp" in github_readme.render_org()


def test_endpoints_headers_and_etag(client: Client) -> None:
    seed()

    for path in ("personal.md", "org.md"):
        response = client.get(f"/github/readme/{path}")
        assert response.status_code == 200
        assert response["Content-Type"] == "text/markdown; charset=utf-8"
        assert response["Cache-Control"] == "public, max-age=300"
        etag = response["ETag"]
        again = client.get(f"/github/readme/{path}", headers={"If-None-Match": etag})
        assert again.status_code == 304 and again["ETag"] == etag

    assert client.post("/github/readme/org.md").status_code == 405
    first = client.get("/github/readme/org.md")["ETag"]
    profile = SiteProfile.load()
    profile.tagline = "바뀜"
    profile.save()
    assert client.get("/github/readme/org.md")["ETag"] != first


def test_github_field_validation() -> None:
    bad = [
        {"public_projects": [{"name": "a", "url": "https://x.io", "scope": "all"}]},
        {"public_projects": [{"name": "a", "url": "ftp://x.io", "scope": "org"}]},
        {"stack_badges": [""]},
        {"unknown": 1},
    ]
    for github in bad:
        with pytest.raises(ValidationError):
            ProfilePatch.model_validate({"github": github})
        row = SiteProfile.load()
        row.github = github
        with pytest.raises(DjangoValidationError):
            row.full_clean()

    saved = update_profile(ProfilePatch.model_validate({"github": {"contact_note": "x"}}))
    assert saved.github.contact_note == "x" and saved.github.public_projects == []


def test_mcp_updates_github_and_service_url(mcp: McpClient) -> None:
    result = mcp.call_tool(
        "update_profile",
        {
            "github": {
                "personal_intro": "소개",
                "stack_badges": ["Python"],
                "public_projects": [{"name": "a", "url": "https://x.io/a", "scope": "org"}],
                "contact_note": "연락",
            }
        },
    )
    assert result["isError"] is False
    assert SiteProfile.load().github["stack_badges"] == ["Python"]
    assert mcp.call_tool("get_profile", {})["structuredContent"]["github"]["contact_note"] == "연락"  # type: ignore[index, call-overload]
    assert "ceo_intro" in mcp.call_tool("get_profile", {})["structuredContent"]  # type: ignore[operator]  # #92: kept

    bad_inputs: list[JSON] = [
        {"public_projects": [{"name": "a", "url": "ftp://x", "scope": "org"}]},
        {"public_projects": [{"name": "a", "url": "https://x.io", "scope": "world"}]},
    ]
    for bad in bad_inputs:
        assert mcp.call_tool("update_profile", {"github": bad})["isError"] is True
    assert SiteProfile.load().github["contact_note"] == "연락"  # refused writes saved nothing

    created = mcp.call_tool(
        "create_portfolio",
        {"slug": "svc", "title": "Svc — x", "service_url": "https://svc.example"},
    )
    assert created["isError"] is False
    assert PortfolioItem.objects.get(slug="svc").service_url == "https://svc.example"
    mcp.call_tool("update_portfolio", {"slug": "svc", "service_url": ""})
    assert PortfolioItem.objects.get(slug="svc").service_url == ""
    assert (
        mcp.call_tool("update_portfolio", {"slug": "svc", "service_url": "javascript:x"})["isError"]
        is True
    )

"""The privacy policy (/privacy, issue 201): the shell and its meta, the server HTML against the
app source, the footer link on every public page, the sitemap, and the facts the text states."""

import json
import re
from pathlib import Path
from typing import cast

import pytest
from django.test import Client
from pytest_django.fixtures import Settings

from content.models import PortfolioItem, SiteProfile
from core import public_html
from services import legal, retention

pytestmark = pytest.mark.django_db

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
TEMPLATES = Path(public_html.__file__).parent / "templates" / "core" / "public"


def page_data(html: str) -> dict[str, object]:
    found = re.search(r'<script id="page-data" type="application/json">(.*?)</script>', html, re.S)
    assert found, "no #page-data"
    return cast(dict[str, object], json.loads(found.group(1)))


def meta(html: str, prop: str) -> str | None:
    found = re.search(rf'<meta (?:property|name)="{prop}" content="([^"]*)"', html)
    return found.group(1) if found else None


def root(html: str) -> str:
    found = re.search(r'<div id="root">(.*)</div>\s*<script id="page-data"', html, re.S)
    assert found, "no #root"
    return found.group(1)


def test_the_privacy_page_is_public_indexed_counted_with_the_default_image(
    client: Client, settings: Settings
) -> None:
    settings.METRICS_SNIPPET_URL = "https://metrics.example/s.js"

    response = client.get("/privacy")

    assert response.status_code == 200
    html = response.content.decode()
    assert "<title>개인정보처리방침 | Sandcorp</title>" in html
    assert meta(html, "robots") == "index, follow"
    assert "og-default.png" in (meta(html, "og:image") or "")
    assert "https://metrics.example/s.js" in html
    assert page_data(html)["policy"] == legal.policy()


def test_the_server_html_has_the_company_the_date_every_section_and_the_youtube_paragraph(
    client: Client,
) -> None:
    html = root(client.get("/privacy").content.decode())
    text = re.sub(r"<[^>]+>", "", html)

    assert '<h1 id="privacy-title" class="work-title">개인정보처리방침</h1>' in html
    assert "시행 2026년 11월 7일" in text
    # issue 237: error records (GlitchTip) and the shared document link
    assert "서비스 오류 기록 — 90일 뒤 자동으로 지웁니다." in text
    assert "접속 IP(끝자리를 가린 것 — IPv4 마지막 8비트, IPv6 /64 이후를 0으로)" in text
    assert 'href="https://sandcorporation.github.io/privacy-and-terms/errors/"' in html
    assert (
        "운영자: 개인사업자 샌드코프(Sandcorp) · 대표 김한얼 · 사업자등록번호 752-26-01740" in text
    )
    for section in legal.SECTIONS:
        assert f'<h2 id="privacy-{section["id"]}">{section["title"]}</h2>' in html
    assert [s["title"].split(". ")[0] for s in legal.SECTIONS] == [str(n) for n in range(1, 12)]
    assert (
        "샌드코프는 자사 유튜브 채널에 영상을 올리기 위해 YouTube API 서비스를 사용합니다" in text
    )
    assert "회사 계정 외 이용자의 데이터는 수집하지 않습니다" in text
    for href in [legal.YOUTUBE_TERMS_URL, legal.GOOGLE_PRIVACY_URL, legal.KISA_URL]:
        assert f'<a href="{href}" target="_blank" rel="noopener noreferrer">' in html
    assert html.count("<table>") == html.count('<div class="sc-prose-table-scroll"><table>') == 4
    assert "대표 결정 대기" not in text


def test_the_retention_text_is_the_period_the_cleanup_enforces() -> None:
    assert retention.INQUIRY_KEEP.days == retention.PROPOSAL_VIEW_LOG_KEEP.days == 365
    assert legal.INQUIRY_RETENTION.startswith("접수한 날부터 1년이 지나면 자동으로 지웁니다")
    assert legal.PROPOSAL_VIEW_LOG_RETENTION.startswith("열람한 날부터 1년이 지나면 IP 주소와")


def test_the_operator_is_the_site_profiles_business_details() -> None:
    profile = SiteProfile()
    assert profile.business_name == legal.OPERATOR_NAME
    assert profile.representative == legal.OPERATOR_REPRESENTATIVE
    assert profile.business_number == legal.OPERATOR_NUMBER


def test_the_sitemap_lists_the_policy_with_its_effective_date(
    client: Client, settings: Settings
) -> None:
    body = client.get("/sitemap.xml").content.decode()
    assert (
        f"<url><loc>{settings.SITE_URL}/privacy</loc>"
        f"<lastmod>{legal.EFFECTIVE_ON.isoformat()}</lastmod></url>"
    ) in body


def test_every_public_page_footer_links_the_policy(client: Client) -> None:
    PortfolioItem.objects.create(slug="a", title="A", is_public=True)
    for path in ["/", "/blog", "/work/a", "/services/mcp-integration", "/privacy"]:
        html = root(client.get(path).content.decode())
        footer = html[html.index('<footer class="site-footer">') :]
        assert '<a href="/privacy">개인정보처리방침</a>' in footer, path


def test_the_home_shorts_player_is_disclosed_with_the_approved_sentence(client: Client) -> None:
    """Issue 211: the approved sentence word for word, and the cookie lines no longer absolute."""
    text = re.sub(r"<[^>]+>", "", root(client.get("/privacy").content.decode()))
    assert (
        "홈의 짧은 영상 썸네일은 Google(YouTube, i.ytimg.com)에서 불러오며, 영상을 재생하면 "
        "youtube-nocookie.com 플레이어가 열려 Google에 접속 정보(IP, 브라우저 정보, 사이트 "
        "출처)가 전달됩니다. 재생 전에는 YouTube 플레이어를 불러오지 않습니다."
    ) in text
    assert (
        "일반 방문자에게는 쿠키를 쓰지 않습니다. 다만 홈의 짧은 영상을 재생하면 열리는 "
        "YouTube(youtube-nocookie.com) 플레이어는 재생에 필요한 정보를 브라우저에 저장할 수 "
        "있습니다(9번)."
    ) in text
    summary = legal.policy()["summary"][0]
    assert (
        "쿠키를 쓰지 않습니다(홈의 짧은 영상을 재생하면 열리는 YouTube 플레이어는 예외" in summary
    )


def test_a_public_visitor_gets_no_cookie(client: Client) -> None:
    """The policy says ordinary visitors get no cookie: keep it true."""
    for path in ["/", "/blog", "/services/mcp-integration", "/privacy"]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert not response.cookies, (path, list(response.cookies))


def test_fixed_text_matches_the_app_sources() -> None:
    """The policy's copy is data (one copy); the labels around it are written twice."""
    page = (FRONTEND / "legal" / "PrivacyPage.tsx").read_text()
    template = (TEMPLATES / "privacy.html").read_text()
    for text in [
        "Privacy",
        "시행 ",
        "요약",
        "한눈에 보기",
        "privacy-summary",
        "privacy-operator",
        "privacy-links",
        "sc-prose-table-scroll",
        'aria-labelledby="privacy-title"',
    ]:
        assert text in page, text
        assert text in template, text
    masthead = (FRONTEND / "brand" / "Masthead.tsx").read_text()
    footer = (TEMPLATES / "_footer.html").read_text()
    assert 'PRIVACY_PATH = "/privacy"' in masthead
    assert "<a href={PRIVACY_PATH}>개인정보처리방침</a>" in masthead
    assert '<a href="/privacy">개인정보처리방침</a>' in footer

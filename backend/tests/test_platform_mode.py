"""외주 플랫폼 제출용 모드 (#225): no company name, contacts or our addresses anywhere."""

import io
import json
import re
import sys
from collections.abc import Iterator
from typing import Any

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client as HttpClient

from adapters.fake_renderer import FAKE_PDF, FakeRenderer
from adapters.fake_storage import FakeObjectStorage
from content.models import PortfolioItem, Proposal, ProposalRevision, SiteProfile, new_proposal_slug
from services import pdf, platform_mode, publishing
from services import proposals as svc
from services.errors import Conflict
from tests.site_auth import SiteAuth
from tests.test_mcp import McpClient
from tests.test_portfolio import make, page_data
from tests.test_private_media import draft, private
from tests.test_proposals import preview_url

pytestmark = pytest.mark.django_db

FORBIDDEN = (
    re.compile(r"샌드\s*코프"),
    re.compile(r"sandcorp", re.I),
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    re.compile(r"(?<!\d)0\d{1,2}[-\s.]\d{3,4}[-\s.]\d{4}(?!\d)"),
)


@pytest.fixture(autouse=True)
def cache_table(db: None) -> Iterator[None]:
    call_command("createcachetable", verbosity=0)
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def mcp(client: HttpClient, auth_server: SiteAuth) -> McpClient:
    return McpClient(client, auth_server)


@pytest.fixture(autouse=True)
def contacts(db: None) -> None:
    SiteProfile.objects.update_or_create(
        pk=1,
        defaults={
            "contact_email": "hello@sandcorp.co.kr",
            "contact_phone": "010-1234-5678",
            "address": "서울시 어딘가 1",
        },
    )


def document(video_id: int, case_id: int, *, leak: bool = False) -> dict[str, object]:
    body = (
        "자세한 내용은 [사례 페이지](https://sandcorp.co.kr/work/flow)와 "
        "[내부 문서](/work/flow), [하위 도메인](https://flow.sandcorp.co.kr/try)을 보세요. "
        "외부 자료는 [MDN](https://developer.mozilla.org)."
    )
    if leak:
        body += " 문의: 샌드코프 dev@example.com 02-123-4567"
    return {
        "tabs": [
            {
                "id": "main",
                "title": "본문",
                "blocks": [
                    {"id": "intro", "type": "markdown", "title": "소개", "body": body},
                    {
                        "id": "raw",
                        "type": "html",
                        "html": '<p><a href="https://sandcorp.co.kr/p/x">우리 주소</a></p>',
                    },
                    {
                        "id": "go",
                        "type": "cta",
                        "items": [
                            {
                                "label": "홈페이지",
                                "target": {"kind": "url", "href": "https://sandcorp.co.kr"},
                            },
                            {"label": "사례로", "target": {"kind": "tab", "tab_id": "main"}},
                        ],
                    },
                    {
                        "id": "only-ours",
                        "type": "cta",
                        "items": [
                            {
                                "label": "메일",
                                "target": {"kind": "url", "href": "mailto:hello@sandcorp.co.kr"},
                            }
                        ],
                    },
                    {
                        "id": "try",
                        "type": "embed",
                        "src": "https://flow.sandcorp.co.kr/try?embed=1",
                        "title": "체험",
                    },
                    {"id": "vid", "type": "video", "media_id": video_id},
                    {
                        "id": "cases",
                        "type": "case-ref",
                        "title": "수행사례",
                        "items": [{"item_id": case_id, "highlight": None}],
                    },
                ],
            }
        ]
    }


def platform_draft(*, leak: bool = False, mode: bool = True) -> svc.ProposalOut:
    v = private("video/mp4")
    case = PortfolioItem.objects.filter(slug="flow-case").first() or make(
        "flow-case", title="업무 흐름 도구", summary="사내 결재 흐름"
    )
    p = draft(platform_mode=mode)
    svc.replace_document(p.slug, document(v.pk, case.pk, leak=leak))
    return p


def structured(result: object) -> dict[str, Any]:  # Any: tool results are arbitrary JSON
    assert isinstance(result, dict)
    out = result["structuredContent"]
    assert isinstance(out, dict)
    return out


def assert_clean(text: str) -> None:
    for pattern in FORBIDDEN:
        assert not pattern.search(text), (pattern.pattern, pattern.search(text))


def blocks_of(data: dict[str, Any]) -> list[dict[str, Any]]:  # Any: test reads raw JSON
    tabs = data["document"]["tabs"]
    return list(tabs[0]["blocks"])


def test_the_preview_of_a_platform_draft_names_nothing_of_ours(
    fake_storage: FakeObjectStorage,
) -> None:
    p = platform_draft()

    response = HttpClient().get(preview_url(p.slug))
    html = response.content.decode()
    data = page_data(html)

    assert response.status_code == 200
    assert_clean(html)
    assert_clean(json.dumps(data, ensure_ascii=False))
    assert data["platform_mode"] is True
    assert data["supplier"] == {"name": "제안사", "email": "", "phone": "", "address": ""}
    assert "<title>제안서</title>" in html
    blocks = {b["id"]: b for b in blocks_of(data)}
    assert "try" not in blocks and "only-ours" not in blocks
    assert blocks["go"]["items"] == [
        {"label": "사례로", "target": {"kind": "tab", "tab_id": "main"}, "style": "primary"}
    ]
    body = blocks["intro"]["body"]
    assert "[MDN](https://developer.mozilla.org)" in body
    assert "사례 페이지와 내부 문서, 하위 도메인을" in body
    assert blocks["raw"]["html"] == "<p>우리 주소</p>"
    case = blocks["cases"]["items"][0]["case"]
    assert case["slug"] == "" and case["title"] == "업무 흐름 도구"


def test_the_revision_print_page_has_no_public_url_or_company_name(
    fake_storage: FakeObjectStorage,
) -> None:
    p = platform_draft()
    publishing.publish(p.slug)
    revision = ProposalRevision.objects.get(proposal__slug=p.slug)
    assert revision.platform_mode is True

    response = HttpClient().get(svc.issue_print_url(revision))
    html = response.content.decode()
    data = page_data(html)

    assert response.status_code == 200
    assert_clean(html)
    assert data["print_mode"] is True
    assert data["public_url"] is None
    assert 'rel="canonical"' not in html and "og:site_name" not in html


def test_the_draft_print_page_follows_the_link_mode_not_the_setting(
    fake_storage: FakeObjectStorage,
) -> None:
    p = platform_draft(mode=False)
    row = Proposal.objects.get(slug=p.slug)

    path = svc.issue_draft_print_url(row, platform=True)
    response = HttpClient().get(path)
    html = response.content.decode()
    data = page_data(html)

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert response["X-Robots-Tag"] == "noindex, nofollow"
    assert_clean(html)
    assert data["print_mode"] is True and data["preview"] is False
    token = path.removeprefix("/print/draft/")
    assert data["media_endpoint"] == f"/print/draft/{token}/media"
    vid = next(b for b in blocks_of(data) if b["id"] == "vid")
    assert vid["url"]  # private media resolved for the renderer
    media = HttpClient().get(f"{data['media_endpoint']}/{vid['media_id']}")
    assert media.status_code == 200 and media.json()["url"]
    assert Proposal.objects.get(slug=p.slug).platform_mode is False

    plain = page_data(HttpClient().get(svc.issue_draft_print_url(row)).content.decode())
    assert plain["platform_mode"] is False
    assert plain["supplier"]["name"] == "샌드코프"


def test_a_bad_draft_print_token_is_404(db: None) -> None:
    assert HttpClient().get("/print/draft/nope").status_code == 404


def test_without_the_mode_the_pages_are_as_before(fake_storage: FakeObjectStorage) -> None:
    p = platform_draft(mode=False)

    html = HttpClient().get(preview_url(p.slug)).content.decode()
    data = page_data(html)

    assert data["platform_mode"] is False
    assert data["supplier"]["email"] == "hello@sandcorp.co.kr"
    assert "<title>제안서 | Sandcorp</title>" in html
    assert {b["id"] for b in blocks_of(data)} >= {"try", "only-ours"}
    publishing.publish(p.slug)
    revision = ProposalRevision.objects.get(proposal__slug=p.slug)
    printed = page_data(HttpClient().get(svc.issue_print_url(revision)).content.decode())
    assert printed["public_url"] == f"https://sandcorp.co.kr/p/{p.slug}"


def test_leaks_find_what_the_author_wrote(fake_storage: FakeObjectStorage) -> None:
    p = platform_draft(leak=True)
    row = Proposal.objects.get(slug=p.slug)

    found = svc.leaks_of(row, True)

    # The name and the email are masked before leaks are counted (#229); a phone is not masked.
    assert not any("샌드코프" in piece or "@" in piece for piece in found)
    assert any("02-123-4567" in piece for piece in found)
    assert svc.leaks_of(Proposal.objects.get(slug=platform_draft().slug), True) == []


@pytest.mark.parametrize(
    "text",
    [
        "Sandcorp",
        "SANDCORP 팀",
        "+82-10-1234-5678",
        "010 1234 5678",
        "01012345678",
        "(02)1234-5678",
    ],
)
def test_leak_patterns(text: str) -> None:
    assert platform_mode.leaks({"title": text})


@pytest.mark.parametrize("text", ["2026-11-06", "5,950만원", "SC-20261105-NEXT-1", "1,234,567원"])
def test_not_leaks(text: str) -> None:
    assert platform_mode.leaks({"title": text}) == []


def test_export_proposal_pdf_over_mcp(
    mcp: McpClient, renderer: FakeRenderer, fake_storage: FakeObjectStorage
) -> None:
    p = platform_draft(leak=True)

    result = mcp.call_tool("export_proposal_pdf", {"slug": p.slug})

    assert result["isError"] is False
    out = structured(result)
    assert isinstance(out, dict)
    assert out["platform_mode"] is True
    assert str(out["url"]).startswith("https://download.test/")
    assert any("02-123-4567" in str(piece) for piece in out["leaks"])
    assert out["expires_at"]
    assert "/print/draft/" in renderer.urls[0]
    (key,) = [k for (_, k) in fake_storage.objects]
    assert key.startswith(f"pdf/drafts/{p.slug}-") and key.endswith(".pdf")

    off = mcp.call_tool("export_proposal_pdf", {"slug": p.slug, "platform_mode": False})
    assert structured(off)["platform_mode"] is False
    assert Proposal.objects.get(slug=p.slug).platform_mode is True


def test_platform_mode_through_create_update_and_get(mcp: McpClient) -> None:
    draft()
    made = mcp.call_tool(
        "create_proposal", {"client_code": "NEXT", "title": "플랫폼 지원", "platform_mode": True}
    )
    slug = structured(made)["slug"]
    assert structured(made)["platform_mode"] is True

    mcp.call_tool("update_proposal", {"slug": slug, "platform_mode": False})
    got = mcp.call_tool("get_proposal", {"slug": slug})

    assert structured(got)["platform_mode"] is False


def test_a_failing_renderer_is_a_conflict(
    renderer: FakeRenderer, fake_storage: FakeObjectStorage
) -> None:
    p = platform_draft()
    renderer.failing = True
    with pytest.raises(Conflict):
        pdf.export_draft(p.slug)
    assert fake_storage.objects == {}


def test_the_management_command_writes_only_the_pdf(
    renderer: FakeRenderer, fake_storage: FakeObjectStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = platform_draft(mode=False)
    before = Proposal.objects.get(slug=p.slug)
    out = io.BytesIO()
    err = io.StringIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(out))

    call_command("proposal_pdf", p.slug, "--platform", stderr=err)

    assert out.getvalue() == FAKE_PDF
    assert "platform_mode=True" in err.getvalue()
    assert "/print/draft/" in renderer.urls[0]
    after = Proposal.objects.get(slug=p.slug)
    assert (after.platform_mode, after.updated_at) == (False, before.updated_at)
    assert fake_storage.objects == {}
    assert not ProposalRevision.objects.exists()


def test_new_slugs_never_start_with_a_dash(monkeypatch: pytest.MonkeyPatch) -> None:
    # issue 7: token_urlsafe starts with "-" about 1 in 64 — argparse reads that as an option.
    tokens = iter(["-abc", "_def", "Xyz"])
    monkeypatch.setattr("content.models.secrets.token_urlsafe", lambda n: next(tokens))
    assert new_proposal_slug() == "Xyz"


def test_the_management_command_takes_an_old_dash_slug_after_double_dash(
    renderer: FakeRenderer, fake_storage: FakeObjectStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = platform_draft(mode=False)
    Proposal.objects.filter(slug=p.slug).update(slug="-" + p.slug[1:])
    out = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(out))

    call_command("proposal_pdf", "--platform", "--", "-" + p.slug[1:], stderr=io.StringIO())

    assert out.getvalue() == FAKE_PDF


# --- #229: names and our addresses are masked in every rendered text ---


@pytest.mark.parametrize(
    ("text", "masked"),
    [
        ("샌드코프는 대표 한 사람이 운영합니다.", "저희는 대표 한 사람이 운영합니다."),
        ("샌드코프(Sandcorp)가 만듭니다", "저희가 만듭니다"),
        (
            "Sandcorp Flow — 흐름으로 만드는 상담 챗봇 플랫폼",
            "Flow — 흐름으로 만드는 상담 챗봇 플랫폼",
        ),
        ("Sandcorp 플랫폼 — 포트폴리오·제안서", "플랫폼 — 포트폴리오·제안서"),
        ("SANDCORP의 방식", "저희의 방식"),
        ("만든 곳: Sandcorp.", "만든 곳: 저희."),
        ("sandcorp-flow 저장소", "flow 저장소"),
        ("sandcorp.co.kr 이 사이트. 포트폴리오", "이 사이트. 포트폴리오"),
        ("직접 고쳐 보기 (https://flow.sandcorp.co.kr/try?template=home) 끝", "직접 고쳐 보기 끝"),
        ("문의 hi@example.com 로", "문의 로"),
        (
            "외부 자료는 https://developer.mozilla.org 참고",
            "외부 자료는 https://developer.mozilla.org 참고",
        ),
        ("  들여쓴 코드\n- 목록", "  들여쓴 코드\n- 목록"),
    ],
)
def test_mask_text(text: str, masked: str) -> None:
    assert platform_mode.mask_text(text) == masked


def _platform_data(row: Proposal, *, platform: bool) -> svc.ProposalPageData:
    return svc._draft_page_data(
        row, preview=False, media_endpoint=None, platform=platform, private=False
    )


def test_case_cards_titles_and_company_text_are_masked(fake_storage: FakeObjectStorage) -> None:
    case = make(
        "flow-case-229",
        title="Sandcorp Flow — 상담 챗봇",
        summary="sandcorp.co.kr 에서 운영. 샌드코프가 만든 도구",
    )
    p = draft(platform_mode=True)
    Proposal.objects.filter(slug=p.slug).update(title="Sandcorp 제안", subtitle="샌드코프의 제안")
    doc: Any = document(private("video/mp4").pk, case.pk)  # Any: the test edits raw JSON
    doc["tabs"][0]["title"] = "샌드코프 소개"
    doc["tabs"][0]["blocks"].append(
        {"id": "about", "type": "markdown", "body": "샌드코프는 대표 한 사람이 운영합니다."}
    )
    svc.replace_document(p.slug, doc)
    row = Proposal.objects.get(slug=p.slug)

    data = _platform_data(row, platform=True)
    dumped = json.dumps(data.model_dump(mode="json"), ensure_ascii=False)

    assert data.title == "제안"
    assert data.subtitle == "저희의 제안"
    assert "Flow — 상담 챗봇" in dumped
    assert "저희는 대표 한 사람이 운영합니다." in dumped
    assert "저희 소개" in dumped
    assert_clean(dumped)
    assert svc.leaks_of(row, True) == []
    # Only the rendering is masked: the stored document and the portfolio item are untouched.
    assert "샌드코프는" in json.dumps(
        Proposal.objects.get(slug=p.slug).document, ensure_ascii=False
    )
    assert PortfolioItem.objects.get(pk=case.pk).title == "Sandcorp Flow — 상담 챗봇"


def test_without_the_mode_names_are_kept(fake_storage: FakeObjectStorage) -> None:
    p = draft(platform_mode=False)
    Proposal.objects.filter(slug=p.slug).update(subtitle="샌드코프의 제안")
    data = _platform_data(Proposal.objects.get(slug=p.slug), platform=False)
    assert data.subtitle == "샌드코프의 제안"
    assert data.supplier.name != platform_mode.SUPPLIER_NAME

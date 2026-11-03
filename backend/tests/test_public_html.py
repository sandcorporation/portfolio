"""Server HTML of the public pages (#109): without JavaScript, home, /work/<slug>, /blog and
/blog/<slug> carry their h1, body text and links in #root; React renders over it."""

import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.test import Client
from django.utils import timezone

from content.models import BlogPost, PortfolioItem, SiteProfile
from core import public_html
from documents.validation import JSON, validate_document

pytestmark = pytest.mark.django_db

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"

BODY: dict[str, JSON] = {
    "tabs": [
        {
            "id": "main",
            "title": "본문",
            "blocks": [
                {
                    "id": "intro",
                    "type": "markdown",
                    "title": "문제",
                    "body": "주문에 **세 시간**.\n\n- 엑셀 입력\n- 전화 확인\n\n"
                    "| 항목 | 값 |\n|---|---|\n| 오류 | 0건 |\n\n"
                    "[사이트](https://example.com) <script>alert(1)</script>",
                },
                {
                    "id": "result",
                    "type": "table",
                    "title": "결과",
                    "columns": ["항목", "후"],
                    "rows": [["처리 시간", {"text": "10분", "colspan": 1}]],
                },
                {"id": "more", "type": "details", "summary": "더 보기", "body": "접힌 글"},
            ],
        }
    ]
}


def root(html: str) -> str:
    """What is inside #root, i.e. what a reader without JavaScript gets."""
    found = re.search(r'<div id="root">(.*)</div>\s*<script id="page-data"', html, re.S)
    assert found, "no #root"
    return found.group(1)


def test_home_draws_hero_intro_rows_and_nav(client: Client) -> None:
    profile = SiteProfile.load()
    profile.tagline = "만들고 돌봅니다"
    profile.company_intro = BODY
    profile.save()
    PortfolioItem.objects.create(slug="codemit", title="Codemit", status="live", body=BODY)
    BlogPost.objects.create(
        slug="ssr",
        title="서버 렌더링",
        status=BlogPost.Status.PUBLISHED,
        published_at=timezone.now() - timedelta(hours=1),
    )

    body = root(client.get("/").content.decode())

    assert '<h1 id="home-hero-title" class="display">SANDCORP</h1>' in body
    assert public_html.HERO_LEAD in body
    assert "만들고 돌봅니다" in body
    assert "<li>엑셀 입력</li>" in body  # the company intro document
    assert '<a class="work-row portfolio-row" href="/work/codemit">' in body
    assert '<a class="work-row" href="/blog/ssr">' in body
    assert '<a href="/blog">기록</a>' in body
    numbers = re.findall(r"(\d\d) — (?:Company|Services|Notes|Foresight|Work|Contact)", body)
    assert numbers == [f"{n:02d}" for n in range(1, len(numbers) + 1)]  # only shown sections


def test_work_page_draws_title_and_block_document(client: Client) -> None:
    PortfolioItem.objects.create(
        slug="codemit", title="Codemit", summary="강의실", tags="Django", body=BODY
    )

    body = root(client.get("/work/codemit").content.decode())

    assert '<h1 id="work-title" class="work-title">Codemit</h1>' in body
    assert '<h2 id="work-intro" class="block-heading">문제</h2>' in body
    assert "<strong>세 시간</strong>" in body
    assert '<div class="sc-prose-table-scroll"><table>' in body
    assert "<td>오류</td>" in body and "<td>10분</td>" in body
    assert (
        '<a href="https://example.com" target="_blank" rel="noopener noreferrer">사이트</a>' in body
    )
    assert '<li data-level="2"><a href="#work-intro">문제</a></li>' in body  # contents
    assert "<summary>더 보기</summary>" in body and "접힌 글" in body
    assert "<script>alert" not in body  # raw HTML tags dropped, their text kept (skipHtml)


def test_work_page_service_link_shows_host_only(client: Client) -> None:
    long = "https://classroom.codemit.kr/join/AbC123?x=1"
    PortfolioItem.objects.create(slug="a", title="A", body=BODY, service_url=long)
    PortfolioItem.objects.create(slug="b", title="B", body=BODY, service_url="https://codemit.kr/")

    a = root(client.get("/work/a").content.decode())
    b = root(client.get("/work/b").content.decode())

    assert (
        f'<a href="{long}" target="_blank" rel="noopener noreferrer">classroom.codemit.kr</a>' in a
    )
    assert (
        '<a href="https://codemit.kr/" target="_blank" rel="noopener noreferrer">codemit.kr</a>'
        in b
    )


def test_blog_pages_draw_rows_tags_and_post(client: Client) -> None:
    for n, slug in enumerate(["old", "new"]):
        BlogPost.objects.create(
            slug=slug,
            title=f"글 {slug}",
            tags="개발",
            body=BODY,
            status=BlogPost.Status.PUBLISHED,
            published_at=timezone.now() - timedelta(days=2 - n),
        )

    index = root(client.get("/blog").content.decode())
    post = root(client.get("/blog/new").content.decode())

    assert '<h1 id="blog-title" class="page-section-title">만들면서 남긴 기록</h1>' in index
    assert '<a class="work-row" href="/blog/old">' in index
    assert 'href="/blog?tag=%EA%B0%9C%EB%B0%9C"' in index
    assert '<h1 id="post-title" class="work-title">글 new</h1>' in post
    assert '<a href="/blog/old" rel="prev">' in post
    assert "<li>전화 확인</li>" in post
    # the contents list is the body's first child, the same shape React draws (CSS moves it right)
    assert '<div class="document-body"><nav class="document-toc"' in post
    assert '</nav><div class="document-blocks">' in post


def test_text_is_escaped(client: Client) -> None:
    PortfolioItem.objects.create(slug="x", title="<b>굵게</b>", body=BODY)

    body = root(client.get("/work/x").content.decode())

    assert "&lt;b&gt;굵게&lt;/b&gt;" in body


def test_every_block_type_of_the_example_document_draws(example_document: dict[str, JSON]) -> None:
    html = public_html.document_html(example_document, "p-")

    ids = {block.id for tab in validate_document(example_document).tabs for block in tab.blocks}
    drawn = set(re.findall(r'data-block-id="([^"]+)"', html))
    assert html.startswith('<div class="document">')
    assert ids - drawn == {"profile-cta"}  # a CTA that only opens tabs has nothing to read


def test_fixed_text_matches_the_app_sources() -> None:
    """The server copy repeats a few constants of the app; a change on one side fails here."""
    home = (FRONTEND / "home" / "HomePage.tsx").read_text()
    masthead = (FRONTEND / "brand" / "Masthead.tsx").read_text()
    templates = Path(public_html.__file__).parent / "templates" / "core" / "public"
    top = (templates / "_top.html").read_text()

    assert " ".join(public_html.HERO_LEAD.split()) in " ".join(home.split())
    assert f'GITHUB_URL = "{public_html.GITHUB_URL}"' in masthead
    for label in [
        "회사 소개",
        "기록",
        "Foresight ↗",
        "포트폴리오",
        "문의",
        "샌드코프 · 웹·AI 제품 개발",
    ]:
        assert f'"{label}"' in masthead or f">{label}<" in masthead
        assert label in top


@pytest.mark.parametrize(
    ("href", "external"),
    [
        ("https://flow.sandcorp.co.kr/x", True),
        ("http://example.com", True),
        ("//example.com/a", True),
        ("HTTPS://Example.com", True),
        ("/work/a", False),
        ("#intro", False),
        ("https://sandcorp.co.kr/work/a", False),
        ("https://SANDCORP.co.kr", False),
        ("mailto:a@b.kr", False),
    ],
)
def test_external_rule(href: str, external: bool) -> None:
    assert public_html.is_external(href) is external


def test_markdown_and_cta_links_open_external_in_new_tab() -> None:
    html = str(
        public_html.prose(
            "[밖](https://flow.sandcorp.co.kr) [안](/work/a) "
            "[같은](https://sandcorp.co.kr/x) [앵커](#a)"
        )
    )
    blank = 'target="_blank" rel="noopener noreferrer"'
    assert f'<a href="https://flow.sandcorp.co.kr" {blank}>' in html or (
        'href="https://flow.sandcorp.co.kr"' in html and blank in html
    )
    assert html.count("target=") == 1
    cta: dict[str, JSON] = {
        "id": "c",
        "type": "cta",
        "items": [
            {
                "label": "밖",
                "style": "primary",
                "target": {"kind": "url", "href": "https://example.com"},
            },
            {
                "label": "안",
                "style": "secondary",
                "target": {"kind": "url", "href": "https://sandcorp.co.kr/a"},
            },
        ],
    }
    out = str(
        public_html.document_html({"tabs": [{"id": "t", "title": "t", "blocks": [cta]}]}, "w-")
    )
    assert out.count("target=") == 1 and 'href="https://example.com"' in out


def test_work_service_link_internal_host_stays_in_tab(client: Client) -> None:
    PortfolioItem.objects.create(
        slug="c", title="C", body=BODY, service_url="https://sandcorp.co.kr/x"
    )
    c = root(client.get("/work/c").content.decode())
    assert 'href="https://sandcorp.co.kr/x" rel="noopener">' in c and 'x" target' not in c


def test_embed_block_draws_frame_and_new_tab_link() -> None:
    embed: dict[str, JSON] = {
        "id": "try",
        "type": "embed",
        "src": "https://flow.sandcorp.co.kr/try?embed=1&template=home",
        "title": "Flow 체험",
        "intro": "아래에서 바로 고쳐 보고",
    }
    out = str(
        public_html.document_html({"tabs": [{"id": "t", "title": "t", "blocks": [embed]}]}, "w-")
    )
    assert (
        '<iframe class="embed-frame" src="https://flow.sandcorp.co.kr/try?embed=1&amp;template=home"'
        in out
    )
    assert 'title="Flow 체험"' in out and "아래에서 바로 고쳐 보고" in out
    assert 'target="_blank" rel="noopener noreferrer">새 탭에서 열기</a>' in out
    assert "<script" not in out  # no script: the frame stays 640px until the app takes over


def test_home_every_external_link_opens_in_new_tab(client: Client) -> None:
    """#129: nav, masthead, footer, inquiry and the Foresight rows; internal ones stay put."""
    body = root(client.get("/").content.decode())

    anchors = re.findall(r'<a\b[^>]*\bhref="([^"]*)"([^>]*)>', body)
    external = [
        (h, rest) for h, rest in anchors if public_html.is_external(h.replace("&amp;", "&"))
    ]
    internal = [(h, rest) for h, rest in anchors if not public_html.is_external(h)]

    hosts = {h.split("/")[2] for h, _ in external}
    assert hosts == {"news.sandcorp.co.kr", "github.com"}
    assert (
        sum(h.startswith("https://github.com") for h, _ in external) >= 3
    )  # masthead, footer, inquiry
    for href, rest in external:
        assert 'target="_blank"' in rest and 'rel="noopener noreferrer"' in rest, href
    for href, rest in internal:
        assert "target=" not in rest, href


def test_gallery_image_keeps_its_ratio_and_links_to_the_original() -> None:
    """#149: a gallery image is the original at its own ratio, one per row, and opens the
    original in a new tab without JavaScript (the app opens its viewer instead)."""
    gallery: dict[str, JSON] = {
        "id": "shots",
        "type": "gallery",
        "images": [
            {
                "media_id": 1,
                "alt": "시연 화면",
                "caption": "왼쪽 기록, 오른쪽 결과",
                "url": "https://cdn.example/a.png",
            },
            {"media_id": 2, "alt": "빠진 이미지"},
        ],
    }
    out = str(
        public_html.document_html({"tabs": [{"id": "t", "title": "t", "blocks": [gallery]}]}, "w-")
    )
    assert (
        '<li><a class="gallery-thumb" href="https://cdn.example/a.png" target="_blank" '
        'rel="noopener noreferrer"><img src="https://cdn.example/a.png" alt="시연 화면" '
        'loading="lazy"></a><p class="media-description">왼쪽 기록, 오른쪽 결과</p></li>'
    ) in out
    assert "빠진 이미지" not in out
    assert "aspect-ratio" not in out and "object-fit" not in out
    assert '<ul class="gallery-grid sc-prose-gallery">' in out  # same classes as Gallery.tsx


DESIGN_CSS = FRONTEND.parent / "node_modules" / "sandcorp-design" / "src" / "components.css"


def _rules(css: str, selector: str) -> list[str]:
    return re.findall(r"(?:^|\n|,\s*)" + re.escape(selector) + r"\s*(?:,[^{]*)?\{([^}]*)\}", css)


def _assert_never_crops(rules: list[str], selector: str) -> None:
    for rule in rules:
        assert "aspect-ratio" not in rule, selector
        assert "object-fit: cover" not in rule, selector
        assert not re.search(r"(?<![-\w])width: 100%", rule), selector


def test_public_image_rules_never_crop() -> None:
    """#149: body images, gallery images and the top cover keep the original ratio: no fixed
    aspect-ratio, no object-fit: cover, no stretching past the original width. Since #150 the
    body, gallery and cover rules come from sandcorp-design (.sc-prose…); portfolio's styles.css
    only adds the gallery button and its own overrides, which must not crop either."""
    assert DESIGN_CSS.is_file(), "sandcorp-design is not installed: run pnpm install in frontend/"
    design = DESIGN_CSS.read_text()
    for selector in (
        ".sc-prose img",
        ".sc-prose-cover",
        ".sc-prose-gallery",
        ".sc-prose-gallery figure",
    ):
        rules = _rules(design, selector)
        assert rules, selector
        _assert_never_crops(rules, selector)
    assert "max-height: 80vh" in _rules(design, ".sc-prose img")[0]
    css = (FRONTEND / "styles.css").read_text()
    for selector in (".gallery-thumb", ".gallery-thumb img"):
        assert _rules(css, selector), selector
    for selector in (
        ".gallery-thumb",
        ".gallery-thumb img",
        ".prose img",
        ".work-cover",
        ".gallery-grid",
    ):
        _assert_never_crops(_rules(css, selector), selector)


@pytest.mark.parametrize(
    ("tsx", "classes"),
    [
        ("blocks/Prose.tsx", "prose sc-prose"),
        ("blocks/Html.tsx", "prose sc-prose"),
        ("blocks/Callout.tsx", "block-callout sc-prose-callout"),
        ("blocks/Callout.tsx", "sc-prose-callout-title"),
        ("blocks/Callout.tsx", "sc-prose-callout-kind"),
        ("blocks/Prose.tsx", "sc-prose-table-scroll"),
        ("blocks/Table.tsx", "sc-prose-table-scroll"),
        ("blocks/Gallery.tsx", "gallery-grid sc-prose-gallery"),
        ("work/WorkPage.tsx", "work-cover sc-prose-cover"),
        ("blog/BlogPostPage.tsx", "work-cover sc-prose-cover"),
    ],
)
def test_server_html_uses_the_app_body_classes(tsx: str, classes: str) -> None:
    """#150, #155: body blocks carry sandcorp-design's .sc-prose… classes in both copies (#109)."""
    assert f'className="{classes}"' in (FRONTEND / tsx).read_text()
    server = Path(public_html.__file__).read_text() + "".join(
        t.read_text() for t in (Path(public_html.__file__).parent / "templates").rglob("*.html")
    )
    assert f'class="{classes}"' in server

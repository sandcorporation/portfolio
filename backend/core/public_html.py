"""Server HTML for the public pages' body (#109, docs/adr/0002-public-server-html.md).

Home, /work/<slug>, /blog and /blog/<slug> draw their text, headings and links into #root from
the same #page-data the React app reads, so a crawler or a reader without JavaScript gets the
page. React then renders over it with createRoot (no hydration): React stays the screen, this is
the readable copy. The page layouts are templates in core/templates/core/public/; block
documents are drawn here, one small function per block type, with the same class names as
frontend/src/blocks so the copy looks close to the screen until React takes over.
"""

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString, mark_safe
from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict

from documents.blocks import (
    AudioCompareBlock,
    Block,
    CalloutBlock,
    CaseRefBlock,
    CoverBlock,
    CtaBlock,
    CtaTargetBlock,
    CtaTargetUrl,
    DetailsBlock,
    EmbedBlock,
    GalleryBlock,
    HtmlBlock,
    KpiBlock,
    MarkdownBlock,
    StepsBlock,
    TableBlock,
    TableCell,
    VideoBlock,
)
from documents.validation import JSON, InvalidDocument, validate_document
from services.blog import PostListing
from services.home import HomeData

SEOUL = ZoneInfo("Asia/Seoul")


# --- Markdown (GFM tables and strikethrough, like remark-gfm; raw HTML dropped like skipHtml) ---


def _drop(
    self: RendererHTML, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
) -> str:
    return ""


def is_external(href: str) -> bool:
    """A link to another host (http(s) or //host).

    /path, #anchor, mailto: and the site's own host are not.

    Mirror of frontend/src/links.ts. The site host is SETTINGS.SITE_URL's.
    """
    href = href.strip()
    if not re.match(r"(?i)(https?:)?//", href):
        return False
    host = (urlsplit(href).netloc.rpartition("@")[2]).lower()
    return host != urlsplit(settings.SITE_URL).netloc.lower()


EXTERNAL_ATTRS = {"target": "_blank", "rel": "noopener noreferrer"}


def _link_open(
    self: RendererHTML, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType
) -> str:
    token = tokens[idx]
    if is_external(str(token.attrGet("href") or "")):
        for name, value in EXTERNAL_ATTRS.items():
            token.attrSet(name, value)
    return self.renderToken(tokens, idx, options, env)


_MARKDOWN = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
_MARKDOWN.add_render_rule("html_inline", _drop)
_MARKDOWN.add_render_rule("html_block", _drop)
_MARKDOWN.add_render_rule("link_open", _link_open)


def prose(source: str) -> SafeString:
    """Markdown body text in `.prose`, tables in their own scroll box (Prose.tsx)."""
    if not source.strip():
        return SafeString("")
    html = _MARKDOWN.render(source)  # escapes text; links are checked by markdown-it
    html = html.replace("<table>", '<div class="table-scroll"><table>')
    html = html.replace("</table>", "</table></div>")
    return format_html('<div class="prose">{}</div>', mark_safe(html))  # noqa: S308


# --- blocks (frontend/src/blocks) ---


def _heading(level: int, anchor: str, title: str | None) -> SafeString:
    if not title:
        return SafeString("")
    return format_html('<h{} id="{}" class="block-heading">{}</h{}>', level, anchor, title, level)


def _markdown(block: MarkdownBlock, anchor: str) -> SafeString:
    return format_html(
        '<section class="block-markdown">{}{}</section>',
        _heading(block.level, anchor, block.title),
        prose(block.body),
    )


def _html(block: HtmlBlock, anchor: str) -> SafeString:
    return format_html(
        '<section class="block-html">{}<div class="prose">{}</div></section>',
        _heading(block.level, anchor, block.title),
        mark_safe(block.html),  # noqa: S308 - sanitised when the document is validated
    )


def _kpi(block: KpiBlock, anchor: str) -> SafeString:
    items = format_html_join(
        "",
        '<li class="kpi-card"><span class="kpi-label">{}</span>'
        '<strong class="kpi-value">{}</strong>{}</li>',
        (
            (
                item.label,
                item.value,
                format_html('<span class="kpi-note">{}</span>', item.note) if item.note else "",
            )
            for item in block.items
        ),
    )
    return format_html(
        '<section class="block-kpi">{}<ul class="kpi-cards">{}</ul></section>',
        _heading(3, anchor, block.title),
        items,
    )


def _cell(cell: str | TableCell) -> SafeString:
    if isinstance(cell, str):
        return format_html("<td>{}</td>", cell)
    span = ""
    if cell.colspan > 1:
        span += f' colspan="{cell.colspan}"'
    if cell.rowspan > 1:
        span += f' rowspan="{cell.rowspan}"'
    return format_html("<td{}>{}</td>", mark_safe(span), cell.text)  # noqa: S308 - two ints


def _table(block: TableBlock, anchor: str) -> SafeString:
    head = format_html_join("", '<th scope="col">{}</th>', ((c,) for c in block.columns))
    rows = format_html_join(
        "",
        "<tr>{}</tr>",
        ((format_html_join("", "{}", ((_cell(c),) for c in row)),) for row in block.rows),
    )
    notes = format_html_join("", "<li>{}</li>", ((n,) for n in block.footnotes))
    return format_html(
        '<section class="block-table">{}{}<div class="table-scroll"><table><thead><tr>{}</tr>'
        "</thead><tbody>{}</tbody></table></div>{}</section>",
        _heading(3, anchor, block.title),
        format_html('<p class="table-unit">{}</p>', block.unit) if block.unit else "",
        head,
        rows,
        format_html('<ul class="table-footnotes">{}</ul>', notes) if block.footnotes else "",
    )


CALLOUT_LABEL = {"info": "안내", "warning": "주의", "condition": "조건"}


def _callout(block: CalloutBlock, anchor: str) -> SafeString:
    label = CALLOUT_LABEL[block.kind]
    return format_html(
        '<aside class="block-callout" data-kind="{}" aria-label="{}"><p class="callout-title">'
        '<span class="callout-kind">{}</span>{}</p>{}</aside>',
        block.kind,
        label,
        label,
        format_html("<strong>{}</strong>", block.title) if block.title else "",
        prose(block.body),
    )


def _details(block: DetailsBlock, anchor: str) -> SafeString:
    return format_html(
        '<details class="block-details"><summary>{}</summary>{}</details>',
        block.summary,
        prose(block.body),
    )


def _steps(block: StepsBlock, anchor: str) -> SafeString:
    items = format_html_join(
        "",
        '<li class="step">{}<strong class="step-title">{}</strong>{}{}</li>',
        (
            (
                format_html('<span class="step-badge" aria-hidden="true">{}</span>', number)
                if block.numbered
                else "",
                item.title,
                prose(item.body or ""),
                format_html('<span class="step-caption">{}</span>', item.caption)
                if item.caption
                else "",
            )
            for number, item in enumerate(block.items, 1)
        ),
    )
    return format_html(
        '<section class="block-steps" data-layout="{}">{}<ol class="steps-list">{}</ol></section>',
        block.layout,
        _heading(3, anchor, block.title),
        items,
    )


def _external_attrs(href: str) -> SafeString:
    if not is_external(href):
        return SafeString("")
    return format_html(' target="{}" rel="{}"', EXTERNAL_ATTRS["target"], EXTERNAL_ATTRS["rel"])


def _cta(block: CtaBlock, prefix: str) -> SafeString:
    links = []
    for item in block.items:
        if isinstance(item.target, CtaTargetUrl):
            href = item.target.href
        elif isinstance(item.target, CtaTargetBlock):
            href = f"#{prefix}{item.target.block_id}"
        else:
            continue  # a tab: only the app can open it
        links.append((href, item.style, item.label))
    if not links:
        return SafeString("")
    return format_html(
        '<div class="block-cta">{}</div>',
        format_html_join(
            "",
            '<a class="cta-button" href="{}" data-style="{}"{}>{}</a>',
            ((href, style, _external_attrs(href), label) for href, style, label in links),
        ),
    )


def _embed(block: EmbedBlock, anchor: str) -> SafeString:
    """The frame (640px, no script: the app grows it from the page's messages) and a link that also
    stands in for the frame on paper."""
    return format_html(
        '<section class="block-embed">{}'
        '<iframe class="embed-frame" src="{}" title="{}" loading="lazy" '
        'referrerpolicy="strict-origin-when-cross-origin"></iframe>'
        '<p class="embed-open"><a href="{}"{}>{}</a>'
        '<span class="embed-where"> {}</span></p></section>',
        format_html('<p class="embed-intro">{}</p>', block.intro) if block.intro else "",
        block.src,
        block.title,
        block.src,
        _external_attrs(block.src),
        block.open_label,
        block.src,
    )


def _gallery(block: GalleryBlock, anchor: str) -> SafeString:
    # Without JavaScript the original opens in a new tab; the app opens its viewer (Gallery.tsx).
    images = format_html_join(
        "",
        '<li><a class="gallery-thumb" href="{}"{}><img src="{}" alt="{}" loading="lazy"></a>'
        "{}</li>",
        (
            (
                image.url,
                _external_attrs(image.url),
                image.url,
                image.alt,
                format_html('<p class="media-description">{}</p>', image.caption)
                if image.caption
                else "",
            )
            for image in block.images
            if image.url
        ),
    )
    return format_html(
        '<section class="block-gallery">{}<ul class="gallery-grid">{}</ul></section>',
        _heading(3, anchor, block.title),
        images,
    )


def _video(block: VideoBlock, anchor: str) -> SafeString:
    return format_html(
        '<section class="block-video">{}{}</section>',
        _heading(3, anchor, block.title),
        format_html('<p class="media-description">{}</p>', block.caption) if block.caption else "",
    )


def _audio_compare(block: AudioCompareBlock, anchor: str) -> SafeString:
    return format_html(
        '<section class="block-audio-compare">{}{}'
        '<p class="audio-track-names">트랙: {}</p></section>',
        _heading(3, anchor, block.title),
        format_html('<p class="media-description">{}</p>', block.description)
        if block.description
        else "",
        " · ".join(track.label for track in block.tracks),
    )


def _case_ref(block: CaseRefBlock, anchor: str) -> SafeString:
    cards = format_html_join(
        "",
        '<li class="case-card"><div class="case-body"><a class="case-title" href="/work/{}">{}</a>'
        "{}{}</div></li>",
        (
            (
                item.case.slug,
                item.case.title,
                format_html('<span class="case-period">{}</span>', item.case.period)
                if item.case.period
                else "",
                format_html('<p class="case-text">{}</p>', item.highlight or item.case.summary)
                if item.highlight or item.case.summary
                else "",
            )
            for item in block.items
            if item.case
        ),
    )
    if not cards:
        return SafeString("")
    return format_html(
        '<section class="block-case-ref">{}<ul class="case-cards">{}</ul></section>',
        _heading(3, anchor, block.title),
        cards,
    )


def _cover(block: CoverBlock, anchor: str) -> SafeString:
    return format_html(
        '<header class="block-cover">{}<p class="cover-title">{}</p>{}</header>',
        format_html('<p class="cover-recipient">{}</p>', block.recipient)
        if block.recipient
        else "",
        block.title,
        format_html('<p class="cover-subtitle">{}</p>', block.subtitle) if block.subtitle else "",
    )


def block_html(block: Block, prefix: str) -> SafeString:
    """One block as server HTML in its `.block-slot`, or "" for a block with nothing to read."""
    anchor = f"{prefix}{block.id}"
    inner: SafeString
    match block:
        case MarkdownBlock():
            inner = _markdown(block, anchor)
        case HtmlBlock():
            inner = _html(block, anchor)
        case KpiBlock():
            inner = _kpi(block, anchor)
        case TableBlock():
            inner = _table(block, anchor)
        case CalloutBlock():
            inner = _callout(block, anchor)
        case DetailsBlock():
            inner = _details(block, anchor)
        case StepsBlock():
            inner = _steps(block, anchor)
        case CtaBlock():
            inner = _cta(block, prefix)
        case EmbedBlock():
            inner = _embed(block, anchor)
        case GalleryBlock():
            inner = _gallery(block, anchor)
        case VideoBlock():
            inner = _video(block, anchor)
        case AudioCompareBlock():
            inner = _audio_compare(block, anchor)
        case CaseRefBlock():
            inner = _case_ref(block, anchor)
        case CoverBlock():
            inner = _cover(block, anchor)
        case _:
            inner = SafeString("")
    if not inner:
        return SafeString("")
    return format_html('<div class="block-slot" data-block-id="{}">{}</div>', block.id, inner)


def _toc_title(block: Block) -> tuple[str, int] | None:
    """The table-of-contents line of a block (registry.ts `toc`)."""
    if isinstance(block, MarkdownBlock | HtmlBlock):
        return (block.title, block.level) if block.title else None
    title = getattr(block, "title", None)
    if isinstance(block, CoverBlock | CalloutBlock) or not isinstance(title, str) or not title:
        return None
    return title, 3


def document_html(document: Mapping[str, JSON], prefix: str, toc: bool = True) -> SafeString:
    """A block document (DocumentView.tsx): every tab in order, a tab's title as a heading when
    there are several (only the app has tab buttons), the contents up front unless `toc` is off.
    An invalid document draws nothing, as in the app."""
    try:
        parsed = validate_document(dict(document))
    except InvalidDocument:
        return SafeString("")
    several = len(parsed.tabs) > 1
    entries = []
    parts = []
    for tab in parsed.tabs:
        if several:
            parts.append(format_html('<h2 class="print-tab-title">{}</h2>', tab.title))
        for block in tab.blocks:
            parts.append(block_html(block, prefix))
            title = _toc_title(block)
            if title:
                entries.append((title[1], f"#{prefix}{block.id}", title[0]))
    nav = (
        format_html(
            '<nav class="document-toc" aria-label="목차"><ul>{}</ul></nav>',
            format_html_join("", '<li data-level="{}"><a href="{}">{}</a></li>', entries),
        )
        if toc and entries
        else ""
    )
    return format_html(
        '<div class="document"><div class="document-body">{}<div class="document-blocks">{}'
        "</div></div></div>",
        nav,
        format_html_join("", "{}", ((part,) for part in parts)),
    )


# --- small formats shared with the app ---


def post_date(iso: str) -> str:
    """2026.10.23 in Seoul time (blog/format.ts `postDate`); "" for a bad date."""
    try:
        at = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    return at.astimezone(SEOUL).strftime("%Y.%m.%d")


def bare_url(url: str) -> str:
    """https://classroom.codemit.kr/join/x?y -> classroom.codemit.kr (host and port only)."""
    for scheme in ("https://", "http://"):
        if url.startswith(scheme):
            url = url[len(scheme) :]
            break
    return re.split(r"[/?#]", url, maxsplit=1)[0]


def blog_index_href(tag: str, page: int = 1) -> str:
    """blog/types.ts `blogIndexHref`."""
    query = {**({"tag": tag} if tag else {}), **({"page": str(page)} if page > 1 else {})}
    return f"/blog?{urlencode(query)}" if query else "/blog"


# Kept in step with the app by tests/test_public_html.py (it reads the .tsx sources).
GITHUB_URL = "https://github.com/sandcorporation"  # brand/Masthead.tsx GITHUB_URL
HERO_LEAD = (  # home/HomePage.tsx HERO_LEAD
    "웹·모바일 서비스를 기획부터 설계·개발·배포·운영까지 한 번에 맡는 1인 개발사. "
    "재하청 없이 대표가 직접 합니다."
)


def _render(page: str, data: Mapping[str, object], **extra: object) -> SafeString:
    context = {"data": data, "github_url": GITHUB_URL, "hero_lead": HERO_LEAD, **extra}
    return mark_safe(  # noqa: S308 - a Django template, autoescaped
        render_to_string(f"core/public/{page}.html", context)
    )


def home_body(data: HomeData) -> SafeString:
    """The home. Section numbers count only the shown sections, as HomePage.tsx works out."""
    shown = [
        "company",
        *(["notes"] if data["posts"] else []),
        *(["news"] if data["news"] else []),
        *(["work"] if data["portfolio"] else []),
        "contact",
    ]
    live = sum(1 for card in data["portfolio"] if card["status"] == "live")
    meta = f"{len(data['portfolio'])} projects" + (f" · 운영 중 {live}" if live else "")
    return _render(
        "home",
        data,
        sections={key: f"{n:02d}" for n, key in enumerate(shown, 1)},
        portfolio_meta=meta,
        news_thumbs=any(item["image_url"] for item in data["news"]),
    )


def work_body(data: Mapping[str, object]) -> SafeString:
    """/work/<slug>: PortfolioDetail plus the masthead's availability and the footer."""
    return _render("work", data)


def blog_index_body(listing: PostListing, data: Mapping[str, object]) -> SafeString:
    """/blog: `data` is `listing` plus the masthead's availability and the footer."""
    tag, page = listing["tag"], listing["page"]
    return _render(
        "blog_index",
        data,
        prev_href=blog_index_href(tag, page - 1),
        next_href=blog_index_href(tag, page + 1),
    )


def blog_post_body(data: Mapping[str, object]) -> SafeString:
    """/blog/<slug>: PostDetail plus the masthead's availability and the footer."""
    return _render("blog_post", data)

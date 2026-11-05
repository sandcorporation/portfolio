"""HTML shell views: Django renders per-route <head> meta (and, on the public pages, a server
HTML copy of the body), then React renders on #root.

Add a route by adding a view here that builds a PageMeta and calls render_shell.
"""

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponsePermanentRedirect,
    HttpResponseRedirect,
    JsonResponse,
)
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.templatetags.static import static
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods, require_POST
from pydantic import BaseModel

from content.models import (
    PortfolioItem,
    Proposal,
    ProposalEvent,
    ProposalRevision,
    SiteProfile,
)
from core import public_html
from core.clientip import client_ip
from core.public_html import HOME_DESCRIPTION
from core.seo import home_jsonld, service_jsonld, work_jsonld
from core.vite import entry_assets
from services import (
    blog,
    legal,
    media,
    offerings,
    og_card,
    pdf,
    platform_mode,
    preview,
    proposals,
    publishing,
    runtime_settings,
    tips,
)
from services import proposal_access as access
from services import proposal_events as events
from services.home import home_page, site_availability, site_business
from services.portfolio import public_detail, public_modified, renamed_to

SITE_NAME = "Sandcorp"
HOME_TITLE = "샌드코프(Sandcorp) — 웹·AI 제품을 만들고 운영하는 1인 개발사"
INDEX = "index, follow"
NOINDEX = "noindex, nofollow"
DEFAULT_WORK_DESCRIPTION = "샌드코프 수행 사례"
# The preview image of public pages that have no cover of their own (#110). Built from
# scripts/og-image/og-default.svg by scripts/og-image/build.sh; 1200x630.
DEFAULT_OG_IMAGE = static("core/og-default.png")
DEFAULT_OG_IMAGE_ALT = "Sandcorp 로고"
OG_IMAGE_SIZE = (1200, 630)


@dataclass(frozen=True)
class PageMeta:
    title: str
    description: str
    robots: str
    image: str = ""  # a path or URL; "" = no preview image (proposals, print, preview)
    image_alt: str = ""
    image_size: tuple[int, int] | None = None  # (width, height) of `image` when known (#123)
    og_type: str = "website"
    # article:published_time / modified_time (ISO 8601) and one article:tag per tag
    published_time: str = ""
    modified_time: str = ""
    tags: tuple[str, ...] = ()
    # schema.org JSON-LD for search engines; None for pages without one
    jsonld: Mapping[str, object] | None = None
    # og:site_name; "" leaves the tag out (외주 플랫폼 제출용 proposals, #225)
    site_name: str = SITE_NAME
    # canonical / og:url (this page's absolute address); False leaves both out (#225)
    canonical: bool = True


# Proposal pages never leak customer names or amounts into meta or link previews.
_PROPOSAL_META = PageMeta(
    title=f"제안서 | {SITE_NAME}", description="샌드코프 제안서", robots=NOINDEX
)
# 외주 플랫폼 제출용 (#225): no company name and no address of ours in the head either (the
# PDF's title metadata comes from <title>).
_PLATFORM_META = PageMeta(
    title=platform_mode.PAGE_TITLE,
    description=platform_mode.PAGE_TITLE,
    robots=NOINDEX,
    site_name="",
    canonical=False,
)


def _proposal_meta(platform: bool) -> PageMeta:
    return _PLATFORM_META if platform else _PROPOSAL_META


def render_shell(
    request: HttpRequest,
    meta: PageMeta,
    status: int = 200,
    data: Mapping[str, object] | None = None,
    count_visit: bool = False,
    body: str = "",
) -> HttpResponse:
    """Render the shell. `data` is embedded as JSON in #page-data for React's first render.

    `count_visit` adds the sandcorp-metrics snippet (when METRICS_SNIPPET_URL is set). Only the
    public pages ask for it: print and preview pages are opened by the PDF renderer and the
    owner, proposals are private, and none of those are visits.

    `body` is the public page's server HTML for #root, drawn from the same `data` (#109,
    core/public_html.py); React renders over it. Proposal, preview and print pages leave it out."""
    context = {
        "site_name": meta.site_name,
        "data": data,
        "meta": meta,
        "og_image": request.build_absolute_uri(meta.image) if meta.image else "",
        "og_image_size": meta.image_size
        or (OG_IMAGE_SIZE if meta.image == DEFAULT_OG_IMAGE else None),
        "jsonld": _jsonld(meta.jsonld),
        "canonical": request.build_absolute_uri(request.path) if meta.canonical else "",
        "verify_google": runtime_settings.get("GOOGLE_SITE_VERIFICATION")
        if meta.robots == INDEX
        else "",
        "verify_naver": runtime_settings.get("NAVER_SITE_VERIFICATION")
        if meta.robots == INDEX
        else "",
        "assets": entry_assets(),
        "metrics_snippet_url": runtime_settings.get("METRICS_SNIPPET_URL") if count_visit else "",
        "metrics_site_key": runtime_settings.get("METRICS_SITE_KEY"),
        "body": body,
    }
    return render(request, "core/shell.html", context, status=status)


def _jsonld(value: Mapping[str, object] | None) -> str:
    """The JSON-LD body, safe inside a <script>: `<` and friends can never close the tag."""
    if value is None:
        return ""
    text = json.dumps(value, ensure_ascii=False)
    return mark_safe(text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))  # noqa: S308


def home(request: HttpRequest) -> HttpResponse:
    page = home_page()
    return render_shell(
        request,
        PageMeta(
            title=HOME_TITLE,
            description=HOME_DESCRIPTION,
            robots=INDEX,
            image=DEFAULT_OG_IMAGE,
            image_alt=DEFAULT_OG_IMAGE_ALT,
            jsonld=home_jsonld(
                site_url=settings.SITE_URL,
                logo=request.build_absolute_uri(static("core/logo.svg")),
                description=HOME_DESCRIPTION,
                profile=SiteProfile.objects.filter(pk=1).first() or SiteProfile(),
                same_as=[public_html.GITHUB_URL],
            ),
        ),
        data=page.data,
        count_visit=True,
        body=public_html.home_body(page.data),
    )


def _customer_page(request: HttpRequest, data: BaseModel, status: int = 200) -> HttpResponse:
    platform = bool(getattr(data, "platform_mode", False))
    response = render_shell(
        request, _proposal_meta(platform), status=status, data=data.model_dump(mode="json")
    )
    return _private(response)


def _private(response: HttpResponse) -> HttpResponse:
    response["Cache-Control"] = "no-store"
    response["X-Robots-Tag"] = NOINDEX
    return response


def _user_agent(request: HttpRequest) -> str:
    return str(request.META.get("HTTP_USER_AGENT", ""))[: events.USER_AGENT_MAX]


def _expired_screen(revision: ProposalRevision) -> proposals.ExpiredScreenData:
    assert revision.valid_until is not None
    return proposals.ExpiredScreenData(
        valid_until=revision.valid_until,
        supplier=proposals.supplier(platform=revision.platform_mode),
        platform_mode=revision.platform_mode,
    )


@require_http_methods(["GET", "HEAD", "POST"])
def proposal(request: HttpRequest, slug: str) -> HttpResponse:
    """The customer page: code form -> (session) -> latest revision.

    Past its validity date the page is the same code form; only the right code shows the expiry
    notice (no session), so a leaked link says nothing about the proposal.

    A draft, a revoked proposal and an unknown slug are the same 404. POST is the code form; a
    right code sets the session cookie and redirects back here.
    """
    found = Proposal.objects.filter(slug=slug, status=Proposal.Status.PUBLISHED).first()
    revision = publishing.latest_revision(found) if found else None
    if found is None or revision is None:
        raise Http404
    if request.method == "POST":
        attempt = access.try_code(
            found, request.POST.get("code", ""), client_ip(request), _user_agent(request)
        )
        if attempt is access.Attempt.OPENED and publishing.is_expired(revision):
            # The right code is what unlocks the notice; nothing to keep a session for.
            return _customer_page(request, _expired_screen(revision))
        if attempt is access.Attempt.OPENED:
            response = _private(HttpResponseRedirect(request.path))
            access.start_customer_session(response, found)
            return response
        form = proposals.CodeScreenData(
            error=attempt.value,
            csrf_token=get_token(request),
            platform_mode=revision.platform_mode,
        )
        return _customer_page(request, form, 429 if attempt is access.Attempt.BLOCKED else 400)
    if not publishing.is_expired(revision) and access.has_customer_session(request, found):
        events.record_view(found, revision, ip=client_ip(request), user_agent=_user_agent(request))
        pdf_url = f"/p/{slug}/pdf" if pdf.ready_job(found) else None
        data = proposals.revision_page_data(
            revision, csrf_token=get_token(request), pdf_url=pdf_url
        )
        return _customer_page(request, data)
    blocked = access.is_blocked(found, client_ip(request))
    form = proposals.CodeScreenData(
        error="blocked" if blocked else None,
        csrf_token=get_token(request),
        platform_mode=revision.platform_mode,
    )
    return _customer_page(request, form)


@require_POST
def proposal_lock(request: HttpRequest, slug: str) -> HttpResponse:
    """「잠금」: forget this browser's session for the proposal and go back to the code form."""
    response = _private(HttpResponseRedirect(f"/p/{slug}"))
    access.end_customer_session(response, slug)
    return response


def _media_answer(url: str | None) -> HttpResponse:
    if url is None:
        return _private(JsonResponse({"error": "not_found"}, status=404))
    return _private(JsonResponse({"url": url}))


@require_http_methods(["GET"])
def proposal_pdf(request: HttpRequest, slug: str) -> HttpResponse:
    """The latest revision's PDF: the same gate as the page, then a 302 to a short-lived presigned
    URL that saves it as `<document number>.pdf`. 404 until the PDF is done."""
    found = Proposal.objects.filter(slug=slug, status=Proposal.Status.PUBLISHED).first()
    revision = publishing.latest_revision(found) if found else None
    if found is None or revision is None:
        raise Http404
    if publishing.is_expired(revision) or not access.has_customer_session(request, found):
        return _private(HttpResponse("코드를 다시 입력해 주세요.", status=403))
    job = pdf.ready_job(found)
    if job is None:
        raise Http404
    response = _private(HttpResponseRedirect(pdf.download_url(job)))
    events.record(
        found,
        ProposalEvent.Kind.PDF,
        ip=client_ip(request),
        user_agent=_user_agent(request),
        revision=revision,
    )
    access.on_pdf_downloaded(found, revision)
    return response


@require_POST
def proposal_tab(request: HttpRequest, slug: str) -> HttpResponse:
    """The customer page reports a tab switch (`{"tab": "<tab id>"}`, CSRF header). Needs the
    session like the page does; limited per proposal and IP; 204 on success."""
    found = Proposal.objects.filter(slug=slug, status=Proposal.Status.PUBLISHED).first()
    revision = publishing.latest_revision(found) if found else None
    if found is None or revision is None:
        raise Http404
    if publishing.is_expired(revision) or not access.has_customer_session(request, found):
        return _private(HttpResponse(status=403))
    ip = client_ip(request)
    if not events.tab_allowed(found, ip):
        return _private(HttpResponse(status=429))
    try:
        tab = json.loads(request.body).get("tab")
    except ValueError, AttributeError:
        tab = None
    tab_ids = {t.get("id") for t in revision.document.get("tabs", []) if isinstance(t, dict)}
    if not isinstance(tab, str) or tab not in tab_ids:
        return _private(HttpResponse(status=400))
    events.record(
        found,
        ProposalEvent.Kind.TAB,
        ip=ip,
        user_agent=_user_agent(request),
        revision=revision,
        tab_id=tab,
    )
    return _private(HttpResponse(status=204))


@require_http_methods(["GET"])
def proposal_media(request: HttpRequest, slug: str, media_id: int) -> HttpResponse:
    """A fresh URL for media in the customer's revision (the page asks when one expires).

    Same gate as the document itself: a published proposal, its latest revision not expired, a
    live session for this proposal (the cookie's Path covers /p/<slug>/...), and media the
    revision refers to. `?download=1` asks for a URL that saves the file.
    """
    found = Proposal.objects.filter(slug=slug, status=Proposal.Status.PUBLISHED).first()
    revision = publishing.latest_revision(found) if found else None
    if found is None or revision is None:
        raise Http404
    if publishing.is_expired(revision) or not access.has_customer_session(request, found):
        return _private(JsonResponse({"error": "no_session"}, status=403))
    download = request.GET.get("download") == "1"
    return _media_answer(media.document_media_url(revision.document, media_id, download=download))


@require_http_methods(["GET"])
def proposal_preview_media(request: HttpRequest, token: str, media_id: int) -> HttpResponse:
    """The preview's counterpart of `proposal_media`: the signed link is the gate, the current
    draft is the document."""
    try:
        found = proposals.proposal_for_preview(token)
    except proposals.ExpiredPreviewToken:
        return _private(JsonResponse({"error": "expired"}, status=410))
    except proposals.BadPreviewToken:
        raise Http404 from None
    download = request.GET.get("download") == "1"
    return _media_answer(media.document_media_url(found.document, media_id, download=download))


def proposal_preview(request: HttpRequest, token: str) -> HttpResponse:
    """A signed, short-lived link to the proposal as the customer will see it."""
    try:
        found = proposals.proposal_for_preview(token)
    except proposals.ExpiredPreviewToken:
        response = HttpResponse(
            "미리보기 링크가 만료되었습니다. 관리자 화면에서 다시 열어 주세요.",
            status=410,
            content_type="text/plain; charset=utf-8",
        )
    except proposals.BadPreviewToken:
        raise Http404 from None
    else:
        data = proposals.page_data(found, preview=True, media_endpoint=f"/preview/{token}/media")
        response = render_shell(
            request, _proposal_meta(data.platform_mode), data=data.model_dump(mode="json")
        )
    return _private(response)


@require_http_methods(["GET"])
def proposal_print_media(request: HttpRequest, token: str, media_id: int) -> HttpResponse:
    """The print page's counterpart of `proposal_media`: the print token is the gate and the
    revision it names is the document."""
    try:
        revision = proposals.revision_for_print(token)
    except proposals.ExpiredPrintToken:
        return _private(JsonResponse({"error": "expired"}, status=410))
    except proposals.BadPrintToken:
        raise Http404 from None
    return _media_answer(media.document_media_url(revision.document, media_id))


def proposal_print(request: HttpRequest, token: str) -> HttpResponse:
    """One revision as the print layout (every tab, QR codes for audio / video). Opened by the PDF
    renderer with a short-lived signed token; no customer session, never indexed."""
    try:
        revision = proposals.revision_for_print(token)
    except proposals.ExpiredPrintToken:
        response = HttpResponse(
            "인쇄 링크가 만료되었습니다.", status=410, content_type="text/plain; charset=utf-8"
        )
    except proposals.BadPrintToken:
        raise Http404 from None
    else:
        data = proposals.print_page_data(revision, token=token)
        response = render_shell(
            request, _proposal_meta(data.platform_mode), data=data.model_dump(mode="json")
        )
    return _private(response)


@require_http_methods(["GET"])
def proposal_draft_print_media(request: HttpRequest, token: str, media_id: int) -> HttpResponse:
    """`proposal_print_media` for the draft print link (#225): the draft's own document."""
    try:
        found, _platform = proposals.draft_for_print(token)
    except proposals.ExpiredPrintToken:
        return _private(JsonResponse({"error": "expired"}, status=410))
    except proposals.BadPrintToken:
        raise Http404 from None
    return _media_answer(media.document_media_url(found.document, media_id))


def proposal_draft_print(request: HttpRequest, token: str) -> HttpResponse:
    """The proposal's current draft as the print layout, for an on-the-spot PDF (#225,
    services/pdf.py::export_draft). Same rules as `proposal_print`."""
    try:
        found, platform = proposals.draft_for_print(token)
    except proposals.ExpiredPrintToken:
        response = HttpResponse(
            "인쇄 링크가 만료되었습니다.", status=410, content_type="text/plain; charset=utf-8"
        )
    except proposals.BadPrintToken:
        raise Http404 from None
    else:
        data = proposals.draft_print_page_data(found, token=token, platform=platform)
        response = render_shell(
            request, _proposal_meta(platform), data=data.model_dump(mode="json")
        )
    return _private(response)


def og_card_image(request: HttpRequest, kind: str, slug: str) -> HttpResponse:
    """The generated link-preview card of a public item or post with a cover (#125)."""
    if kind not in ("work", "blog"):
        raise Http404
    if kind == "work" and og_card.source_of("work", slug) is None:
        current = renamed_to(slug)
        if current is not None:
            return HttpResponsePermanentRedirect(og_card.card_path("work", current))
    source = og_card.source_of(kind, slug)  # type: ignore[arg-type]
    if source is None:
        if _exists_without_cover(kind, slug):
            return _default_card()
        raise Http404
    etag = f'"{source.key[:32]}"'
    if request.headers.get("If-None-Match") == etag:
        response = HttpResponse(status=304)
        response["ETag"] = etag
        response["Cache-Control"] = "public, max-age=86400"
        return response
    try:
        png = og_card.card_png(source)
    except og_card.CardFailed as exc:
        logging.getLogger(__name__).warning("og card %s/%s failed: %s", kind, slug, exc)
        return _default_card()
    response = HttpResponse(png, content_type="image/png")
    response["ETag"] = etag
    response["Cache-Control"] = "public, max-age=86400"
    return response


def _exists_without_cover(kind: str, slug: str) -> bool:
    if kind == "work":
        return PortfolioItem.objects.filter(slug=slug, is_public=True).exists()
    return blog.public_detail(slug) is not None


def _default_card() -> HttpResponse:
    """Stand-in when the card cannot be made: the default image, not kept for long."""
    path = Path(__file__).resolve().parent / "static" / "core" / "og-default.png"
    response = HttpResponse(path.read_bytes(), content_type="image/png")
    response["Cache-Control"] = "public, max-age=60"
    return response


def work_hub(request: HttpRequest) -> HttpResponse:
    """/work has no page of its own: the portfolio list is the home's section (#111)."""
    return HttpResponsePermanentRedirect("/#home-portfolio")


def privacy(request: HttpRequest) -> HttpResponse:
    """/privacy (issue 201): the company site's privacy policy; the copy is services/legal.py."""
    data = {
        "policy": legal.policy(),
        "availability": site_availability(),
        "business": site_business(),
    }
    return render_shell(
        request,
        PageMeta(
            title=f"{legal.TITLE} | {SITE_NAME}",
            description=f"샌드코프 회사 사이트 개인정보처리방침 (시행 {legal.effective_on_text()})",
            robots=INDEX,
            image=DEFAULT_OG_IMAGE,
            image_alt=DEFAULT_OG_IMAGE_ALT,
        ),
        data=data,
        count_visit=True,
        body=public_html.privacy_body(data),
    )


def services_hub(request: HttpRequest) -> HttpResponse:
    """/services has no page of its own: the rows are the home's section (issue 163)."""
    return HttpResponsePermanentRedirect("/#home-services")


def service(request: HttpRequest, slug: str) -> HttpResponse:
    """/services/<slug>: a published service with its copy (content.Service, issue 215)."""
    offering = offerings.get(slug)
    if offering is None:
        raise Http404
    data = {"offering": offering, "availability": site_availability(), "business": site_business()}
    cover = offering["cover"]  # its own image in the link preview, else the site's default
    size = (
        (cover["width"], cover["height"]) if cover and cover["width"] and cover["height"] else None
    )
    return render_shell(
        request,
        PageMeta(
            title=f"{offering['name']} | {SITE_NAME}",
            description=offering["summary"],
            robots=INDEX,
            image=cover["url"] if cover else DEFAULT_OG_IMAGE,
            image_alt=cover["alt"] if cover else DEFAULT_OG_IMAGE_ALT,
            image_size=size,
            jsonld=service_jsonld(
                site_url=settings.SITE_URL,
                url=_absolute(request, offerings.path(slug)),
                offering=offering,
            ),
        ),
        data=data,
        count_visit=True,
        body=public_html.service_body(data),
    )


def work(request: HttpRequest, slug: str) -> HttpResponse:
    detail = public_detail(slug)
    if detail is None:
        current = renamed_to(slug)
        if current is None:
            raise Http404
        return HttpResponsePermanentRedirect(f"/work/{current}")
    card = detail["card"]
    cover_card = og_card.preview_path("work", slug)
    image = cover_card or DEFAULT_OG_IMAGE
    data = {**detail, "availability": site_availability(), "business": site_business()}
    return render_shell(
        request,
        PageMeta(
            title=f"{card['title']} | {SITE_NAME}",
            description=card["summary"] or DEFAULT_WORK_DESCRIPTION,
            robots=INDEX,
            image=image,
            image_alt=card["title"] if cover_card else DEFAULT_OG_IMAGE_ALT,
            image_size=OG_IMAGE_SIZE,
            jsonld=work_jsonld(
                url=_absolute(request, f"/work/{card['slug']}"),
                card=card,
                service_url=detail["service_url"],
                image=request.build_absolute_uri(image),
                publisher=_publisher(),
            ),
        ),
        data=data,
        count_visit=True,
        body=public_html.work_body(data),
    )


def robots_txt(request: HttpRequest) -> HttpResponse:
    body = (
        "User-agent: *\nDisallow: /p/\nDisallow: /preview/\nDisallow: /print/\n\n"
        f"Sitemap: {settings.SITE_URL}/sitemap.xml\n"
    )
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


def sitemap_xml(request: HttpRequest) -> HttpResponse:
    works = public_modified()
    posts = blog.public_modified_by_slug()
    tip_stamps = tips.public_modified_by_slug()
    stamps = [*works.values(), *posts.values()]
    latest = max(stamps) if stamps else None
    entries: list[tuple[str, date | None]] = [
        ("/", latest),  # the home lists both, so it changed when either did
        *((f"/work/{slug}", at) for slug, at in works.items()),
        # an empty blog is not worth a crawl
        *([("/blog", max(posts.values()))] if posts else []),
        *((f"/blog/{slug}", at) for slug, at in posts.items()),
        # issue 203: published tips only; an empty /tips is left out like an empty blog
        *([("/tips", max(tip_stamps.values()))] if tip_stamps else []),
        *((tips.tip_path(slug), at) for slug, at in tip_stamps.items()),
        *offerings.page_stamps(),
        (legal.PATH, legal.EFFECTIVE_ON),
    ]
    urls = "".join(
        f"<url><loc>{escape(settings.SITE_URL + path)}</loc>"
        + (f"<lastmod>{at.isoformat()}</lastmod>" if at else "")
        + "</url>"
        for path, at in entries
    )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    )
    return HttpResponse(body, content_type="application/xml; charset=utf-8")


def _absolute(request: HttpRequest, path: str) -> str:
    return request.build_absolute_uri(path)


def _publisher() -> dict[str, str]:
    return {"@type": "Organization", "name": SITE_NAME, "url": settings.SITE_URL}


def blog_index(request: HttpRequest) -> HttpResponse:
    """/blog: the newest-first list, `?tag=` narrows it, `?page=` pages it (20 per page)."""
    tag = request.GET.get("tag", "").strip()
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        raise Http404 from None
    listing = blog.public_listing(tag, page)
    if listing is None:
        raise Http404
    narrowed = bool(tag) or page > 1  # the same posts as /blog: keep them out of the index
    title = f"{tag} · {BLOG_TITLE}" if tag else BLOG_TITLE
    data = {**listing, "availability": site_availability(), "business": site_business()}
    return render_shell(
        request,
        PageMeta(
            title=f"{title} | {SITE_NAME}",
            description=BLOG_DESCRIPTION,
            robots="noindex, follow" if narrowed else INDEX,
            image=DEFAULT_OG_IMAGE,
            image_alt=DEFAULT_OG_IMAGE_ALT,
            jsonld={
                "@context": "https://schema.org",
                "@type": "CollectionPage",
                "name": BLOG_TITLE,
                "description": BLOG_DESCRIPTION,
                "url": _absolute(request, "/blog"),
                "inLanguage": "ko",
                "isPartOf": {
                    "@type": "Blog",
                    "name": BLOG_TITLE,
                    "url": _absolute(request, "/blog"),
                },
                "publisher": _publisher(),
            },
        ),
        data=data,
        count_visit=True,
        body=public_html.blog_index_body(listing, data),
    )


def blog_post(request: HttpRequest, slug: str) -> HttpResponse:
    detail = blog.public_detail(slug)
    if detail is None:
        raise Http404
    card = detail["card"]
    description = card["summary"] or BLOG_DESCRIPTION
    modified = blog.public_modified_at(slug) or card["published_at"]
    cover_card = og_card.preview_path("blog", slug)
    image = cover_card or DEFAULT_OG_IMAGE
    data = {**detail, "availability": site_availability(), "business": site_business()}
    return render_shell(
        request,
        PageMeta(
            title=f"{card['title']} | {SITE_NAME}",
            description=description,
            robots=INDEX,
            image=image,
            image_alt=card["title"] if cover_card else DEFAULT_OG_IMAGE_ALT,
            image_size=OG_IMAGE_SIZE,
            og_type="article",
            published_time=card["published_at"],
            modified_time=modified,
            tags=tuple(card["tags"]),
            jsonld={
                "@context": "https://schema.org",
                "@type": "BlogPosting",
                "headline": card["title"],
                "description": description,
                "datePublished": card["published_at"],
                "dateModified": modified,
                "url": _absolute(request, f"/blog/{slug}"),
                "mainEntityOfPage": _absolute(request, f"/blog/{slug}"),
                "inLanguage": "ko",
                "keywords": ", ".join(card["tags"]),
                "author": _publisher(),
                "publisher": _publisher(),
                "image": request.build_absolute_uri(image),
            },
        ),
        data=data,
        count_visit=True,
        body=public_html.blog_post_body(data),
    )


def blog_preview(request: HttpRequest, token: str) -> HttpResponse:
    """A signed, short-lived link to a post (draft or not) as /blog/<slug> will show it (#147).
    Like the proposal preview: noindex, no-store, no visit counted, no server HTML."""
    try:
        detail = blog.preview_detail(token)
    except preview.ExpiredPreviewToken:
        response = HttpResponse(
            "미리보기 링크가 만료되었습니다. 링크를 다시 발급해 주세요.",
            status=410,
            content_type="text/plain; charset=utf-8",
        )
    except preview.BadPreviewToken:
        raise Http404 from None
    else:
        data = {**detail, "availability": site_availability(), "business": site_business()}
        meta = PageMeta(
            title=f"미리보기 · {detail['card']['title']} | {SITE_NAME}",
            description=BLOG_DESCRIPTION,
            robots=NOINDEX,
        )
        response = render_shell(request, meta, data=data)
    return _private(response)


BLOG_TITLE = f"{SITE_NAME} 기록"
BLOG_DESCRIPTION = "샌드코프가 만들며 배운 것을 적는 블로그"
FEED_SIZE = 30


def blog_feed(request: HttpRequest) -> HttpResponse:
    """RSS 2.0 of the newest published posts. Absolute links from SITE_URL (no request host)."""
    items = blog.feed_items(FEED_SIZE)
    home = f"{settings.SITE_URL}/blog"

    def item_xml(post: blog.FeedItem) -> str:
        link = escape(f"{home}/{post.slug}")
        categories = "".join(f"<category>{escape(tag)}</category>" for tag in post.tags)
        return (
            f"<item><title>{escape(post.title)}</title><link>{link}</link>"
            f"<description>{escape(post.summary)}</description>"
            f"<pubDate>{format_datetime(post.published_at)}</pubDate>"
            f'<guid isPermaLink="true">{link}</guid>{categories}</item>'
        )

    last_build = (
        f"<lastBuildDate>{format_datetime(items[0].published_at)}</lastBuildDate>" if items else ""
    )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
        f"<title>{escape(BLOG_TITLE)}</title><link>{escape(home)}</link>"
        f"<description>{escape(BLOG_DESCRIPTION)}</description><language>ko</language>"
        f'<atom:link href="{escape(home)}/feed.xml" rel="self" type="application/rss+xml"/>'
        f"{last_build}{''.join(item_xml(p) for p in items)}</channel></rss>"
    )
    response = HttpResponse(body, content_type="application/rss+xml; charset=utf-8")
    response["Cache-Control"] = "public, max-age=300"
    return response


TIPS_TITLE = "개발 팁"
TIPS_DESCRIPTION = "프로젝트와 상관없이 다시 쓸 수 있는 개발 요령: 문제, 원인, 해법, 짧은 코드 예시"


def tips_index(request: HttpRequest) -> HttpResponse:
    """/tips (issue 203): newest-first cards, `?category=` narrows them, `?page=` pages them (20
    per page). An unknown category or a page past the end is a 404, as on /blog."""
    category = request.GET.get("category", "").strip()
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        raise Http404 from None
    listing = tips.public_listing(category, page)
    if listing is None:
        raise Http404
    chosen = listing["category"]
    narrowed = chosen is not None or page > 1  # the same tips as /tips: keep them out of the index
    title = f"{chosen['label']} · {TIPS_TITLE}" if chosen else TIPS_TITLE
    data = {**listing, "availability": site_availability(), "business": site_business()}
    return render_shell(
        request,
        PageMeta(
            title=f"{title} | {SITE_NAME}",
            description=TIPS_DESCRIPTION,
            robots="noindex, follow" if narrowed else INDEX,
            image=DEFAULT_OG_IMAGE,
            image_alt=DEFAULT_OG_IMAGE_ALT,
            jsonld={
                "@context": "https://schema.org",
                "@type": "CollectionPage",
                "name": TIPS_TITLE,
                "description": TIPS_DESCRIPTION,
                "url": _absolute(request, "/tips"),
                "inLanguage": "ko",
                "publisher": _publisher(),
            },
        ),
        data=data,
        count_visit=True,
        body=public_html.tips_index_body(listing, data),
    )


def tip(request: HttpRequest, slug: str) -> HttpResponse:
    """/tips/<slug>: a published tip; a draft or an unknown slug is a 404. No cover, so the
    default preview image."""
    detail = tips.public_detail(slug)
    if detail is None:
        raise Http404
    card = detail["card"]
    description = card["summary"] or TIPS_DESCRIPTION
    modified = tips.public_modified_at(slug) or card["published_at"]
    labels = tuple(c["label"] for c in card["categories"])
    url = _absolute(request, tips.tip_path(slug))
    data = {**detail, "availability": site_availability(), "business": site_business()}
    return render_shell(
        request,
        PageMeta(
            title=f"{card['title']} | {SITE_NAME}",
            description=description,
            robots=INDEX,
            image=DEFAULT_OG_IMAGE,
            image_alt=DEFAULT_OG_IMAGE_ALT,
            og_type="article",
            published_time=card["published_at"],
            modified_time=modified,
            tags=labels,
            jsonld={
                "@context": "https://schema.org",
                "@type": "TechArticle",
                "headline": card["title"],
                "description": description,
                "datePublished": card["published_at"],
                "dateModified": modified,
                "url": url,
                "mainEntityOfPage": url,
                "inLanguage": "ko",
                "keywords": ", ".join(labels),
                "articleSection": TIPS_TITLE,
                "author": _publisher(),
                "publisher": _publisher(),
                "image": request.build_absolute_uri(DEFAULT_OG_IMAGE),
            },
        ),
        data=data,
        count_visit=True,
        body=public_html.tip_body(data),
    )


def tip_preview(request: HttpRequest, token: str) -> HttpResponse:
    """A signed, short-lived link to a tip (draft or not) as /tips/<slug> will show it. Like the
    blog preview: noindex, no-store, no visit counted, no server HTML."""
    try:
        detail = tips.preview_detail(token)
    except preview.ExpiredPreviewToken:
        response = HttpResponse(
            "미리보기 링크가 만료되었습니다. 링크를 다시 발급해 주세요.",
            status=410,
            content_type="text/plain; charset=utf-8",
        )
    except preview.BadPreviewToken:
        raise Http404 from None
    else:
        data = {**detail, "availability": site_availability(), "business": site_business()}
        meta = PageMeta(
            title=f"미리보기 · {detail['card']['title']} | {SITE_NAME}",
            description=TIPS_DESCRIPTION,
            robots=NOINDEX,
        )
        response = render_shell(request, meta, data=data)
    return _private(response)


def service_preview(request: HttpRequest, token: str) -> HttpResponse:
    """A signed, short-lived link to a service page (published or not) as /services/<slug> will
    show it (issue 215). Like the tip preview: noindex, no-store, no visit counted, no server
    HTML."""
    try:
        offering = offerings.preview_offering(token)
    except preview.ExpiredPreviewToken:
        response = HttpResponse(
            "미리보기 링크가 만료되었습니다. 링크를 다시 발급해 주세요.",
            status=410,
            content_type="text/plain; charset=utf-8",
        )
    except preview.BadPreviewToken:
        raise Http404 from None
    else:
        data = {
            "offering": offering,
            "availability": site_availability(),
            "business": site_business(),
        }
        meta = PageMeta(
            title=f"미리보기 · {offering['name']} | {SITE_NAME}",
            description=offering["summary"],
            robots=NOINDEX,
        )
        response = render_shell(request, meta, data=data)
    return _private(response)

"""HTML shell views: Django renders per-route <head> meta, then React mounts on #root.

Add a route by adding a view here that builds a PageMeta and calls render_shell.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from email.utils import format_datetime
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods, require_POST
from pydantic import BaseModel

from content.models import Proposal, ProposalEvent, ProposalRevision
from core.clientip import client_ip
from core.vite import entry_assets
from services import blog, media, pdf, proposals, publishing
from services import proposal_access as access
from services import proposal_events as events
from services.home import home_page, site_availability, site_business
from services.portfolio import public_detail, public_slugs

SITE_NAME = "Sandcorp"
INDEX = "index, follow"
NOINDEX = "noindex, nofollow"
DEFAULT_WORK_DESCRIPTION = "샌드코프 수행 사례"


@dataclass(frozen=True)
class PageMeta:
    title: str
    description: str
    robots: str
    image: str = ""
    og_type: str = "website"
    # schema.org JSON-LD for search engines; None for pages without one
    jsonld: Mapping[str, object] | None = None


# Proposal pages never leak customer names or amounts into meta or link previews.
_PROPOSAL_META = PageMeta(
    title=f"제안서 | {SITE_NAME}", description="샌드코프 제안서", robots=NOINDEX
)


def render_shell(
    request: HttpRequest,
    meta: PageMeta,
    status: int = 200,
    data: Mapping[str, object] | None = None,
    count_visit: bool = False,
) -> HttpResponse:
    """Render the shell. `data` is embedded as JSON in #page-data for React's first render.

    `count_visit` adds the sandcorp-metrics snippet (when METRICS_SNIPPET_URL is set). Only the
    public pages ask for it: print and preview pages are opened by the PDF renderer and the
    owner, proposals are private, and none of those are visits."""
    context = {
        "site_name": SITE_NAME,
        "data": data,
        "meta": meta,
        "og_image": request.build_absolute_uri(meta.image) if meta.image else "",
        "jsonld": _jsonld(meta.jsonld),
        "canonical": request.build_absolute_uri(request.path),
        "assets": entry_assets(),
        "metrics_snippet_url": settings.METRICS_SNIPPET_URL if count_visit else "",
        "metrics_site_key": settings.METRICS_SITE_KEY,
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
        PageMeta(title=SITE_NAME, description=page.description, robots=INDEX),
        data=page.data,
        count_visit=True,
    )


def _customer_page(request: HttpRequest, data: BaseModel, status: int = 200) -> HttpResponse:
    response = render_shell(
        request, _PROPOSAL_META, status=status, data=data.model_dump(mode="json")
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
        valid_until=revision.valid_until, supplier=proposals.supplier()
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
        form = proposals.CodeScreenData(error=attempt.value, csrf_token=get_token(request))
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
        error="blocked" if blocked else None, csrf_token=get_token(request)
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
    except (ValueError, AttributeError):
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
        response = render_shell(request, _PROPOSAL_META, data=data.model_dump(mode="json"))
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
        response = render_shell(request, _PROPOSAL_META, data=data.model_dump(mode="json"))
    return _private(response)


def work(request: HttpRequest, slug: str) -> HttpResponse:
    detail = public_detail(slug)
    if detail is None:
        raise Http404
    card = detail["card"]
    return render_shell(
        request,
        PageMeta(
            title=f"{card['title']} | {SITE_NAME}",
            description=card["summary"] or DEFAULT_WORK_DESCRIPTION,
            robots=INDEX,
            image=card["cover_url"],
        ),
        data={**detail, "availability": site_availability(), "business": site_business()},
        count_visit=True,
    )


def robots_txt(request: HttpRequest) -> HttpResponse:
    body = (
        "User-agent: *\nDisallow: /p/\nDisallow: /preview/\nDisallow: /print/\n\n"
        f"Sitemap: {settings.SITE_URL}/sitemap.xml\n"
    )
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


def sitemap_xml(request: HttpRequest) -> HttpResponse:
    posts = blog.public_slugs()
    paths = [
        "/",
        *(f"/work/{slug}" for slug in public_slugs()),
        *(["/blog"] if posts else []),  # an empty blog is not worth a crawl
        *(f"/blog/{slug}" for slug in posts),
    ]
    urls = "".join(f"<url><loc>{escape(settings.SITE_URL + path)}</loc></url>" for path in paths)
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
    return render_shell(
        request,
        PageMeta(
            title=f"{title} | {SITE_NAME}",
            description=BLOG_DESCRIPTION,
            robots="noindex, follow" if narrowed else INDEX,
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
        data={**listing, "availability": site_availability(), "business": site_business()},
        count_visit=True,
    )


def blog_post(request: HttpRequest, slug: str) -> HttpResponse:
    detail = blog.public_detail(slug)
    if detail is None:
        raise Http404
    card = detail["card"]
    description = card["summary"] or BLOG_DESCRIPTION
    return render_shell(
        request,
        PageMeta(
            title=f"{card['title']} | {SITE_NAME}",
            description=description,
            robots=INDEX,
            image=card["cover_url"],
            og_type="article",
            jsonld={
                "@context": "https://schema.org",
                "@type": "BlogPosting",
                "headline": card["title"],
                "description": description,
                "datePublished": card["published_at"],
                "url": _absolute(request, f"/blog/{slug}"),
                "mainEntityOfPage": _absolute(request, f"/blog/{slug}"),
                "inLanguage": "ko",
                "keywords": ", ".join(card["tags"]),
                "author": _publisher(),
                "publisher": _publisher(),
                **({"image": card["cover_url"]} if card["cover_url"] else {}),
            },
        ),
        data={**detail, "availability": site_availability(), "business": site_business()},
        count_visit=True,
    )


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

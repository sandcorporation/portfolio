"""HTML shell views: Django renders per-route <head> meta, then React mounts on #root.

Add a route by adding a view here that builds a PageMeta and calls render_shell.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from content.models import Proposal
from core.vite import entry_assets
from services import proposals
from services.home import home_page
from services.portfolio import public_detail, public_slugs

SITE_NAME = "Sandcorp"
INDEX = "index, follow"
NOINDEX = "noindex, nofollow"
DEFAULT_WORK_DESCRIPTION = "샌드코퍼레이션 수행 사례"


@dataclass(frozen=True)
class PageMeta:
    title: str
    description: str
    robots: str
    image: str = ""


# Proposal pages never leak customer names or amounts into meta or link previews.
_PROPOSAL_META = PageMeta(
    title=f"제안서 | {SITE_NAME}", description="샌드코퍼레이션 제안서", robots=NOINDEX
)


def render_shell(
    request: HttpRequest,
    meta: PageMeta,
    status: int = 200,
    data: Mapping[str, object] | None = None,
) -> HttpResponse:
    """Render the shell. `data` is embedded as JSON in #page-data for React's first render."""
    context = {
        "site_name": SITE_NAME,
        "data": data,
        "meta": meta,
        "og_image": request.build_absolute_uri(meta.image) if meta.image else "",
        "canonical": request.build_absolute_uri(request.path),
        "assets": entry_assets(),
    }
    return render(request, "core/shell.html", context, status=status)


def home(request: HttpRequest) -> HttpResponse:
    page = home_page()
    return render_shell(
        request,
        PageMeta(title=SITE_NAME, description=page.description, robots=INDEX),
        data=page.data,
    )


def proposal(request: HttpRequest, slug: str) -> HttpResponse:
    # Only a published proposal has a customer page (the content arrives with #12). A draft or a
    # revoked one is a 404, indistinguishable from a slug that never existed.
    if not Proposal.objects.filter(slug=slug, status=Proposal.Status.PUBLISHED).exists():
        raise Http404
    return render_shell(request, _PROPOSAL_META)


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
        data = proposals.page_data(found, preview=True)
        response = render_shell(request, _PROPOSAL_META, data=data.model_dump(mode="json"))
    response["Cache-Control"] = "no-store"
    response["X-Robots-Tag"] = NOINDEX
    return response


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
        data=detail,
    )


def robots_txt(request: HttpRequest) -> HttpResponse:
    body = (
        "User-agent: *\nDisallow: /p/\nDisallow: /preview/\n\n"
        f"Sitemap: {settings.SITE_URL}/sitemap.xml\n"
    )
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


def sitemap_xml(request: HttpRequest) -> HttpResponse:
    paths = ["/", *(f"/work/{slug}" for slug in public_slugs())]
    urls = "".join(f"<url><loc>{escape(settings.SITE_URL + path)}</loc></url>" for path in paths)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    )
    return HttpResponse(body, content_type="application/xml; charset=utf-8")

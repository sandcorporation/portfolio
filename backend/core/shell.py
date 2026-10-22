"""HTML shell views: Django renders per-route <head> meta, then React mounts on #root.

Add a route by adding a view here that builds a PageMeta and calls render_shell.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from core.vite import entry_assets
from services.home import home_page

SITE_NAME = "Sandcorp"
INDEX = "index, follow"
NOINDEX = "noindex, nofollow"


@dataclass(frozen=True)
class PageMeta:
    title: str
    description: str
    robots: str


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
    # Proposal pages never leak customer names or amounts into meta or previews.
    return render_shell(
        request,
        PageMeta(
            title=f"제안서 | {SITE_NAME}",
            description="샌드코퍼레이션 제안서",
            robots=NOINDEX,
        ),
    )

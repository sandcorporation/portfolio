"""Site-shaped 404/500 pages (issue 33).

Both are plain server templates with inline CSS and no React bundle: the public shell would let
React redraw over the page ("사이트를 준비하고 있습니다"), and the 500 page must render without the
DB, context processors or the static manifest. JSON/MCP/admin paths keep Django's plain 404."""

from pathlib import Path

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound, HttpResponseServerError
from django.template.loader import render_to_string

_DIR = Path(__file__).resolve().parent / "templates" / "core" / "errors"
_NOT_FOUND = "<h1>Not Found</h1><p>The requested resource was not found on this server.</p>"


def _machine_path(path: str) -> bool:
    admin = "/" + settings.ADMIN_PATH.strip("/")
    return (
        path.startswith(("/api/", "/mcp", "/.well-known/", "/static/"))
        or path == admin
        or path.startswith(admin + "/")
    )


def not_found(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    if _machine_path(request.path):
        return HttpResponseNotFound(_NOT_FOUND)
    html = render_to_string("core/errors/404.html")
    response = HttpResponseNotFound(html)
    response["Cache-Control"] = "no-store"
    return response


def server_error(request: HttpRequest) -> HttpResponse:
    """Static file read only: no DB, no template context, no manifest."""
    response = HttpResponseServerError((_DIR / "500.html").read_text(encoding="utf-8"))
    response["Cache-Control"] = "no-store"
    return response

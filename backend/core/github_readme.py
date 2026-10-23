"""GET /github/readme/<personal|org>.md: the generated GitHub profile READMEs (public data only)."""

import hashlib

from django.http import HttpRequest, HttpResponse, HttpResponseNotModified
from django.views.decorators.http import require_safe

from services import github_readme

CACHE_SECONDS = 300


def _respond(request: HttpRequest, kind: github_readme.Kind) -> HttpResponse:
    body = github_readme.render(kind)
    etag = '"' + hashlib.sha256(body.encode()).hexdigest()[:32] + '"'
    if etag in (v.strip() for v in request.headers.get("If-None-Match", "").split(",")):
        response: HttpResponse = HttpResponseNotModified()
    else:
        response = HttpResponse(body, content_type="text/markdown; charset=utf-8")
    response["ETag"] = etag
    response["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"
    return response


@require_safe
def personal(request: HttpRequest) -> HttpResponse:
    return _respond(request, "personal")


@require_safe
def org(request: HttpRequest) -> HttpResponse:
    return _respond(request, "org")

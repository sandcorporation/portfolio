"""POST /api/inquiries: the home form and the news site's server-to-server relay.

Two callers, one route (the contract with the news service, issue #17):
  - A server sends `X-Inquiry-Secret` equal to `INQUIRY_SHARED_SECRET`. It is believed about
    `site` and skips the honeypot and IP limit (it applied its own). CSRF does not apply: no
    browser holds that secret, so a cross-site page cannot forge such a request.
  - A browser sends no secret. This is the CSRF-sensitive path, but it keeps no session or cookie,
    so there is nothing for a forged request to ride on; the form is anonymous by design. What is
    left to stop is another site's page filling the form in visitors' browsers, so the request
    must be same-origin: JSON only (a cross-site <form> cannot send it, and fetch would need a
    CORS preflight we never grant) and an `Origin`, when sent, must be this site or trusted.
Status codes: 2xx saved (or silently dropped by the honeypot), 4xx refused for good, 429 slow
down, 5xx never because of Discord.
"""

import hmac
from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpRequest
from ninja import Router, Schema, Status

from core.clientip import client_ip
from services import inquiries

router = Router(auth=None, tags=["inquiries"])


class Receipt(Schema):
    ok: bool = True


class Refusal(Schema):
    detail: str


def has_valid_secret(request: HttpRequest) -> bool:
    expected: str = settings.INQUIRY_SHARED_SECRET
    given = request.headers.get("X-Inquiry-Secret", "")
    if not expected or not given:  # an unset secret must never match an empty header
        return False
    return hmac.compare_digest(given.encode(), expected.encode())


def is_same_origin(request: HttpRequest) -> bool:
    if request.content_type != "application/json":
        return False
    origin = request.headers.get("Origin")
    if origin is None:  # not a browser cross-site request (those always carry Origin)
        return True
    if origin in settings.CSRF_TRUSTED_ORIGINS:
        return True
    parts = urlsplit(origin)
    return parts.scheme == request.scheme and parts.netloc == request.get_host()


@router.post("", response={201: Receipt, 403: Refusal})
def create_inquiry(
    request: HttpRequest, body: inquiries.NewInquiry
) -> Status[Receipt] | Status[Refusal]:
    trusted = has_valid_secret(request)
    if not trusted and not is_same_origin(request):
        return Status(403, Refusal(detail="허용되지 않은 요청입니다"))
    inquiries.submit(body, trusted=trusted, ip=client_ip(request))
    return Status(201, Receipt())

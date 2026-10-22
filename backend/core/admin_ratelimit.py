"""TEMPORARY (issue #25): rate limit for the Django admin password login.

Everything for this lives here plus three hooks that #7 removes together with this file:
  - `core.admin_ratelimit.AdminLoginRateLimitMiddleware` in settings.MIDDLEWARE
  - `ADMIN_LOGIN_*` and `CACHES` in settings.py
  - `createcachetable` in deploy/deploy.sh (and tests/test_admin_ratelimit.py)

Counters live in the Django cache, which is a DB cache so both gunicorn workers share them.
"""

import hashlib
from collections.abc import Callable

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse


def client_ip(request: HttpRequest) -> str:
    """The address NPMplus saw. It appends the peer to X-Forwarded-For, so the entry
    `ADMIN_LOGIN_PROXY_HOPS` from the right is trustworthy; the left part is client-supplied
    and forgeable. With 0 hops (no proxy) only REMOTE_ADDR is used."""
    hops: int = settings.ADMIN_LOGIN_PROXY_HOPS
    forwarded = [
        p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()
    ]
    if hops > 0 and len(forwarded) >= hops:
        return str(forwarded[-hops])
    return str(request.META.get("REMOTE_ADDR", ""))


def _key(kind: str, value: str) -> str:
    return f"admin-login:{kind}:{hashlib.sha256(value.lower().encode()).hexdigest()[:32]}"


class AdminLoginRateLimitMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.method != "POST" or request.path != f"/{settings.ADMIN_PATH}login/":
            return self.get_response(request)
        keys = [
            _key("ip", client_ip(request)),
            _key("user", request.POST.get("username", "")),
        ]
        limit = settings.ADMIN_LOGIN_MAX_FAILURES
        # Checked before authentication, so a correct password is refused while locked.
        if any(cache.get(k, 0) >= limit for k in keys):
            response = HttpResponse(
                "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요.", status=429
            )
            response["Retry-After"] = str(settings.ADMIN_LOGIN_WINDOW_SECONDS)
            return response
        response = self.get_response(request)
        if response.status_code == 302:  # logged in
            cache.delete(keys[1])
        else:  # the form came back with an error
            for k in keys:
                cache.set(k, cache.get(k, 0) + 1, settings.ADMIN_LOGIN_WINDOW_SECONDS)
        return response

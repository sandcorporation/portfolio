"""The customer's way into /p/<slug>: the access code, its session cookie and the failure limit.

Session: a signed cookie per proposal (name and Path carry the slug; HttpOnly, Secure, Lax) that
lasts `PROPOSAL_SESSION_MAX_AGE`. Its value is when the current code was issued, so reissuing the
code ends every session opened with the old one. Locking deletes the cookie.

Failure limit: wrong codes are counted per proposal and client IP in the Django cache (a DB cache,
shared by every worker). At `PROPOSAL_CODE_MAX_FAILURES` the pair is blocked for
`PROPOSAL_CODE_BLOCK_SECONDS`, and while blocked even the right code is refused.
"""

import enum
import hashlib

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse

from content.models import Proposal, ProposalRevision
from services.publishing import code_matches


class Attempt(enum.Enum):
    OPENED = "opened"
    WRONG = "wrong"
    BLOCKED = "blocked"


# --- hooks for owner alerts (#18 sends them to Discord) ---


def on_blocked(p: Proposal, ip: str) -> None:
    """Called once when a proposal + IP pair becomes blocked. #18: alert the owner here."""


def on_opened(p: Proposal, revision: ProposalRevision) -> None:
    """Called when the right code opens a customer session. #18: the "viewed" event goes here."""


# --- the session cookie ---


def cookie_name(slug: str) -> str:
    return f"proposal_{slug}"  # slugs are URL-safe base64, valid in a cookie name


def cookie_path(slug: str) -> str:
    return f"/p/{slug}"


def _salt(slug: str) -> str:
    return f"proposal-session:{slug}"


def _stamp(p: Proposal) -> str:
    assert p.access_code_issued_at is not None
    return p.access_code_issued_at.isoformat()


def has_customer_session(request: HttpRequest, p: Proposal) -> bool:
    """Whether this request carries a live session for `p` (signed for it, younger than the
    session age, made with the current code). Callers check `p.status` themselves."""
    if p.access_code_issued_at is None:
        return False
    value = request.get_signed_cookie(
        cookie_name(p.slug),
        default=None,
        salt=_salt(p.slug),
        max_age=settings.PROPOSAL_SESSION_MAX_AGE,
    )
    return value is not None and value == _stamp(p)


def start_customer_session(response: HttpResponse, p: Proposal) -> None:
    response.set_signed_cookie(
        cookie_name(p.slug),
        _stamp(p),
        salt=_salt(p.slug),
        max_age=settings.PROPOSAL_SESSION_MAX_AGE,
        path=cookie_path(p.slug),
        secure=True,
        httponly=True,
        samesite="Lax",
    )


def end_customer_session(response: HttpResponse, slug: str) -> None:
    response.delete_cookie(cookie_name(slug), path=cookie_path(slug), samesite="Lax")


# --- the failure limit ---


def _failures_key(slug: str, ip: str) -> str:
    return f"proposal-code:{slug}:{hashlib.sha256(ip.encode()).hexdigest()[:32]}"


def is_blocked(p: Proposal, ip: str) -> bool:
    failures: int = cache.get(_failures_key(p.slug, ip), 0)
    return failures >= settings.PROPOSAL_CODE_MAX_FAILURES


def _count_failure(p: Proposal, ip: str) -> None:
    key = _failures_key(p.slug, ip)
    window: int = settings.PROPOSAL_CODE_BLOCK_SECONDS
    cache.add(key, 0, window)  # starts the window only once
    try:
        failures = cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, window)
        failures = 1
    if failures == settings.PROPOSAL_CODE_MAX_FAILURES:
        cache.set(key, failures, window)  # the block lasts a full window from now
        on_blocked(p, ip)


def try_code(p: Proposal, raw_code: str, ip: str) -> Attempt:
    """Check a typed code. The caller starts the session on OPENED."""
    if is_blocked(p, ip):
        return Attempt.BLOCKED
    if not code_matches(p, raw_code):
        _count_failure(p, ip)
        return Attempt.BLOCKED if is_blocked(p, ip) else Attempt.WRONG
    cache.delete(_failures_key(p.slug, ip))
    return Attempt.OPENED

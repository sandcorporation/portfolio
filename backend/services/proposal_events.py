"""What customers do on a published proposal (#18): the event log and the owner alerts.

Events: code accepted / wrong / blocked, a view, a tab switch, a PDF download, each with the time,
revision, IP and User-Agent (clipped to 255). The owner preview and the print page never call in
here, so they leave nothing.

A "view" is any page load by a customer with a session, so a returning customer shows up as "looked
again at 14:02". Reloads do not pile up: the same revision from the same IP and User-Agent within
`VIEW_DEDUPE_SECONDS` (30 minutes) is one view. (The session cookie carries no id of its own; IP +
User-Agent is the closest stand-in for "the same session" without adding state to it.)

The alert "○○사가 vN을 처음 열었습니다" goes out once per revision: the first view is stored with
`first=True`, and a partial unique constraint on (revision) lets only one of two simultaneous
first views win. Alerts never raise: a Discord outage must not fail a customer request.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from adapters.notify import Field, Notification, get_notifier
from content.models import Proposal, ProposalEvent, ProposalRevision
from services.errors import NotFound

logger = logging.getLogger(__name__)

VIEW_DEDUPE_SECONDS = 30 * 60
USER_AGENT_MAX = 255
TAB_LIMIT = 120  # tab events per proposal and IP ...
TAB_WINDOW_SECONDS = 600  # ... per this window


def record(
    p: Proposal,
    kind: ProposalEvent.Kind,
    *,
    ip: str,
    user_agent: str,
    revision: ProposalRevision | None = None,
    tab_id: str = "",
) -> ProposalEvent:
    return ProposalEvent.objects.create(
        proposal=p,
        revision=revision,
        kind=kind,
        ip=ip[:45],
        user_agent=user_agent[:USER_AGENT_MAX],
        tab_id=tab_id[:60],
    )


def record_view(p: Proposal, revision: ProposalRevision, *, ip: str, user_agent: str) -> bool:
    """Log a customer's page load; returns whether a new view event was stored. The first view of
    the revision also alerts the owner."""
    user_agent = user_agent[:USER_AGENT_MAX]
    since = timezone.now() - timedelta(seconds=VIEW_DEDUPE_SECONDS)
    if ProposalEvent.objects.filter(
        revision=revision,
        kind=ProposalEvent.Kind.VIEWED,
        ip=ip[:45],
        user_agent=user_agent,
        created_at__gte=since,
    ).exists():
        return False
    first = not ProposalEvent.objects.filter(revision=revision, first=True).exists()
    try:
        with transaction.atomic():
            event = ProposalEvent.objects.create(
                proposal=p,
                revision=revision,
                kind=ProposalEvent.Kind.VIEWED,
                ip=ip[:45],
                user_agent=user_agent,
                first=first,
            )
    except IntegrityError:  # someone else's first view got in between
        event = record(
            p, ProposalEvent.Kind.VIEWED, ip=ip, user_agent=user_agent, revision=revision
        )
    if event.first:
        alert(_first_view(p, revision, ip))
    return True


def tab_allowed(p: Proposal, ip: str) -> bool:
    """Count one tab event against the per-proposal-and-IP limit; False once it is used up."""
    key = f"proposal-tab:{p.slug}:{ip}"
    cache.add(key, 0, TAB_WINDOW_SECONDS)
    try:
        return int(cache.incr(key)) <= TAB_LIMIT
    except ValueError:  # expired between add and incr
        cache.set(key, 1, TAB_WINDOW_SECONDS)
        return True


# --- alerts ---


def alert(notification: Notification) -> bool:
    try:
        return get_notifier().send(notification)
    except Exception:  # a broken channel must not fail the customer's request
        logger.exception("owner alert failed")
        return False


def _who(p: Proposal) -> str:
    return f"{p.client.name}({p.client.code})"


def _first_view(p: Proposal, r: ProposalRevision, ip: str) -> Notification:
    return Notification(
        title=f"{_who(p)}가 v{r.number}을 처음 열었습니다",
        text=p.title,
        fields=(Field("문서번호", r.doc_number, True), Field("IP", ip or "-", True)),
    )


def alert_pdf_downloaded(p: Proposal, r: ProposalRevision) -> bool:
    return alert(
        Notification(
            title=f"{_who(p)}가 v{r.number} PDF를 내려받았습니다",
            text=p.title,
            fields=(Field("문서번호", r.doc_number, True),),
        )
    )


def alert_blocked(p: Proposal, ip: str) -> bool:
    return alert(
        Notification(
            title=f"{_who(p)}의 제안서 코드 입력이 차단되었습니다",
            text=f"{p.title} — 잘못된 코드를 여러 번 입력했습니다.",
            fields=(Field("IP", ip or "-", True),),
        )
    )


# --- reading (admin, #24 MCP) ---


@dataclass(frozen=True)
class EventOut:
    at: datetime
    kind: str
    kind_label: str
    revision: int | None
    doc_number: str | None
    tab_id: str
    ip: str
    user_agent: str


def list_events(slug: str, limit: int = 200) -> list[EventOut]:
    """A proposal's events in time order (oldest first), capped at the latest `limit`."""
    p = Proposal.objects.filter(slug=slug).first()
    if p is None:
        raise NotFound("제안서를 찾을 수 없습니다")
    rows = (
        ProposalEvent.objects.filter(proposal=p)
        .select_related("revision")
        .order_by("-created_at", "-id")[:limit]
    )
    return [
        EventOut(
            at=e.created_at,
            kind=e.kind,
            kind_label=e.get_kind_display(),
            revision=e.revision.number if e.revision else None,
            doc_number=e.revision.doc_number if e.revision else None,
            tab_id=e.tab_id,
            ip=e.ip,
            user_agent=e.user_agent,
        )
        for e in reversed(list(rows))
    ]

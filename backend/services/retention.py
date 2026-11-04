"""Personal data the privacy policy (/privacy, issue 201) promises to drop after a year.

- Inquiries: the whole row, a year after it came in (`Inquiry.created_at`).
- Proposal views: the IP address and User-Agent of each `ProposalEvent`, a year after the event.
  The event itself stays, so the proposal's history still says when it was opened.

`prune()` does both now; `prune_if_due()` does it at most once a day across every process (the
compose `worker` loop calls it, see `manage.py pdf_worker`). `manage.py prune_personal_data` runs
it by hand. Change the periods here and the policy text in services/legal.py together.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from content.models import Inquiry, ProposalEvent

INQUIRY_KEEP = timedelta(days=365)
PROPOSAL_VIEW_LOG_KEEP = timedelta(days=365)

# One run a day: the first process to add this key (django_cache, shared) does the work.
DUE_KEY = "retention:pruned-today"
DUE_EVERY = timedelta(days=1)


@dataclass(frozen=True)
class Pruned:
    inquiries: int  # rows deleted
    proposal_events: int  # rows whose IP and User-Agent were blanked


def prune(now: datetime | None = None) -> Pruned:
    now = now or timezone.now()
    inquiries, _ = Inquiry.objects.filter(created_at__lt=now - INQUIRY_KEEP).delete()
    events = (
        ProposalEvent.objects.filter(created_at__lt=now - PROPOSAL_VIEW_LOG_KEEP)
        .filter(~Q(ip="") | ~Q(user_agent=""))
        .update(ip="", user_agent="")
    )
    return Pruned(inquiries=inquiries, proposal_events=events)


def prune_if_due(now: datetime | None = None) -> Pruned | None:
    """`prune()` unless some process already did in the last day; None when skipped."""
    if not cache.add(DUE_KEY, True, timeout=int(DUE_EVERY.total_seconds())):
        return None
    try:
        return prune(now)
    except Exception:
        cache.delete(DUE_KEY)  # let the next check retry instead of waiting a day
        raise

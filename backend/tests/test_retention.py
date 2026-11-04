"""The privacy policy's retention (issue 201): inquiries and proposal-view IP/UA go after a year,
once a day from the worker loop, or now from `manage.py prune_personal_data`."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone

from content.models import Inquiry, Proposal, ProposalEvent
from services import retention
from tests.test_proposals import make_draft

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def cache_table(db: None) -> None:
    call_command("createcachetable", verbosity=0)
    cache.clear()


def inquiry(name: str, age: timedelta) -> Inquiry:
    row = Inquiry.objects.create(name=name, contact="a@example.com", message="안녕하세요")
    Inquiry.objects.filter(pk=row.pk).update(created_at=timezone.now() - age)
    return row


def event(proposal: Proposal, age: timedelta) -> ProposalEvent:
    return ProposalEvent.objects.create(
        proposal=proposal,
        kind="tab",
        tab_id="main",
        ip="203.0.113.7",
        user_agent="Mozilla/5.0 Test",
        created_at=timezone.now() - age,
    )


def test_inquiries_older_than_a_year_are_deleted_and_newer_ones_stay() -> None:
    inquiry("old", timedelta(days=366))
    inquiry("recent", timedelta(days=364))

    pruned = retention.prune()

    assert pruned.inquiries == 1
    assert list(Inquiry.objects.values_list("name", flat=True)) == ["recent"]


def test_proposal_events_older_than_a_year_lose_ip_and_user_agent_but_stay() -> None:
    proposal = Proposal.objects.get(slug=make_draft().slug)
    old = event(proposal, timedelta(days=366))
    recent = event(proposal, timedelta(days=10))

    assert retention.prune().proposal_events == 1
    assert retention.prune().proposal_events == 0  # already blank: nothing to do again

    old.refresh_from_db()
    recent.refresh_from_db()
    assert (old.ip, old.user_agent, old.kind) == ("", "", "tab")
    assert (recent.ip, recent.user_agent) == ("203.0.113.7", "Mozilla/5.0 Test")


def test_the_daily_run_happens_once_a_day_across_processes() -> None:
    inquiry("old", timedelta(days=400))

    assert retention.prune_if_due() == retention.Pruned(inquiries=1, proposal_events=0)
    inquiry("old again", timedelta(days=400))
    assert retention.prune_if_due() is None  # another process (or this one) already ran today
    assert Inquiry.objects.count() == 1

    cache.delete(retention.DUE_KEY)  # a day later
    assert retention.prune_if_due() is not None
    assert Inquiry.objects.count() == 0


def test_a_failed_run_does_not_wait_a_day_to_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(now: object = None) -> retention.Pruned:
        raise RuntimeError("db down")

    monkeypatch.setattr(retention, "prune", boom)
    with pytest.raises(RuntimeError):
        retention.prune_if_due()
    assert cache.get(retention.DUE_KEY) is None


def test_the_worker_loop_prunes_and_the_command_prunes_now() -> None:
    from core.management.commands import pdf_worker

    inquiry("old", timedelta(days=400))
    pdf_worker.prune_if_due()
    assert Inquiry.objects.count() == 0

    inquiry("old", timedelta(days=400))
    out = StringIO()
    call_command("prune_personal_data", stdout=out)
    assert Inquiry.objects.count() == 0
    assert "문의 1건 삭제" in out.getvalue()

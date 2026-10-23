"""What the move to MySQL (#63) must keep from Postgres, checked against the real database:
case-sensitive keys (the `utf8mb4_0900_as_cs` collation), one first view per revision under
concurrent first views, and two PDF workers that do not starve each other."""

import threading
from collections.abc import Callable, Iterator
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from adapters.fake_notify import FakeNotifier
from content.models import Client, PdfJob, PortfolioItem, Proposal, ProposalEvent
from services import pdf, publishing
from services import proposal_events as events
from services import proposals as svc
from tests.test_proposals import make_draft
from tests.test_publishing import published

THREADS = 8


def run_together(target: Callable[[int], object], n: int = THREADS) -> None:
    """Run `target(i)` in n threads released at once, each on its own DB connection."""
    barrier = threading.Barrier(n)
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            barrier.wait(timeout=10)
            target(i)
        except BaseException as exc:  # reported in the main thread
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors, errors


@pytest.mark.django_db
def test_slugs_codes_and_usernames_are_case_sensitive() -> None:
    PortfolioItem.objects.create(slug="svc", title="소문자")
    PortfolioItem.objects.create(slug="Svc", title="대문자")  # no unique clash
    assert PortfolioItem.objects.get(slug="svc").title == "소문자"
    assert not PortfolioItem.objects.filter(slug="SVC").exists()

    slug, _ = published()
    assert Proposal.objects.filter(slug=slug).exists()
    assert not Proposal.objects.filter(slug=slug.swapcase()).exists()

    assert Client.objects.filter(code="NEXT").exists()
    assert not Client.objects.filter(code="next").exists()

    get_user_model().objects.create(username="owner")
    assert not get_user_model().objects.filter(username="OWNER").exists()


@pytest.mark.django_db
def test_only_one_first_view_row_per_revision() -> None:
    slug, _ = published()
    p = Proposal.objects.get(slug=slug)
    revision = p.revisions.get()
    kind = ProposalEvent.Kind.VIEWED
    ProposalEvent.objects.create(proposal=p, revision=revision, kind=kind, first=True)
    ProposalEvent.objects.create(proposal=p, revision=revision, kind=kind)
    ProposalEvent.objects.create(proposal=p, revision=revision, kind=kind)
    ProposalEvent.objects.create(proposal=p, revision=None, kind=kind, first=True)
    ProposalEvent.objects.create(proposal=p, revision=None, kind=kind, first=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        ProposalEvent.objects.create(proposal=p, revision=revision, kind=kind, first=True)


@pytest.mark.django_db(transaction=True)
def test_simultaneous_first_views_alert_once(notifier: FakeNotifier) -> None:
    slug, _ = published()
    p = Proposal.objects.get(slug=slug)
    revision = p.revisions.get()

    run_together(lambda i: events.record_view(p, revision, ip=f"203.0.113.{i}", user_agent="probe"))

    views = ProposalEvent.objects.filter(revision=revision, kind=ProposalEvent.Kind.VIEWED)
    assert views.count() == THREADS
    assert views.filter(first=True).count() == 1
    assert len(notifier.sent) == 1


@pytest.fixture
def two_due_jobs(transactional_db: None) -> Iterator[list[int]]:
    publishing.publish(make_draft().slug)
    publishing.publish(svc.create_proposal(svc.NewProposal(client_code="NEXT", title="둘째")).slug)
    PdfJob.objects.update(run_after=timezone.now() - timedelta(minutes=1))
    yield list(PdfJob.objects.order_by("id").values_list("id", flat=True))


def test_a_second_worker_takes_the_next_job_while_the_first_holds_its_own(
    two_due_jobs: list[int],
) -> None:
    held = threading.Event()
    release = threading.Event()
    first: list[int] = []

    def first_worker() -> None:
        try:
            with transaction.atomic():  # keeps the row lock until released
                job = pdf.claim_next()
                first.append(job.pk if job else 0)
                held.set()
                release.wait(timeout=10)
        finally:
            held.set()
            connection.close()

    t = threading.Thread(target=first_worker)
    t.start()
    try:
        assert held.wait(timeout=10)
        second = pdf.claim_next()
    finally:
        release.set()
        t.join(timeout=10)
    assert first == [two_due_jobs[0]]
    assert second is not None and second.pk == two_due_jobs[1]

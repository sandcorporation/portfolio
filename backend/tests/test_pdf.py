"""Revision PDFs (#40): publishing queues a job, the worker renders and stores it, failures are
retried, and the customer downloads it through their session."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client as HttpClient
from django.urls import reverse
from django.utils import timezone

from adapters.fake_renderer import FAKE_PDF, FakeRenderer
from adapters.fake_storage import FakeObjectStorage
from adapters.storage import Bucket
from content.models import PdfJob, ProposalRevision
from services import pdf, publishing
from services.errors import Conflict
from tests.test_publishing import published, screen, unlock

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def cache_table(db: None) -> Iterator[None]:
    call_command("createcachetable", verbosity=0)
    cache.clear()
    yield
    cache.clear()


def work() -> None:
    call_command("pdf_worker", "--once")


def job_of(slug: str) -> PdfJob:
    return PdfJob.objects.get(revision__proposal__slug=slug)


def make_due(slug: str) -> None:
    """Skip the wait before the next automatic attempt."""
    PdfJob.objects.filter(revision__proposal__slug=slug).update(
        run_after=timezone.now() - timedelta(seconds=1)
    )


# --- queue and worker ---


def test_publishing_queues_a_pdf_job_for_the_new_revision() -> None:
    slug, _ = published()
    assert pdf.pdf_status(slug).status == PdfJob.Status.PENDING
    publishing.publish(slug)
    assert [j.revision.number for j in PdfJob.objects.order_by("id")] == [1, 2]


def test_the_worker_renders_the_print_page_and_stores_the_pdf_privately(
    fake_storage: FakeObjectStorage, renderer: FakeRenderer
) -> None:
    slug, _ = published()
    work()

    revision = ProposalRevision.objects.get(proposal__slug=slug)
    [url] = renderer.urls
    assert url.startswith("http://web:8000/print/")
    status = pdf.pdf_status(slug)
    assert status.status == PdfJob.Status.DONE
    assert status.doc_number == revision.doc_number
    assert status.finished_at is not None
    key = f"pdf/{revision.doc_number}.pdf"
    assert fake_storage.objects[(Bucket.PRIVATE, key)] == (FAKE_PDF, "application/pdf")


def test_the_print_link_the_renderer_gets_opens_the_revision(
    fake_storage: FakeObjectStorage, renderer: FakeRenderer
) -> None:
    published()
    work()
    path = renderer.urls[0].removeprefix("http://web:8000")
    assert HttpClient().get(path).status_code == 200


def test_with_nothing_due_the_worker_does_nothing(renderer: FakeRenderer) -> None:
    work()
    assert renderer.urls == []


def test_a_renderer_failure_is_retried_then_the_job_fails_until_retried(
    fake_storage: FakeObjectStorage, renderer: FakeRenderer
) -> None:
    slug, _ = published()
    renderer.failing = True

    work()
    status = pdf.pdf_status(slug)
    assert (status.status, status.attempts) == (PdfJob.Status.PENDING, 1)
    assert "가짜 렌더러 장애" in status.error
    work()  # not due yet: the next attempt waits a minute
    assert len(renderer.urls) == 1

    for _ in range(2):
        make_due(slug)
        work()
    status = pdf.pdf_status(slug)
    assert (status.status, status.attempts) == (PdfJob.Status.FAILED, 3)
    make_due(slug)
    work()
    assert len(renderer.urls) == 3  # failed jobs wait for a person

    renderer.failing = False
    pdf.retry(ProposalRevision.objects.get(proposal__slug=slug))
    assert pdf.pdf_status(slug).status == PdfJob.Status.PENDING
    work()
    status = pdf.pdf_status(slug)
    assert (status.status, status.attempts, status.error) == (PdfJob.Status.DONE, 1, "")


def test_a_storage_failure_fails_the_attempt_too(renderer: FakeRenderer) -> None:
    slug, _ = published()
    work()  # no fake_storage: STORAGE_* are empty, so storing raises StorageNotConfigured
    status = pdf.pdf_status(slug)
    assert status.status == PdfJob.Status.PENDING
    assert "StorageNotConfigured" in status.error


def test_without_a_renderer_token_pdfs_fail_and_publishing_still_works(
    fake_storage: FakeObjectStorage,
) -> None:
    slug, _ = published()
    work()
    status = pdf.pdf_status(slug)
    assert "PDF_RENDERER_TOKEN" in status.error


def test_a_job_left_running_by_a_dead_worker_is_taken_back(
    fake_storage: FakeObjectStorage, renderer: FakeRenderer
) -> None:
    slug, _ = published()
    job = pdf.claim_next()  # a worker claims it and dies
    assert job is not None
    work()
    assert renderer.urls == []  # still within the stale limit: left alone

    PdfJob.objects.filter(pk=job.pk).update(locked_at=timezone.now() - timedelta(minutes=6))
    work()
    status = pdf.pdf_status(slug)
    assert (status.status, status.attempts) == (PdfJob.Status.DONE, 2)


def test_a_dead_worker_on_the_last_attempt_fails_the_job(renderer: FakeRenderer) -> None:
    slug, _ = published()
    PdfJob.objects.update(
        status=PdfJob.Status.RUNNING,
        attempts=3,
        locked_at=timezone.now() - timedelta(minutes=6),
    )
    work()
    status = pdf.pdf_status(slug)
    assert status.status == PdfJob.Status.FAILED
    assert "워커가 멈춤" in status.error
    assert renderer.urls == []


def test_a_result_is_dropped_when_the_job_was_taken_back_meanwhile(
    fake_storage: FakeObjectStorage, renderer: FakeRenderer
) -> None:
    slug, _ = published()
    slow = pdf.claim_next()
    assert slow is not None
    PdfJob.objects.filter(pk=slow.pk).update(locked_at=timezone.now() - timedelta(minutes=6))
    again = pdf.claim_next()
    assert again is not None
    pdf.run(slow)  # the slow worker finishes late: its write must not count
    assert job_of(slug).status == PdfJob.Status.RUNNING
    pdf.run(again)
    assert job_of(slug).status == PdfJob.Status.DONE


def test_a_running_job_cannot_be_retried() -> None:
    slug, _ = published()
    pdf.claim_next()
    with pytest.raises(Conflict):
        pdf.retry(ProposalRevision.objects.get(proposal__slug=slug))


def test_retry_makes_a_job_for_a_revision_published_before_pdfs(renderer: FakeRenderer) -> None:
    slug, _ = published()
    PdfJob.objects.all().delete()
    assert pdf.pdf_status(slug).status == PdfJob.Status.FAILED
    pdf.retry(ProposalRevision.objects.get(proposal__slug=slug))
    assert pdf.pdf_status(slug).status == PdfJob.Status.PENDING


# --- the customer's download ---


def pdf_path(slug: str) -> str:
    return f"/p/{slug}/pdf"


def test_without_a_session_the_pdf_is_refused(
    fake_storage: FakeObjectStorage, renderer: FakeRenderer
) -> None:
    slug, _ = published()
    work()
    response = HttpClient().get(pdf_path(slug))
    assert response.status_code == 403
    assert response["Cache-Control"] == "no-store"
    assert ("presign_get", Bucket.PRIVATE, f"pdf/{job_of(slug).revision.doc_number}.pdf") not in (
        fake_storage.calls
    )


def test_with_a_session_the_pdf_redirects_to_a_presigned_url_named_after_the_document(
    fake_storage: FakeObjectStorage, renderer: FakeRenderer, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloads: list[str] = []
    monkeypatch.setattr(
        "services.proposal_access.on_pdf_downloaded", lambda p, r: downloads.append(r.doc_number)
    )
    slug, code = published()
    client = HttpClient()
    unlock(client, slug, code)
    assert screen(client, slug).get("pdf_url") is None  # not made yet: no button
    assert client.get(pdf_path(slug)).status_code == 404

    work()
    assert screen(client, slug)["pdf_url"] == pdf_path(slug)
    response = client.get(pdf_path(slug))
    doc_number = job_of(slug).revision.doc_number
    assert response.status_code == 302
    assert response["Location"] == (
        f"https://download.test/private/pdf/{doc_number}.pdf?expires=600&download={doc_number}.pdf"
    )
    assert response["Cache-Control"] == "no-store"
    assert downloads == [doc_number]


def test_the_pdf_of_a_new_revision_replaces_the_old_one_only_when_done(
    fake_storage: FakeObjectStorage, renderer: FakeRenderer
) -> None:
    slug, code = published()
    work()
    publishing.publish(slug)
    client = HttpClient()
    unlock(client, slug, code)
    assert screen(client, slug).get("pdf_url") is None  # v2 is still pending
    work()
    assert screen(client, slug)["pdf_url"] == pdf_path(slug)
    assert "-002" in client.get(pdf_path(slug))["Location"]


def test_a_revoked_proposal_has_no_pdf(
    fake_storage: FakeObjectStorage, renderer: FakeRenderer
) -> None:
    slug, code = published()
    work()
    client = HttpClient()
    unlock(client, slug, code)
    publishing.revoke(slug)
    assert client.get(pdf_path(slug)).status_code == 404


# --- the owner ---


def test_pdf_status_reports_the_requested_revision(
    fake_storage: FakeObjectStorage, renderer: FakeRenderer
) -> None:
    slug, _ = published()
    work()
    publishing.publish(slug)
    assert pdf.pdf_status(slug).status == PdfJob.Status.PENDING
    assert pdf.pdf_status(slug, 1).status == PdfJob.Status.DONE
    assert pdf.pdf_status(slug, 2).revision == 2


def test_admin_shows_the_pdf_state_and_retries_it(
    admin_client: HttpClient, fake_storage: FakeObjectStorage, renderer: FakeRenderer
) -> None:
    slug, _ = published()
    renderer.failing = True
    PdfJob.objects.update(attempts=2)
    work()
    revision = ProposalRevision.objects.get(proposal__slug=slug)
    changelist = reverse("admin:content_proposalrevision_changelist")
    assert "실패" in admin_client.get(changelist).content.decode()
    page = admin_client.get(reverse("admin:content_proposalrevision_change", args=[revision.pk]))
    assert "가짜 렌더러 장애" in page.content.decode()

    response = admin_client.post(
        changelist, {"action": "retry_pdf", "_selected_action": [revision.pk]}, follow=True
    )
    assert "다시 만들도록" in response.content.decode()
    renderer.failing = False
    work()
    page = admin_client.get(reverse("admin:content_proposalrevision_change", args=[revision.pk]))
    assert f"{revision.doc_number}.pdf" in page.content.decode()

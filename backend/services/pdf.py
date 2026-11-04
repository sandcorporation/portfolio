"""Revision PDFs: the job queue, the worker's step, the customer's download and the status.

Publishing makes a `PdfJob` for the new revision in the same transaction (`publishing.publish`),
so the worker sees it only once the publication has committed and never sees a rolled-back one.

The worker (`manage.py pdf_worker`, one compose service, one job at a time) calls `work_once`:
`claim_next` locks the oldest due job with `SKIP LOCKED` and marks it running with `locked_at`;
the renderer prints the revision's `/print/<token>` page (#16) to PDF; the PDF goes to the private
bucket and the job becomes done. A failure puts the job back with a growing delay until
`PDF_JOB_MAX_ATTEMPTS`, then it stays failed until someone presses retry (`retry`, admin action).

A worker that dies mid-job leaves it running. One render is bounded by the renderer timeout, so a
job running for longer than `PDF_JOB_STALE_SECONDS` is taken back by the next claim (that attempt
counts). Finishing only writes when the job is still the one this worker claimed (`locked_at`).
"""

import hashlib
import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from pydantic import BaseModel

from adapters.renderer import PdfRenderer, RenderFailed, get_renderer
from adapters.storage import Bucket, ObjectStorage, get_storage
from content.models import PdfJob, Proposal, ProposalRevision
from services import proposals
from services.errors import Conflict, NotFound

logger = logging.getLogger(__name__)

DOWNLOAD_URL_TTL = timedelta(minutes=10)
Status = PdfJob.Status


class PdfStatus(BaseModel):
    doc_number: str
    revision: int
    status: Status
    attempts: int
    error: str
    finished_at: datetime | None


def object_key(revision: ProposalRevision) -> str:
    return f"pdf/{revision.doc_number}.pdf"


def download_name(revision: ProposalRevision) -> str:
    return f"{revision.doc_number}.pdf"


def enqueue(revision: ProposalRevision) -> PdfJob:
    """The job for a new revision. Call inside the transaction that creates the revision."""
    return PdfJob.objects.create(revision=revision)


# --- the worker ---


def _give_up_or_wait(job: PdfJob, now: datetime, error: str) -> None:
    job.error = error[:2000]
    job.locked_at = None
    if job.attempts >= settings.PDF_JOB_MAX_ATTEMPTS:
        job.status = Status.FAILED
    else:
        job.status = Status.PENDING
        job.run_after = now + timedelta(minutes=job.attempts)


def _lock_first(due: Q) -> PdfJob | None:
    return (
        PdfJob.objects.select_for_update(skip_locked=True)
        .select_related("revision")
        .filter(due)
        .order_by("run_after", "id")
        .first()
    )


def claim_next(now: datetime | None = None) -> PdfJob | None:
    """Lock the next due job and mark it running, or None. Takes back jobs of a dead worker.

    Two queries, each on one status, so InnoDB walks the `pdfjob_due` index and locks only the
    row it returns; with an OR it sorted every due row and locked them all, leaving nothing for
    a second worker.
    """
    now = now or timezone.now()
    stale = now - timedelta(seconds=settings.PDF_JOB_STALE_SECONDS)
    while True:
        with transaction.atomic():
            job = _lock_first(Q(status=Status.PENDING, run_after__lte=now)) or _lock_first(
                Q(status=Status.RUNNING, locked_at__lt=stale)
            )
            if job is None:
                return None
            if job.status == Status.RUNNING:
                logger.warning("PDF job %s: taking back from a stopped worker", job.pk)
                _give_up_or_wait(job, now, "처리 중에 워커가 멈춤")
                if job.status == Status.FAILED:
                    job.save()
                    continue
            job.status = Status.RUNNING
            job.attempts += 1
            job.locked_at = now
            job.save()
            return job


def _finish(job: PdfJob, claimed_at: datetime | None) -> None:
    """Write the outcome unless another worker has taken the job back meanwhile."""
    fields = (
        "status",
        "attempts",
        "run_after",
        "locked_at",
        "finished_at",
        "error",
        "object_key",
        "size",
    )
    updated = PdfJob.objects.filter(pk=job.pk, status=Status.RUNNING, locked_at=claimed_at).update(
        **{f: getattr(job, f) for f in fields}
    )
    if not updated:
        logger.warning("PDF job %s was taken back while running; result dropped", job.pk)


def run(
    job: PdfJob,
    *,
    renderer: PdfRenderer | None = None,
    storage: ObjectStorage | None = None,
) -> None:
    """Render and store one claimed job, then mark it done, waiting again, or failed."""
    claimed_at = job.locked_at
    url = settings.PDF_PRINT_BASE_URL.rstrip("/") + proposals.issue_print_url(job.revision)
    try:
        data = (renderer or get_renderer()).render(url)
        key = object_key(job.revision)
        (storage or get_storage()).put(Bucket.PRIVATE, key, data, "application/pdf")
    except Exception as e:  # noqa: BLE001 — any failure (renderer, storage, config) fails the job
        logger.warning("PDF job %s failed (attempt %s): %s", job.pk, job.attempts, e)
        _give_up_or_wait(job, timezone.now(), f"{type(e).__name__}: {e}")
    else:
        job.status = Status.DONE
        job.object_key = key
        job.size = len(data)
        job.error = ""
        job.finished_at = timezone.now()
        job.locked_at = None
    _finish(job, claimed_at)


def work_once(*, renderer: PdfRenderer | None = None, storage: ObjectStorage | None = None) -> bool:
    """Process the next due job; False when there was none."""
    job = claim_next()
    if job is None:
        return False
    run(job, renderer=renderer, storage=storage)
    return True


def retry(revision: ProposalRevision) -> None:
    """Make the revision's PDF again from scratch (attempts reset): a failed or finished job, or
    a revision published before PDFs existed. A running job is left alone."""
    with transaction.atomic():
        job = PdfJob.objects.select_for_update().filter(revision=revision).first()
        if job is None:
            enqueue(revision)
            return
        if job.status == Status.RUNNING:
            raise Conflict("처리 중인 PDF는 다시 시도할 수 없습니다")
        job.status = Status.PENDING
        job.attempts = 0
        job.error = ""
        job.run_after = timezone.now()
        job.locked_at = None
        job.save()


def retry_revision(slug: str, number: int | None = None) -> PdfStatus:
    """`retry` by proposal slug and revision number (latest by default); returns the new status."""
    revisions = ProposalRevision.objects.filter(proposal__slug=slug)
    revision = revisions.filter(number=number).first() if number is not None else revisions.first()
    if revision is None:
        raise NotFound(f"제안서 {slug!r}의 리비전이 없습니다")
    retry(revision)
    return pdf_status(slug, revision.number)


# --- reading ---


def _job_of(revision: ProposalRevision) -> PdfJob | None:
    return PdfJob.objects.filter(revision=revision).first()


def pdf_status(slug: str, number: int | None = None) -> PdfStatus:
    """The PDF state of a revision (the latest one by default). For the owner's tools (#24)."""
    revisions = ProposalRevision.objects.filter(proposal__slug=slug)
    revision = revisions.filter(number=number).first() if number is not None else revisions.first()
    if revision is None:
        raise NotFound(f"제안서 {slug!r}의 리비전이 없습니다")
    job = _job_of(revision)
    if job is None:  # revisions published before #40
        return PdfStatus(
            doc_number=revision.doc_number,
            revision=revision.number,
            status=Status.FAILED,
            attempts=0,
            error="PDF 작업이 없습니다(이전 발행). 다시 발행하면 만들어집니다",
            finished_at=None,
        )
    return PdfStatus(
        doc_number=revision.doc_number,
        revision=revision.number,
        status=Status(job.status),
        attempts=job.attempts,
        error=job.error,
        finished_at=job.finished_at,
    )


def ready_job(p: Proposal) -> PdfJob | None:
    """The finished PDF job of the proposal's latest revision, if there is one."""
    revision = p.revisions.first()
    if revision is None:
        return None
    return PdfJob.objects.filter(revision=revision, status=Status.DONE).first()


def download_url(job: PdfJob, *, storage: ObjectStorage | None = None) -> str:
    """A short-lived presigned GET that saves the file as `<document number>.pdf`."""
    return (storage or get_storage()).presign_get(
        Bucket.PRIVATE,
        job.object_key,
        DOWNLOAD_URL_TTL,
        download_name=download_name(job.revision),
    )


# --- on-the-spot PDF of the draft (#225): admin action, MCP export_proposal_pdf ---


class PdfExport(BaseModel):
    url: str
    expires_at: datetime
    platform_mode: bool
    # Text left in the document that still names us or carries an email / a phone number
    # (services/platform_mode.py::leaks). Empty is what a platform submission needs.
    leaks: list[str]


def render_draft(
    slug: str, platform: bool | None = None, *, renderer: PdfRenderer | None = None
) -> tuple[Proposal, bool, bytes]:
    """The PDF of the proposal's current draft document (a published one too), through the draft
    print link. `platform` overrides the proposal's `platform_mode` for this PDF only (None = the
    proposal's own). Writes nothing (`manage.py proposal_pdf` relies on that)."""
    p = proposals.get_proposal_row(slug)
    mode = p.platform_mode if platform is None else platform
    url = settings.PDF_PRINT_BASE_URL.rstrip("/") + proposals.issue_draft_print_url(
        p, platform=mode
    )
    try:
        data = (renderer or get_renderer()).render(url)
    except RenderFailed as e:
        raise Conflict(f"PDF를 만들지 못했습니다: {e}") from None
    return p, mode, data


def export_draft(
    slug: str,
    platform: bool | None = None,
    *,
    renderer: PdfRenderer | None = None,
    storage: ObjectStorage | None = None,
) -> PdfExport:
    """`render_draft`, stored in the private bucket under `pdf/drafts/`, with a 10-minute link."""
    p, mode, data = render_draft(slug, platform, renderer=renderer)
    key = f"pdf/drafts/{p.slug}-{hashlib.sha256(data).hexdigest()[:10]}.pdf"
    store = storage or get_storage()
    store.put(Bucket.PRIVATE, key, data, "application/pdf")
    expires_at = timezone.now() + DOWNLOAD_URL_TTL
    url = store.presign_get(
        Bucket.PRIVATE, key, DOWNLOAD_URL_TTL, download_name=f"proposal-{p.slug}.pdf"
    )
    return PdfExport(
        url=url, expires_at=expires_at, platform_mode=mode, leaks=proposals.leaks_of(p, mode)
    )

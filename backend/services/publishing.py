"""Publishing a proposal to its customer: revisions, document numbers and the access code.

A proposal keeps one editable draft (`Proposal.document` and its metadata). Publishing freezes a
copy of it as the next `ProposalRevision` (v1, v2, ...) with a new document number; the customer
page always shows the latest revision, and older ones stay as they were.

The first publication issues the access code (8 characters, no look-alikes), and so does a
reissue, which also invalidates every customer session. The plain code exists only in the return
value of those two functions; the database keeps a Django password hash.
"""

import copy
import secrets
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from pydantic import BaseModel, Field

from content.models import Client, Proposal, ProposalRevision
from documents.validation import JSON
from services.errors import Conflict, NotFound
from services.proposals import ProposalSummary, proposal_summary

# No 0/O, 1/I/L: a code is read off a message and typed on a phone.
ACCESS_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
ACCESS_CODE_LENGTH = 8
SEOUL = ZoneInfo("Asia/Seoul")


class RevisionSummary(BaseModel):
    number: int
    doc_number: str
    published_at: datetime
    valid_until: date | None


class RevisionOut(RevisionSummary):
    recipient: str
    title: str
    subtitle: str
    quote_date: date
    document: dict[str, JSON]


class Published(BaseModel):
    slug: str
    revision: RevisionOut
    access_code: str | None = Field(
        description="Only on the first publication; later ones keep the code the customer has."
    )


class IssuedCode(BaseModel):
    slug: str
    access_code: str
    issued_at: datetime


def new_access_code() -> str:
    return "".join(secrets.choice(ACCESS_CODE_ALPHABET) for _ in range(ACCESS_CODE_LENGTH))


def normalize_code(raw: str) -> str:
    """What the customer typed, as it was issued: upper case, without spaces or hyphens."""
    return "".join(raw.split()).replace("-", "").upper()


def code_matches(p: Proposal, raw: str) -> bool:
    code = normalize_code(raw)
    if not p.access_code_hash or len(code) != ACCESS_CODE_LENGTH:
        return False
    return check_password(code, p.access_code_hash)


def document_number(day: date, client_code: str, serial: int) -> str:
    return f"SC-{day:%Y%m%d}-{client_code}-{serial:03d}"


def snapshot_document(document: dict[str, JSON]) -> dict[str, JSON]:
    """The document as frozen into a revision.

    #13: expand `case-ref` blocks here into the referenced case as it reads at publish time, so a
    later edit of the case does not change what the customer was sent.
    """
    return copy.deepcopy(document)


def _revision_summary(r: ProposalRevision) -> RevisionSummary:
    return RevisionSummary(
        number=r.number,
        doc_number=r.doc_number,
        published_at=r.published_at,
        valid_until=r.valid_until,
    )


def revision_out(r: ProposalRevision) -> RevisionOut:
    return RevisionOut(
        **_revision_summary(r).model_dump(),
        recipient=r.recipient,
        title=r.title,
        subtitle=r.subtitle,
        quote_date=r.quote_date,
        document=r.document,
    )


def _issue_code(p: Proposal) -> str:
    code = new_access_code()
    p.access_code_hash = make_password(code)
    p.access_code_issued_at = timezone.now()
    return code


def _locked_proposal(slug: str) -> Proposal:
    p = Proposal.objects.select_for_update().filter(slug=slug).first()
    if p is None:
        raise NotFound(f"제안서 {slug!r}이(가) 없습니다")
    return p


def publish(slug: str) -> Published:
    """Freeze the draft as the next revision and show it to the customer.

    Locks the proposal, then its client (always in that order), so two publications of one
    proposal get consecutive revision numbers and two of one client consecutive serials.
    """
    with transaction.atomic():
        p = _locked_proposal(slug)
        if p.status == Proposal.Status.REVOKED:
            raise Conflict("회수된 제안서는 다시 발행할 수 없습니다. 복제해서 새 주소로 발행합니다")
        client = Client.objects.select_for_update().get(pk=p.client_id)
        now = timezone.now()
        last = p.revisions.aggregate(n=Max("number"))["n"] or 0
        serial = (client.revisions.aggregate(n=Max("serial"))["n"] or 0) + 1
        revision = ProposalRevision.objects.create(
            proposal=p,
            number=last + 1,
            client=client,
            serial=serial,
            doc_number=document_number(timezone.localdate(now, SEOUL), client.code, serial),
            published_at=now,
            recipient=f"{client.contact_title}께" if client.contact_title else client.name,
            title=p.title,
            subtitle=p.subtitle,
            quote_date=p.quote_date,
            valid_until=p.valid_until,
            document=snapshot_document(p.document),
        )
        code = None if p.access_code_hash else _issue_code(p)
        p.status = Proposal.Status.PUBLISHED
        p.save()
    return Published(slug=p.slug, revision=revision_out(revision), access_code=code)


def reissue_access_code(slug: str) -> IssuedCode:
    """A new code for a published proposal; every customer session made with the old one ends."""
    with transaction.atomic():
        p = _locked_proposal(slug)
        if p.status != Proposal.Status.PUBLISHED:
            raise Conflict("발행된 제안서만 접근 코드를 다시 만들 수 있습니다")
        code = _issue_code(p)
        p.save(update_fields=["access_code_hash", "access_code_issued_at", "updated_at"])
    assert p.access_code_issued_at is not None
    return IssuedCode(slug=p.slug, access_code=code, issued_at=p.access_code_issued_at)


def revoke(slug: str) -> ProposalSummary:
    """Take a published proposal back. Its page answers as if it never existed, for good."""
    with transaction.atomic():
        p = _locked_proposal(slug)
        if p.status != Proposal.Status.PUBLISHED:
            raise Conflict("발행된 제안서만 회수할 수 있습니다")
        p.status = Proposal.Status.REVOKED
        p.save(update_fields=["status", "updated_at"])
    return proposal_summary(Proposal.objects.select_related("client").get(pk=p.pk))


def latest_revision(p: Proposal) -> ProposalRevision | None:
    return p.revisions.order_by("-number").first()


def list_revisions(slug: str) -> list[RevisionSummary]:
    """Newest first."""
    p = Proposal.objects.filter(slug=slug).first()
    if p is None:
        raise NotFound(f"제안서 {slug!r}이(가) 없습니다")
    return [_revision_summary(r) for r in p.revisions.order_by("-number")]


def get_revision(slug: str, number: int) -> RevisionOut:
    r = ProposalRevision.objects.filter(proposal__slug=slug, number=number).first()
    if r is None:
        raise NotFound(f"제안서 {slug!r}의 리비전 v{number}이(가) 없습니다")
    return revision_out(r)


def is_expired(r: ProposalRevision, today: date | None = None) -> bool:
    """Valid through `valid_until` (inclusive), by the date in Seoul."""
    today = today or timezone.localdate(timezone.now(), SEOUL)
    return r.valid_until is not None and today > r.valid_until

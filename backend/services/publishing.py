"""Publishing a proposal to its customer: revisions, document numbers and the access code.

A proposal keeps one editable draft (`Proposal.document` and its metadata). Publishing freezes a
copy of it as the next `ProposalRevision` (v1, v2, ...) with a new document number; the customer
page always shows the latest revision, and older ones stay as they were.

The first publication issues the access code, and so does a reissue, which also invalidates
every customer session. Either takes a code the owner chose (4-32 characters, see
`validate_access_code`); without one an 8-character code without look-alikes is made. The plain
code exists only in the return value of those two functions; the database keeps a Django password
hash.
"""

import secrets
import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from pydantic import BaseModel, Field

from content.models import Client, Proposal, ProposalRevision
from documents.validation import JSON
from services import case_refs, pdf
from services.errors import Conflict, NotFound, Rejected
from services.proposals import ProposalSummary, proposal_summary

# No 0/O, 1/I/L: a code is read off a message and typed on a phone.
ACCESS_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
ACCESS_CODE_LENGTH = 8  # the length of a generated code
ACCESS_CODE_MIN = 4  # what an owner may choose
ACCESS_CODE_MAX = 32
# Too easy to guess whatever else they are (compared case-insensitively).
COMMON_ACCESS_CODES = frozenset(
    {
        "0000",
        "00000000",
        "1234",
        "12345",
        "123456",
        "12345678",
        "password",
        "passw0rd",
        "admin",
        "test",
        "qwer",
        "qwerty",
        "letmein",
        "welcome",
        "비밀번호",
    }
)
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


class InvalidAccessCode(Rejected):
    """A chosen access code that breaks the rules. The message never contains the code."""

    def __init__(self, reason: str) -> None:
        super().__init__(Rejected.at("access_code", reason).errors)


def clean_code(raw: str) -> str:
    """What was typed or chosen, as it is hashed: composed Unicode (a Mac may send decomposed
    Hangul), without spaces at either end. Case and inner characters are kept."""
    return unicodedata.normalize("NFC", raw).strip()


def normalize_code(raw: str) -> str:
    """The form of the generated codes: upper case, without spaces or hyphens."""
    return "".join(raw.split()).replace("-", "").upper()


def _is_run(chars: str) -> bool:
    steps = {ord(b) - ord(a) for a, b in zip(chars, chars[1:], strict=False)}
    return steps == {1} or steps == {-1}


def validate_access_code(raw: str, *, proposal_slug: str, client_code: str) -> str:
    """The chosen code in its stored form, or `InvalidAccessCode`."""
    code = clean_code(raw)
    if not ACCESS_CODE_MIN <= len(code) <= ACCESS_CODE_MAX:
        raise InvalidAccessCode(
            f"접근 코드는 {ACCESS_CODE_MIN}~{ACCESS_CODE_MAX}자여야 합니다(앞뒤 공백 제외)"
        )
    if not all(c.isalnum() or c in "-_ " for c in code):
        raise InvalidAccessCode("접근 코드에는 글자·숫자·하이픈·밑줄·공백만 쓸 수 있습니다")
    plain = "".join(c for c in code if c.isalnum()).casefold()
    if len(set(plain)) <= 1 and plain:
        raise InvalidAccessCode("같은 문자를 반복한 코드는 너무 쉽습니다")
    if len(plain) >= ACCESS_CODE_MIN and _is_run(plain):
        raise InvalidAccessCode("연속된 숫자·글자 코드는 너무 쉽습니다")
    folded = code.casefold()
    if folded in COMMON_ACCESS_CODES or plain in COMMON_ACCESS_CODES:
        raise InvalidAccessCode("너무 흔한 코드입니다")
    if folded in {proposal_slug.casefold(), client_code.casefold()}:
        raise InvalidAccessCode("제안서 주소나 고객 코드와 같은 코드는 쓸 수 없습니다")
    return code


def code_matches(p: Proposal, raw: str) -> bool:
    """Right if it is the chosen/generated code as typed (spaces at the ends aside), or a
    generated one typed loosely (any case, with spaces or hyphens)."""
    code = clean_code(raw)
    if not p.access_code_hash or not ACCESS_CODE_MIN <= len(code) <= ACCESS_CODE_MAX:
        return False
    if check_password(code, p.access_code_hash):
        return True
    loose = normalize_code(raw)
    return (
        loose != code
        and len(loose) == ACCESS_CODE_LENGTH
        and check_password(loose, p.access_code_hash)
    )


def document_number(day: date, client_code: str, serial: int) -> str:
    return f"SC-{day:%Y%m%d}-{client_code}-{serial:03d}"


def snapshot_document(document: dict[str, JSON]) -> dict[str, JSON]:
    """The document as frozen into a revision.

    `case-ref` items are expanded into the cited case as it reads now, so a later edit or delete
    of the portfolio item does not change what the customer was sent. Other blocks are copied
    as they are. Media is frozen as its id, never a URL: presigned URLs expire, so the customer
    page issues them when serving (`media.resolve_document(private=True)`) and again on request
    (`/p/<slug>/media/<id>`). Media deleted after publishing simply has no URL any more; the
    renderers say the material is no longer available.
    """
    return case_refs.expand(document)


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


def _issue_code(p: Proposal, chosen: str | None) -> str:
    if chosen is not None and chosen.strip():
        client_code = Client.objects.values_list("code", flat=True).get(pk=p.client_id)
        code = validate_access_code(chosen, proposal_slug=p.slug, client_code=client_code)
    else:
        code = new_access_code()
    p.access_code_hash = make_password(code)
    p.access_code_issued_at = timezone.now()
    return code


def _locked_proposal(slug: str) -> Proposal:
    p = Proposal.objects.select_for_update().filter(slug=slug).first()
    if p is None:
        raise NotFound(f"제안서 {slug!r}이(가) 없습니다")
    return p


def publish(slug: str, access_code: str | None = None) -> Published:
    """Freeze the draft as the next revision and show it to the customer.

    Locks the proposal, then its client (always in that order), so two publications of one
    proposal get consecutive revision numbers and two of one client consecutive serials.

    `access_code` is the owner's own choice for the first publication (empty: generated); a
    proposal that already has a code keeps it, so passing one then is a conflict.
    """
    with transaction.atomic():
        p = _locked_proposal(slug)
        if p.status == Proposal.Status.REVOKED:
            raise Conflict("회수된 제안서는 다시 발행할 수 없습니다. 복제해서 새 주소로 발행합니다")
        if access_code and access_code.strip() and p.access_code_hash:
            raise Conflict(
                "이미 접근 코드가 있습니다. 코드를 바꾸려면 접근 코드 재발급에서 지정하세요"
            )
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
        pdf.enqueue(revision)  # same transaction: the worker sees it once this commits
        code = None if p.access_code_hash else _issue_code(p, access_code)
        p.status = Proposal.Status.PUBLISHED
        p.save()
    return Published(slug=p.slug, revision=revision_out(revision), access_code=code)


def reissue_access_code(slug: str, access_code: str | None = None) -> IssuedCode:
    """A new code (the owner's `access_code`, else generated) for a published proposal; every
    customer session made with the old one ends."""
    with transaction.atomic():
        p = _locked_proposal(slug)
        if p.status != Proposal.Status.PUBLISHED:
            raise Conflict("발행된 제안서만 접근 코드를 다시 만들 수 있습니다")
        code = _issue_code(p, access_code)
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

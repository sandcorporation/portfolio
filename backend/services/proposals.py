"""Clients and proposals: the owner's side. Drafts live here; publishing is services/publishing.

Every write takes a Pydantic input (only `model_fields_set` fields change) and returns a Pydantic
output, and refuses with `services.errors`. Block and tab edits address blocks by `block_id` and
tabs by `tab_id`, touch nothing else, and re-validate the whole document before saving.
A proposal's draft stays editable after publishing: what the customer sees is a frozen revision,
and the next publication makes a new one. Only a revoked proposal is refused (it can never be
published again, so edits would go nowhere; duplicate it instead).
"""

import copy
from datetime import date, datetime, timedelta
from typing import Literal

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field

from content.models import (
    CLIENT_CODE_PATTERN,
    Client,
    Proposal,
    ProposalRevision,
    SiteProfile,
    default_proposal_document,
    new_proposal_slug,
    stored_document,
)
from documents.validation import JSON, DocumentError, InvalidDocument
from services import case_refs, media
from services.errors import Conflict, NotFound, Rejected
from services.profile import get_profile

PREVIEW_SALT = "proposal-preview"
# A different salt than the preview: a preview link can never open a print page, nor the reverse.
PRINT_SALT = "proposal-print"


# --- clients ---


class ClientOut(BaseModel):
    code: str
    name: str
    contact_title: str
    memo: str


class NewClient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=CLIENT_CODE_PATTERN, description="Uppercase, 2-6 letters; unique.")
    name: str = Field(min_length=1, max_length=120)
    contact_title: str = Field(default="", max_length=80, description="e.g. 홍길순 대표님")
    memo: str = ""


class ClientPatch(BaseModel):
    """Fields left out stay as they are. The code never changes."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", min_length=1, max_length=120)
    contact_title: str = Field(default="", max_length=80)
    memo: str = ""


def _client_out(client: Client) -> ClientOut:
    return ClientOut(
        code=client.code, name=client.name, contact_title=client.contact_title, memo=client.memo
    )


def _client_or_404(code: str) -> Client:
    client = Client.objects.filter(code=code).first()
    if client is None:
        raise NotFound(f"고객 {code!r}이(가) 없습니다")
    return client


def list_clients() -> list[ClientOut]:
    return [_client_out(c) for c in Client.objects.all()]


def create_client(new: NewClient) -> ClientOut:
    try:
        with transaction.atomic():
            client = Client.objects.create(**new.model_dump())
    except IntegrityError:
        raise Conflict(f"고객코드 {new.code!r}는 이미 쓰고 있습니다") from None
    return _client_out(client)


def update_client(code: str, patch: ClientPatch) -> ClientOut:
    client = _client_or_404(code)
    for name in patch.model_fields_set:
        setattr(client, name, getattr(patch, name))
    client.save()
    return _client_out(client)


# --- proposals ---


class ProposalSummary(BaseModel):
    slug: str
    client_code: str
    title: str
    subtitle: str
    quote_date: date
    valid_until: date | None
    status: str


class ProposalOut(ProposalSummary):
    document: dict[str, JSON]
    updated_at: datetime


class NewProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_code: str
    title: str = Field(min_length=1, max_length=160)
    subtitle: str = Field(default="", max_length=200)
    quote_date: date = Field(default_factory=date.today, description="견적 기준일")
    valid_until: date | None = None
    document: dict[str, object] | None = Field(
        default=None, description="Omit to start with the tabs 견적 제안 and 회사소개·수행사례."
    )


class ProposalPatch(BaseModel):
    """Metadata only (the document has its own functions). `valid_until: null` clears it."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", min_length=1, max_length=160)
    subtitle: str = Field(default="", max_length=200)
    quote_date: date = Field(default_factory=date.today)
    valid_until: date | None = None


def _summary_fields(p: Proposal) -> dict[str, object]:
    return {
        "slug": p.slug,
        "client_code": p.client.code,
        "title": p.title,
        "subtitle": p.subtitle,
        "quote_date": p.quote_date,
        "valid_until": p.valid_until,
        "status": p.status,
    }


def proposal_summary(p: Proposal) -> ProposalSummary:
    return ProposalSummary.model_validate(_summary_fields(p))


def proposal_out(p: Proposal) -> ProposalOut:
    return ProposalOut.model_validate(
        {**_summary_fields(p), "document": p.document, "updated_at": p.updated_at}
    )


def _proposal_or_404(slug: str) -> Proposal:
    p = Proposal.objects.select_related("client").filter(slug=slug).first()
    if p is None:
        raise NotFound(f"제안서 {slug!r}이(가) 없습니다")
    return p


def _document(data: object, prefix: str = "document") -> dict[str, JSON]:
    try:
        return stored_document(data, allow_private_media=True)
    except InvalidDocument as exc:
        raise Rejected([DocumentError(f"{prefix}.{e.path}", e.reason) for e in exc.errors]) from exc


def _editable(slug: str) -> Proposal:
    p = _proposal_or_404(slug)
    if p.status == Proposal.Status.REVOKED:
        raise Conflict("회수된 제안서는 고칠 수 없습니다. 복제해서 새 초안으로 고칩니다")
    return p


def list_proposals(client_code: str | None = None) -> list[ProposalSummary]:
    rows = Proposal.objects.select_related("client")
    if client_code is not None:
        rows = rows.filter(client__code=client_code)
    return [proposal_summary(p) for p in rows]


def get_proposal(slug: str) -> ProposalOut:
    return proposal_out(_proposal_or_404(slug))


def _starting_document() -> dict[str, JSON]:
    """The two default tabs. 회사소개·수행사례 starts with the site profile's company intro, copied
    now (the draft is then the author's to edit; a published revision freezes it anyway), then an
    empty `case-ref` block for the author to fill."""
    document = default_proposal_document()
    blocks: list[JSON] = []
    tabs_of_intro = get_profile().company_intro.get("tabs")
    for tab in tabs_of_intro if isinstance(tabs_of_intro, list) else []:
        tab_blocks = tab.get("blocks") if isinstance(tab, dict) else None
        for block in tab_blocks if isinstance(tab_blocks, list) else []:
            if isinstance(block, dict):
                blocks.append({**block, "id": f"intro-{block.get('id')}"})
    blocks.append({"id": "cases", "type": "case-ref", "title": "수행사례", "items": []})
    tabs = document["tabs"]
    assert isinstance(tabs, list)
    company = tabs[1]
    assert isinstance(company, dict)
    company["blocks"] = blocks
    return _document(document)


def create_proposal(new: NewProposal) -> ProposalOut:
    """A draft with a fresh random slug, for an existing client."""
    client = _client_or_404(new.client_code)
    p = Proposal(
        client=client,
        title=new.title,
        subtitle=new.subtitle,
        quote_date=new.quote_date,
        valid_until=new.valid_until,
    )
    p.document = _document(new.document) if new.document is not None else _starting_document()
    p.save()
    return proposal_out(p)


def duplicate_proposal(slug: str, client_code: str | None = None) -> ProposalOut:
    """A copy as a new draft with its own slug (for another client when `client_code` is given)."""
    source = _proposal_or_404(slug)
    client = _client_or_404(client_code) if client_code else source.client
    copy_ = Proposal(
        client=client,
        title=f"{source.title} (복사)",
        subtitle=source.subtitle,
        quote_date=source.quote_date,
        valid_until=source.valid_until,
        document=copy.deepcopy(source.document),
    )
    copy_.save()
    return proposal_out(copy_)


def update_proposal(slug: str, patch: ProposalPatch) -> ProposalOut:
    p = _editable(slug)
    for name in patch.model_fields_set:
        setattr(p, name, getattr(patch, name))
    p.save()
    return proposal_out(p)


# --- the document: whole, or a block / tab at a time ---


def _tabs(p: Proposal) -> list[dict[str, JSON]]:
    """The document's own tab list (edit it in place); stored documents hold only tab objects."""
    tabs: list[dict[str, JSON]] = p.document["tabs"]
    return tabs


def _blocks(tab: dict[str, JSON]) -> list[JSON]:
    blocks = tab["blocks"]
    assert isinstance(blocks, list)
    return blocks


def _find_tab(p: Proposal, tab_id: str) -> dict[str, JSON]:
    for tab in _tabs(p):
        if tab["id"] == tab_id:
            return tab
    raise NotFound(f"탭 {tab_id!r}이(가) 없습니다")


def _find_block(p: Proposal, block_id: str) -> tuple[list[JSON], int]:
    for tab in _tabs(p):
        blocks = _blocks(tab)
        for index, block in enumerate(blocks):
            if isinstance(block, dict) and block.get("id") == block_id:
                return blocks, index
    raise NotFound(f"블록 {block_id!r}이(가) 없습니다")


def _save_document(p: Proposal, document: object) -> ProposalOut:
    p.document = _document(document)
    p.save()
    return proposal_out(p)


def replace_document(slug: str, document: dict[str, object]) -> ProposalOut:
    return _save_document(_editable(slug), document)


def replace_block(slug: str, block_id: str, block: dict[str, object]) -> ProposalOut:
    """Swap one block in place (same position). A block without an `id` keeps `block_id`."""
    p = _editable(slug)
    blocks, index = _find_block(p, block_id)
    blocks[index] = {"id": block_id, **block}  # type: ignore[dict-item]  # JSON from the caller
    return _save_document(p, p.document)


def insert_block(
    slug: str, tab_id: str, block: dict[str, object], after_block_id: str | None = None
) -> ProposalOut:
    """Add a block to a tab: at the start, or right after `after_block_id` (in that tab)."""
    p = _editable(slug)
    blocks = _blocks(_find_tab(p, tab_id))
    position = 0
    if after_block_id is not None:
        ids = [b.get("id") if isinstance(b, dict) else None for b in blocks]
        if after_block_id not in ids:
            raise NotFound(f"탭 {tab_id!r}에 블록 {after_block_id!r}이(가) 없습니다")
        position = ids.index(after_block_id) + 1
    blocks.insert(position, block)  # type: ignore[arg-type]  # JSON from the caller
    return _save_document(p, p.document)


def delete_block(slug: str, block_id: str) -> ProposalOut:
    p = _editable(slug)
    blocks, index = _find_block(p, block_id)
    del blocks[index]
    return _save_document(p, p.document)


def add_tab(slug: str, title: str, tab_id: str | None = None) -> ProposalOut:
    """Append an empty tab; its id is generated unless given."""
    p = _editable(slug)
    tab: dict[str, JSON] = {"id": tab_id or f"tab-{new_proposal_slug()[:6]}", "title": title}
    tab["blocks"] = []
    _tabs(p).append(tab)
    return _save_document(p, p.document)


def delete_tab(slug: str, tab_id: str) -> ProposalOut:
    """Remove a tab with its blocks. A proposal keeps at least one tab."""
    p = _editable(slug)
    tab = _find_tab(p, tab_id)
    if len(_tabs(p)) == 1:
        raise Rejected.at("document.tabs", "탭이 하나뿐이라 지울 수 없습니다")
    _tabs(p).remove(tab)
    return _save_document(p, p.document)


def rename_tab(slug: str, tab_id: str, title: str) -> ProposalOut:
    p = _editable(slug)
    _find_tab(p, tab_id)["title"] = title
    return _save_document(p, p.document)


def reorder_tabs(slug: str, tab_ids: list[str]) -> ProposalOut:
    """Set the tab order. `tab_ids` must name every tab exactly once."""
    p = _editable(slug)
    tabs = {str(t["id"]): t for t in _tabs(p)}
    if sorted(tab_ids) != sorted(tabs):
        raise Rejected.at("tab_ids", f"모든 탭 id를 한 번씩 적어야 합니다: {', '.join(tabs)}")
    p.document = {"tabs": [tabs[i] for i in tab_ids]}
    return _save_document(p, p.document)


# --- preview: a signed, short-lived link ---


class PreviewLink(BaseModel):
    url: str
    expires_at: datetime


def issue_preview_url(slug: str) -> PreviewLink:
    """A link that shows the proposal (draft or not) as the customer will see it, for a while."""
    p = _proposal_or_404(slug)
    token = signing.TimestampSigner(salt=PREVIEW_SALT).sign(p.slug)
    expires_at = timezone.now() + timedelta(seconds=settings.PROPOSAL_PREVIEW_MAX_AGE)
    return PreviewLink(url=f"/preview/{token}", expires_at=expires_at)


class BadPreviewToken(Exception):
    pass


class ExpiredPreviewToken(BadPreviewToken):
    pass


def proposal_for_preview(token: str) -> Proposal:
    try:
        slug = signing.TimestampSigner(salt=PREVIEW_SALT).unsign(
            token, max_age=settings.PROPOSAL_PREVIEW_MAX_AGE
        )
    except signing.SignatureExpired:
        raise ExpiredPreviewToken from None
    except signing.BadSignature:
        raise BadPreviewToken from None
    p = Proposal.objects.select_related("client").filter(slug=slug).first()
    if p is None:
        raise BadPreviewToken
    return p


# --- the customer-facing page data (the draft's preview, and a revision on /p/<slug>) ---


class Supplier(BaseModel):
    name: str
    email: str
    phone: str
    address: str


class RevisionMeta(BaseModel):
    number: int
    doc_number: str
    published_at: datetime


class ProposalPageData(BaseModel):
    """Embedded as #page-data. Mirrors frontend/src/proposal/types.ts.

    `revision` and `csrf_token` (for the lock button) are set on the customer page only.
    `media_endpoint` is where the page asks for a fresh private media URL when one expires:
    GET {media_endpoint}/{media_id} -> {"url": ...}."""

    preview: bool
    recipient: str
    title: str
    subtitle: str
    quote_date: date
    valid_until: date | None
    supplier: Supplier
    document: dict[str, JSON]
    revision: RevisionMeta | None = None
    csrf_token: str | None = None
    media_endpoint: str | None = None
    # Print page only (/print/<token>, the PDF renderer's): the customer-facing address of the
    # proposal, which video / audio-compare blocks turn into a QR code plus link (`#<block id>`).
    print_mode: bool = False
    public_url: str | None = None
    # Customer page only: where the finished PDF of this revision downloads (absent until done).
    pdf_url: str | None = None


class CodeScreenData(BaseModel):
    """/p/<slug> before the code: the form, and why the last try failed (if it did)."""

    screen: Literal["code"] = "code"
    error: Literal["wrong", "blocked"] | None = None
    csrf_token: str


class ExpiredScreenData(BaseModel):
    """/p/<slug> past its validity date: whom to contact instead of the document."""

    screen: Literal["expired"] = "expired"
    valid_until: date
    supplier: Supplier


# --- print: a signed, very short-lived link to one revision, for the PDF renderer ---


class BadPrintToken(Exception):
    pass


class ExpiredPrintToken(BadPrintToken):
    pass


def issue_print_url(revision: ProposalRevision) -> str:
    """`/print/<token>`: the revision as a print layout. The token names the revision (not the
    proposal), expires after `PROPOSAL_PRINT_MAX_AGE`, and is not a preview token."""
    token = signing.TimestampSigner(salt=PRINT_SALT).sign(str(revision.pk))
    return f"/print/{token}"


def revision_for_print(token: str) -> ProposalRevision:
    try:
        raw = signing.TimestampSigner(salt=PRINT_SALT).unsign(
            token, max_age=settings.PROPOSAL_PRINT_MAX_AGE
        )
    except signing.SignatureExpired:
        raise ExpiredPrintToken from None
    except signing.BadSignature:
        raise BadPrintToken from None
    revision = (
        ProposalRevision.objects.select_related("proposal").filter(pk=raw).first()
        if raw.isdigit()
        else None
    )
    if revision is None:
        raise BadPrintToken
    return revision


def print_page_data(r: ProposalRevision, *, token: str) -> ProposalPageData:
    """The revision's frozen fields for the print layout. Private media is resolved now with the
    print token as the gate (no customer session on this route)."""
    data = revision_page_data(r, csrf_token="")
    return data.model_copy(
        update={
            "csrf_token": None,
            "media_endpoint": f"/print/{token}/media",
            "print_mode": True,
            "public_url": f"{settings.SITE_URL}/p/{r.proposal.slug}",
        }
    )


def supplier() -> Supplier:
    profile = SiteProfile.objects.filter(pk=1).first() or SiteProfile()
    return Supplier(
        name=settings.SUPPLIER_NAME,
        email=profile.contact_email,
        phone=profile.contact_phone,
        address=profile.address,
    )


def revision_page_data(
    r: ProposalRevision, *, csrf_token: str, pdf_url: str | None = None
) -> ProposalPageData:
    """The customer page: a revision's frozen fields, with media resolved now (private media as
    short-lived URLs: the caller has checked the customer session)."""
    return ProposalPageData(
        preview=False,
        recipient=r.recipient,
        title=r.title,
        subtitle=r.subtitle,
        quote_date=r.quote_date,
        valid_until=r.valid_until,
        supplier=supplier(),
        document=media.resolve_document(r.document, private=True),
        revision=RevisionMeta(
            number=r.number, doc_number=r.doc_number, published_at=r.published_at
        ),
        csrf_token=csrf_token,
        media_endpoint=f"/p/{r.proposal.slug}/media",
        pdf_url=pdf_url,
    )


def page_data(p: Proposal, *, preview: bool, media_endpoint: str | None = None) -> ProposalPageData:
    """The draft as the customer will see it. Private media is resolved only on the preview
    (the caller has checked the signed link)."""
    title = p.client.contact_title
    return ProposalPageData(
        preview=preview,
        recipient=f"{title}께" if title else p.client.name,
        title=p.title,
        subtitle=p.subtitle,
        quote_date=p.quote_date,
        valid_until=p.valid_until,
        supplier=supplier(),
        document=case_refs.expand(media.resolve_document(p.document, private=preview)),
        media_endpoint=media_endpoint,
    )

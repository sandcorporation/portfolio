"""Services sold as outsourced work (issue 163, moved to the database in issue 215): the home's
「외주로 맡는 일」 cards and the pages /services/<slug>.

Rows are `content.Service`, written through MCP (mcpserver/tools_services.py) or admin. A card
shows when `is_visible`, in `position` order. A page exists when `is_published` and its `lead`
is filled (`has_page`); every other slug is 404, out of the sitemap and without JSON-LD, and its
card opens the inquiry form with its 「구분」 preselected.

Owner side: `list_services`, `get_service`, `create_service`, `update_service`,
`publish_service`, `unpublish_service`, `issue_preview_url`. Writes take Pydantic inputs (only
the given fields change) and refuse with `services.errors`; `problems` is the one set of rules,
also run by admin (`Service.clean`). There is no delete: hide the card instead.

Public side (the shell): `get` (a page's copy), `cards`, `page_stamps` (sitemap `lastmod`),
`preview_offering`. Every fact quoted in `cases` comes from the linked post or portfolio item.
"""

from datetime import date, datetime
from typing import TypedDict

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from content.models import Inquiry, Service
from documents.validation import DocumentError
from services import preview
from services.errors import Conflict, NotFound, Rejected

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
SITE_OR_HTTPS = r"^(/[^\s]*|https://[^\s/]+[^\s]*)$"

AUDIENCE_MAX = 6
ITEMS_MAX = 8  # deliverables, steps
CASES_MAX = 8
# A published page needs these (the cards need only name, summary and inquiry_kind).
PAGE_FIELDS = ("lead", "audience", "deliverables", "steps", "contact")

KIND_HELP = "One of the inquiry form's 「구분」 values: " + ", ".join(Inquiry.Kind.values)


# --- the shapes: the shell's JSON (TypedDict) ---


class Item(TypedDict):
    title: str
    text: str


class Case(TypedDict):
    title: str
    href: str  # a page of this site (/…) or another site's https address (opens in a new tab)
    kind: str  # the mono label of the row: 「기록」 or 「포트폴리오」
    note: str


class Offering(TypedDict):
    """#page-data["offering"] of the shell. Mirrored by frontend/src/services/types.ts."""

    slug: str
    name: str
    summary: str  # the home row and the meta description
    inquiry_kind: str  # its value in the inquiry form's 「구분」 (content.Inquiry.Kind)
    lead: str  # under the page title
    service_type: str  # JSON-LD serviceType
    audience: list[str]
    deliverables: list[Item]
    steps: list[Item]
    cases: list[Case]
    contact: str


class OfferingCard(TypedDict):
    """One home row. Mirrored by frontend/src/services/types.ts."""

    slug: str
    name: str
    summary: str
    inquiry_kind: str
    href: str  # the service page, or the inquiry form for a card without a page


# --- the rules: lengths and counts that keep the page's shape ---


class ItemIn(BaseModel):
    """One line of 02 What / 03 Process: 「title — text」."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=300)


class CaseIn(BaseModel):
    """One row of 04 Cases. Only facts the linked page states."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    href: str = Field(
        max_length=300,
        pattern=SITE_OR_HTTPS,
        description="A page of this site (/blog/…, /work/…) or an https address of another site "
        "(opens in a new tab).",
    )
    kind: str = Field(min_length=1, max_length=20, description="Row label: 기록 or 포트폴리오.")
    note: str = Field(min_length=1, max_length=400)


type ListAdapter = TypeAdapter[list[str]] | TypeAdapter[list[ItemIn]] | TypeAdapter[list[CaseIn]]
_AUDIENCE = TypeAdapter(list[str])
_ITEMS = TypeAdapter(list[ItemIn])
_CASES = TypeAdapter(list[CaseIn])

_TEXT_LIMITS = {  # field -> most characters
    "name": 80,
    "summary": 200,
    "lead": 600,
    "service_type": 60,
    "contact": 400,
}
_LINE_MAX = 120


def _shape_errors(field: str, adapter: ListAdapter, value: object) -> list[DocumentError]:
    try:
        adapter.validate_python(value)
    except ValidationError as exc:
        return [
            DocumentError(
                field + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in e["loc"]),
                e["msg"],
            )
            for e in exc.errors()
        ]
    return []


def problems(service: Service) -> list[DocumentError]:
    """Everything wrong with a row as it stands (empty: fine to save). The same rules for MCP
    and admin."""
    found: list[DocumentError] = []
    if service.inquiry_kind not in Inquiry.Kind.values:
        found.append(DocumentError("inquiry_kind", KIND_HELP))
    for field in ("name", "summary"):
        if not str(getattr(service, field)).strip():
            found.append(DocumentError(field, "비어 있으면 안 됩니다"))
    for field, limit in _TEXT_LIMITS.items():
        if len(str(getattr(service, field))) > limit:
            found.append(DocumentError(field, f"{limit}자 이하여야 합니다"))
    shapes: list[tuple[str, ListAdapter, int]] = [
        ("audience", _AUDIENCE, AUDIENCE_MAX),
        ("deliverables", _ITEMS, ITEMS_MAX),
        ("steps", _ITEMS, ITEMS_MAX),
        ("cases", _CASES, CASES_MAX),
    ]
    for field, adapter, most in shapes:
        value = getattr(service, field)
        errors = _shape_errors(field, adapter, value)
        found.extend(errors)
        if errors:
            continue
        if len(value) > most:
            found.append(DocumentError(field, f"{most}개 이하여야 합니다"))
    for i, line in enumerate(service.audience if isinstance(service.audience, list) else []):
        if isinstance(line, str) and not (len(line.strip()) > 0 and len(line) <= _LINE_MAX):
            found.append(DocumentError(f"audience[{i}]", f"1~{_LINE_MAX}자여야 합니다"))
    if service.is_published:
        for field in PAGE_FIELDS:
            if not getattr(service, field):
                found.append(DocumentError(field, "상세 페이지를 공개하려면 채워야 합니다"))
    return found


def _check(service: Service) -> None:
    found = problems(service)
    if found:
        raise Rejected(found)


# --- owner side: Pydantic in, Pydantic out ---


class ServiceOut(BaseModel):
    slug: str
    name: str
    summary: str
    inquiry_kind: str
    lead: str
    service_type: str
    audience: list[str]
    deliverables: list[ItemIn]
    steps: list[ItemIn]
    cases: list[CaseIn]
    contact: str
    position: int
    is_visible: bool
    is_published: bool
    has_page: bool  # /services/<slug> answers (published and the lead filled)
    url: str  # where the home card links: the page, or the inquiry form
    updated_at: datetime


class NewService(BaseModel):
    """A new service starts hidden and unpublished; the page fields may come later."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(
        max_length=80, pattern=SLUG_PATTERN, description="URL part: /services/<slug>."
    )
    name: str = Field(min_length=1, max_length=80, description="The page title and card name.")
    summary: str = Field(
        min_length=1, max_length=200, description="One or two sentences: the card and meta."
    )
    inquiry_kind: str = Field(max_length=20, description=KIND_HELP)
    lead: str = Field(default="", max_length=600, description="The paragraph under the title.")
    service_type: str = Field(default="", max_length=60, description="JSON-LD serviceType.")
    audience: list[str] = Field(default_factory=list, max_length=AUDIENCE_MAX)
    deliverables: list[ItemIn] = Field(default_factory=list, max_length=ITEMS_MAX)
    steps: list[ItemIn] = Field(default_factory=list, max_length=ITEMS_MAX)
    cases: list[CaseIn] = Field(default_factory=list, max_length=CASES_MAX)
    contact: str = Field(default="", max_length=400, description="05 Contact paragraph.")
    position: int | None = Field(
        default=None, description="Card order, smaller first. Omit to put it last."
    )


class ServicePatch(BaseModel):
    """Fields left out stay as they are. Lists replace the whole list."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", min_length=1, max_length=80)
    summary: str = Field(default="", min_length=1, max_length=200)
    inquiry_kind: str = Field(default="", max_length=20, description=KIND_HELP)
    lead: str = Field(default="", max_length=600)
    service_type: str = Field(default="", max_length=60)
    audience: list[str] = Field(default_factory=list, max_length=AUDIENCE_MAX)
    deliverables: list[ItemIn] = Field(default_factory=list, max_length=ITEMS_MAX)
    steps: list[ItemIn] = Field(default_factory=list, max_length=ITEMS_MAX)
    cases: list[CaseIn] = Field(default_factory=list, max_length=CASES_MAX)
    contact: str = Field(default="", max_length=400)
    position: int = Field(default=0, description="Card order, smaller first.")
    is_visible: bool = Field(default=False, description="Show the card on the home page.")


def path(slug: str) -> str:
    return f"/services/{slug}"


def inquiry_href(slug: str) -> str:
    return f"/?inquiry={slug}#home-inquiry"


def has_page(service: Service) -> bool:
    return service.is_published and bool(service.lead.strip())


def _href(service: Service) -> str:
    return path(service.slug) if has_page(service) else inquiry_href(service.slug)


def service_out(service: Service) -> ServiceOut:
    return ServiceOut.model_validate(
        {
            **_offering(service),
            "position": service.position,
            "is_visible": service.is_visible,
            "is_published": service.is_published,
            "has_page": has_page(service),
            "url": _href(service),
            "updated_at": service.updated_at,
        }
    )


def _service_or_404(slug: str) -> Service:
    service = Service.objects.filter(slug=slug).first()
    if service is None:
        raise NotFound(f"서비스 {slug!r}이(가) 없습니다")
    return service


def list_services() -> list[ServiceOut]:
    """Every service in card order, hidden and unpublished ones included."""
    return [service_out(s) for s in Service.objects.order_by("position", "id")]


def get_service(slug: str) -> ServiceOut:
    return service_out(_service_or_404(slug))


def _items(values: list[ItemIn]) -> list[Item]:
    return [Item(title=v.title, text=v.text) for v in values]


def _cases(values: list[CaseIn]) -> list[Case]:
    return [Case(title=v.title, href=v.href, kind=v.kind, note=v.note) for v in values]


def create_service(new: NewService) -> ServiceOut:
    """A new hidden, unpublished service. A taken slug is a Conflict."""
    if Service.objects.filter(slug=new.slug).exists():
        raise Conflict(f"주소 {new.slug!r}는 이미 쓰고 있습니다")
    if new.position is None:
        last = Service.objects.aggregate(last=Max("position"))["last"]
        position = 0 if last is None else last + 1
    else:
        position = new.position
    service = Service(
        slug=new.slug,
        name=new.name,
        summary=new.summary,
        inquiry_kind=new.inquiry_kind,
        lead=new.lead,
        service_type=new.service_type,
        audience=list(new.audience),
        deliverables=_items(new.deliverables),
        steps=_items(new.steps),
        cases=_cases(new.cases),
        contact=new.contact,
        position=position,
    )
    _check(service)
    try:
        with transaction.atomic():
            service.save()
    except IntegrityError:
        raise Conflict(f"주소 {service.slug!r}는 이미 쓰고 있습니다") from None
    return service_out(service)


def update_service(slug: str, patch: ServicePatch) -> ServiceOut:
    """Change the given fields; a published page changes live. The slug does not change."""
    service = _service_or_404(slug)
    given = patch.model_fields_set
    for field in ("name", "summary", "inquiry_kind", "lead", "service_type", "contact"):
        if field in given:
            setattr(service, field, getattr(patch, field))
    if "audience" in given:
        service.audience = list(patch.audience)
    if "deliverables" in given:
        service.deliverables = _items(patch.deliverables)
    if "steps" in given:
        service.steps = _items(patch.steps)
    if "cases" in given:
        service.cases = _cases(patch.cases)
    if "position" in given:
        service.position = patch.position
    if "is_visible" in given:
        service.is_visible = patch.is_visible
    _check(service)
    service.save()
    return service_out(service)


def publish_service(slug: str) -> ServiceOut:
    """Open /services/<slug> (and point the card at it). Refused while a page field is empty."""
    service = _service_or_404(slug)
    service.is_published = True
    _check(service)
    service.save()
    return service_out(service)


def unpublish_service(slug: str) -> ServiceOut:
    """Close the page at once (404, out of the sitemap); the card goes back to the inquiry form."""
    service = _service_or_404(slug)
    service.is_published = False
    service.save()
    return service_out(service)


# --- public side: plain JSON for the shell ---


def _offering(service: Service) -> Offering:
    return Offering(
        slug=service.slug,
        name=service.name,
        summary=service.summary,
        inquiry_kind=service.inquiry_kind,
        lead=service.lead,
        service_type=service.service_type,
        audience=list(service.audience),
        deliverables=[Item(title=d["title"], text=d["text"]) for d in service.deliverables],
        steps=[Item(title=d["title"], text=d["text"]) for d in service.steps],
        cases=[
            Case(title=c["title"], href=c["href"], kind=c["kind"], note=c["note"])
            for c in service.cases
        ],
        contact=service.contact,
    )


def get(slug: str) -> Offering | None:
    """A page's copy; None when the slug has no page (unknown, unpublished or without copy)."""
    service = Service.objects.filter(slug=slug, is_published=True).first()
    if service is None or not has_page(service):
        return None
    return _offering(service)


def cards() -> list[OfferingCard]:
    """The home's rows: visible services in `position` order."""
    return [
        OfferingCard(
            slug=s.slug,
            name=s.name,
            summary=s.summary,
            inquiry_kind=s.inquiry_kind,
            href=_href(s),
        )
        for s in Service.objects.filter(is_visible=True).order_by("position", "id")
    ]


def page_stamps() -> list[tuple[str, date]]:
    """(path, day of the last change) of every page, in card order, for sitemap `lastmod`."""
    rows = Service.objects.filter(is_published=True).order_by("position", "id")
    return [(path(s.slug), timezone.localdate(s.updated_at)) for s in rows if has_page(s)]


# --- preview: a signed, short-lived link to a page as it will look, unpublished included ---

PREVIEW_SALT = "service-preview"


def issue_preview_url(slug: str) -> preview.PreviewLink:
    """A link (`/preview/services/<token>`) that shows the page, published or not, as
    /services/<slug> will, for `SERVICE_PREVIEW_MAX_AGE` seconds. Refused without a lead."""
    service = _service_or_404(slug)
    if not service.lead.strip():
        raise Rejected.at("lead", "리드가 비어 있어 그릴 페이지가 없습니다")
    return preview.issue(
        salt=PREVIEW_SALT,
        value=service.slug,
        path="/preview/services/",
        max_age=settings.SERVICE_PREVIEW_MAX_AGE,
    )


def preview_offering(token: str) -> Offering:
    """The page a preview link names. `preview.BadPreviewToken`/`ExpiredPreviewToken`."""
    slug = preview.unsign(token, salt=PREVIEW_SALT, max_age=settings.SERVICE_PREVIEW_MAX_AGE)
    service = Service.objects.filter(slug=slug).first()
    if service is None or not service.lead.strip():
        raise preview.BadPreviewToken
    return _offering(service)

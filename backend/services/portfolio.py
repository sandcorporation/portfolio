"""Portfolio items. Public reads hide hidden items; `get_item`/`all_items` do not.

Proposal `case-ref` blocks (and MCP tools) use the full lookups, because a hidden item can still
be cited in a proposal. Public pages use `public_cards` / `public_detail` / `public_slugs`.
"""

from datetime import datetime
from typing import Literal, TypedDict

from django.db import transaction
from django.db.models import Max
from pydantic import BaseModel, ConfigDict, Field, field_validator

from adapters.metrics import Stats, fetch_stats
from content.github_profile import http_url
from content.models import (
    Media,
    PortfolioItem,
    PortfolioSlugAlias,
    empty_document,
    media_kind,
    stored_document,
)
from documents.validation import JSON, DocumentError, InvalidDocument
from services import media
from services.errors import Conflict, NotFound, Rejected


class Visits(TypedDict):
    """One site's counts on a portfolio row: visitors today and since the count began."""

    today: int
    total: int


class PortfolioCard(TypedDict):
    slug: str
    title: str
    summary: str
    cover_url: str
    tags: list[str]
    period: str
    status: str  # "live" | "building" | "ended" | "" (not shown)
    status_label: str  # the Korean label of `status`, "" when there is none
    outcome: str
    visits: Visits | None  # None: no site key, not in the counts, or the numbers are off


class PortfolioDetail(TypedDict):
    """Embedded in the shell as #page-data on /work/<slug>. Mirrors frontend/src/work/types.ts."""

    card: PortfolioCard
    service_url: str
    body: dict[str, JSON]


def card_of(item: PortfolioItem, stats: Stats | None = None) -> PortfolioCard:
    # The only place that reads the cover: a media reference turned into its public URL.
    return PortfolioCard(
        slug=item.slug,
        title=item.title,
        summary=item.summary,
        cover_url=(media.public_url(item.cover) or "") if item.cover else "",
        tags=item.tag_list(),
        period=item.period,
        status=item.status,
        status_label=item.get_status_display() if item.status else "",
        outcome=item.outcome,
        visits=visits_of(item, stats),
    )


def visits_of(item: PortfolioItem, stats: Stats | None) -> Visits | None:
    site = stats.site(item.metrics_site_key) if stats and item.metrics_site_key else None
    if site is None:
        return None
    return Visits(today=site.today_visitors, total=site.total_visitors)


def detail_of(item: PortfolioItem) -> PortfolioDetail:
    return PortfolioDetail(
        card=card_of(item),
        service_url=item.service_url,
        body=media.resolve_document(item.body),
    )


# --- full lookups: include hidden items ---


def all_items() -> list[PortfolioItem]:
    return list(PortfolioItem.objects.all())


def get_item(slug: str) -> PortfolioItem | None:
    return PortfolioItem.objects.filter(slug=slug).first()


# --- public lookups: published items only ---


def public_items() -> list[PortfolioItem]:
    return list(PortfolioItem.objects.filter(is_public=True).select_related("cover"))


def public_cards() -> list[PortfolioCard]:
    stats = fetch_stats()
    return [card_of(item, stats) for item in public_items()]


def public_slugs() -> list[str]:
    return [item.slug for item in public_items()]


def renamed_to(slug: str) -> str | None:
    """The current slug of a public item that once had `slug`, else None (#111)."""
    alias = PortfolioSlugAlias.objects.filter(slug=slug, item__is_public=True).select_related(
        "item"
    )
    found = alias.first()
    return found.item.slug if found else None


def public_modified() -> dict[str, datetime]:
    """slug -> last change of every public item, for sitemap `lastmod`."""
    return {item.slug: item.updated_at for item in public_items()}


def public_detail(slug: str) -> PortfolioDetail | None:
    item = PortfolioItem.objects.filter(slug=slug, is_public=True).first()
    return detail_of(item) if item else None


# --- writes (MCP tools and the admin API call these) ---

ItemStatus = Literal["", "live", "building", "ended"]  # PortfolioItem.Status values, or none
SLUG_PATTERN = r"^[-a-zA-Z0-9_]+$"
TAGS_MAX_LENGTH = 200  # the column's width once joined with ", "


class ItemSummary(BaseModel):
    """One row of the owner's list: hidden items included, with their public flag."""

    id: int  # what a `case-ref` block's `item_id` takes
    slug: str
    title: str
    summary: str
    tags: list[str]
    period: str
    status: str
    outcome: str
    service_url: str
    metrics_site_key: str
    is_public: bool
    sort_order: int
    cover_media_id: int | None
    url: str


class ItemAdmin(ItemSummary):
    body: dict[str, JSON]
    updated_at: datetime


class NewItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(
        min_length=1, max_length=50, pattern=SLUG_PATTERN, description="URL part: /work/<slug>."
    )
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=300, description="Card and OG description.")
    tags: list[str] = Field(default_factory=list)
    period: str = Field(default="", max_length=60, description="e.g. 2025.03 ~ 2025.08")
    status: ItemStatus = Field(
        default="",
        description='"live" (운영 중), "building" (진행 중), "ended" (서비스 종료); "" shows none.',
    )
    outcome: str = Field(
        default="",
        max_length=160,
        description="One-line result shown under the title on the home row instead of the summary.",
    )
    service_url: str = Field(
        default="",
        max_length=300,
        description="Address of the running service (e.g. https://codemit.kr); lists it in the "
        "GitHub README's services table.",
    )
    metrics_site_key: str = Field(
        default="",
        max_length=40,
        description="sandcorp-metrics site key (codemit, daypage, foresight, sandcorp); the "
        "home page row shows that site's visit counts. Empty shows none.",
    )
    cover_media_id: int | None = Field(
        default=None, description="Id of a finished, public upload; omit for no cover."
    )
    body: dict[str, object] = Field(
        default_factory=lambda: dict[str, object](empty_document()),
        description="Block document (see block_schema).",
    )
    is_public: bool = Field(default=False, description="Created hidden unless true.")

    @field_validator("service_url")
    @classmethod
    def _service_url(cls, value: str) -> str:
        return http_url(value)


class ItemPatch(BaseModel):
    """Fields left out stay as they are. `cover_media_id: null` removes the cover."""

    model_config = ConfigDict(extra="forbid")

    new_slug: str = Field(
        default="",
        min_length=1,
        max_length=50,
        pattern=SLUG_PATTERN,
        description="Change the address. The old /work/<slug> then redirects (301) to the new one.",
    )
    title: str = Field(default="", min_length=1, max_length=120)
    summary: str = Field(default="", max_length=300)
    tags: list[str] = Field(default_factory=list)
    period: str = Field(default="", max_length=60)
    status: ItemStatus = Field(default="", description='"" clears it.')
    outcome: str = Field(default="", max_length=160, description='"" clears it.')
    service_url: str = Field(default="", max_length=300, description='"" clears it.')
    metrics_site_key: str = Field(
        default="", max_length=40, description='sandcorp-metrics site key; "" clears it.'
    )
    cover_media_id: int | None = None
    body: dict[str, object] = Field(
        default_factory=dict, description="Whole block document (see block_schema)."
    )

    @field_validator("service_url")
    @classmethod
    def _service_url(cls, value: str) -> str:
        return http_url(value)


def _summary_fields(item: PortfolioItem) -> dict[str, object]:
    return {
        "id": item.pk,
        "slug": item.slug,
        "title": item.title,
        "summary": item.summary,
        "tags": item.tag_list(),
        "period": item.period,
        "status": item.status,
        "outcome": item.outcome,
        "service_url": item.service_url,
        "metrics_site_key": item.metrics_site_key,
        "is_public": item.is_public,
        "sort_order": item.sort_order,
        "cover_media_id": item.cover_id,
        "url": f"/work/{item.slug}",
    }


def summary_of(item: PortfolioItem) -> ItemSummary:
    return ItemSummary.model_validate(_summary_fields(item))


def admin_of(item: PortfolioItem) -> ItemAdmin:
    return ItemAdmin.model_validate(
        {**_summary_fields(item), "body": item.body, "updated_at": item.updated_at}
    )


def list_summaries() -> list[ItemSummary]:
    return [summary_of(item) for item in all_items()]


def read_item(slug: str) -> ItemAdmin:
    return admin_of(_item_or_404(slug))


def _item_or_404(slug: str) -> PortfolioItem:
    item = get_item(slug)
    if item is None:
        raise NotFound(f"포트폴리오 항목 {slug!r}이(가) 없습니다")
    return item


def clean_tags(tags: list[str]) -> list[str]:
    cleaned = [tag.strip() for tag in tags if tag.strip()]
    if any("," in tag for tag in cleaned):
        raise Rejected.at("tags", "태그에 쉼표를 넣을 수 없습니다")
    if len(", ".join(cleaned)) > TAGS_MAX_LENGTH:
        raise Rejected.at("tags", f"태그를 합쳐 {TAGS_MAX_LENGTH}자 이하로 줄이세요")
    return cleaned


def cover_media(media_id: int | None) -> Media | None:
    if media_id is None:
        return None
    found = Media.objects.filter(pk=media_id).first()
    if found is None:
        raise Rejected.at("cover_media_id", f"미디어 {media_id}가 없습니다")
    if not found.is_complete:
        raise Rejected.at("cover_media_id", f"미디어 {media_id}는 업로드가 끝나지 않았습니다")
    if not found.is_public:
        raise Rejected.at("cover_media_id", f"미디어 {media_id}는 공개 미디어가 아닙니다")
    if media_kind(found.content_type) != "image":
        raise Rejected.at("cover_media_id", f"미디어 {media_id}는 이미지가 아닙니다")
    return found


def _body(document: object) -> dict[str, JSON]:
    try:
        return stored_document(document)
    except InvalidDocument as exc:
        raise Rejected([DocumentError(f"body.{e.path}", e.reason) for e in exc.errors]) from exc


def create_item(new: NewItem) -> ItemAdmin:
    """Append a new item after the last one. Nothing is saved if anything is refused."""
    if (
        PortfolioItem.objects.filter(slug=new.slug).exists()
        or PortfolioSlugAlias.objects.filter(slug=new.slug).exists()
    ):
        raise Conflict(f"주소 {new.slug!r}는 이미 쓰고 있습니다")
    item = PortfolioItem(
        slug=new.slug,
        title=new.title,
        summary=new.summary,
        tags=", ".join(clean_tags(new.tags)),
        period=new.period,
        status=new.status,
        outcome=new.outcome.strip(),
        service_url=new.service_url,
        metrics_site_key=new.metrics_site_key.strip(),
        cover=cover_media(new.cover_media_id),
        body=_body(new.body),
        is_public=new.is_public,
        sort_order=(PortfolioItem.objects.aggregate(top=Max("sort_order"))["top"] or 0) + 10,
    )
    item.save()
    return admin_of(item)


def update_item(slug: str, patch: ItemPatch) -> ItemAdmin:
    item = _item_or_404(slug)
    given = patch.model_fields_set
    if "new_slug" in given and patch.new_slug != item.slug:
        taken = PortfolioItem.objects.filter(slug=patch.new_slug).exists()
        if (
            taken
            or PortfolioSlugAlias.objects.filter(slug=patch.new_slug).exclude(item=item).exists()
        ):
            raise Conflict(f"주소 {patch.new_slug!r}는 이미 쓰고 있습니다")
        item.slug = patch.new_slug
    if "title" in given:
        item.title = patch.title
    if "summary" in given:
        item.summary = patch.summary
    if "period" in given:
        item.period = patch.period
    if "status" in given:
        item.status = patch.status
    if "outcome" in given:
        item.outcome = patch.outcome.strip()
    if "service_url" in given:
        item.service_url = patch.service_url
    if "metrics_site_key" in given:
        item.metrics_site_key = patch.metrics_site_key.strip()
    if "tags" in given:
        item.tags = ", ".join(clean_tags(patch.tags))
    if "cover_media_id" in given:
        item.cover = cover_media(patch.cover_media_id)
    if "body" in given:
        item.body = _body(patch.body)
    item.save()
    return admin_of(item)


def set_visibility(slug: str, is_public: bool) -> ItemAdmin:
    item = _item_or_404(slug)
    item.is_public = is_public
    item.save(update_fields=["is_public", "updated_at"])
    return admin_of(item)


def reorder(slugs: list[str]) -> list[ItemSummary]:
    """Set the display order (hidden items included). `slugs` must name every item exactly once."""
    with transaction.atomic():
        items = {item.slug: item for item in PortfolioItem.objects.select_for_update()}
        missing = sorted(set(items) - set(slugs))
        unknown = sorted(set(slugs) - set(items))
        if len(set(slugs)) != len(slugs) or missing or unknown:
            problems = []
            if unknown:
                problems.append(f"없는 주소: {', '.join(unknown)}")
            if missing:
                problems.append(f"빠진 주소: {', '.join(missing)}")
            if len(set(slugs)) != len(slugs):
                problems.append("같은 주소가 두 번 들어 있습니다")
            raise Rejected.at("slugs", "; ".join(problems))
        for position, slug in enumerate(slugs):
            PortfolioItem.objects.filter(pk=items[slug].pk).update(sort_order=(position + 1) * 10)
    return list_summaries()

"""Development tips (/tips, issue 203): short markdown notes written and published through MCP.

Owner side (MCP tools): `list_tips`, `get_tip`, `create_tip`, `update_tip`, `publish_tip`,
`unpublish_tip`, `delete_tip`, `issue_preview_url`. Writes take Pydantic inputs (only the given
fields change) and refuse with `services.errors`. The same rules as the blog (services/blog.py):
a tip starts as a draft, `published_at` is set on the first publication and kept.

Public side (the shell): `public_listing` (`?category=`, `?page=` 20 a page), `public_detail`
(with up to three other tips of the same categories), `public_modified_by_slug` for the sitemap.
Drafts never appear there.

There is no source field on purpose: where a tip came from is not published (issue 203).
"""

import re
import secrets
from datetime import datetime
from typing import Literal, TypedDict

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Q, QuerySet
from django.utils.text import slugify
from pydantic import BaseModel, ConfigDict, Field

from content.models import Tip, TipCategory
from services import preview
from services.errors import Conflict, NotFound
from services.portfolio import SLUG_PATTERN

SLUG_MAX_LENGTH = 80
_SUFFIX_ROOM = 6  # "-9999" and a little; generated slugs are cut so a suffix still fits
_MIN_LATIN = 3
PAGE_SIZE = 20
RELATED_SIZE = 3

type TipStatus = Literal["draft", "published"]
type CategoryValue = Literal[
    "testing", "performance", "realtime", "memory", "deploy", "frontend", "auth", "debugging"
]

CATEGORY_HELP = "Any of: " + ", ".join(f"{c.value} ({c.label})" for c in TipCategory)


# --- owner side: Pydantic in, Pydantic out ---


class TipSummary(BaseModel):
    id: int
    slug: str
    title: str
    summary: str
    categories: list[CategoryValue]
    status: TipStatus
    published_at: datetime | None
    url: str
    updated_at: datetime


class TipOut(TipSummary):
    body: str
    created_at: datetime


class NewTip(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    slug: str = Field(
        default="",
        max_length=SLUG_MAX_LENGTH,
        pattern=r"^$|" + SLUG_PATTERN,
        description="URL part: /tips/<slug>. Omit to make one from the title (latin letters "
        "and digits; a mostly Korean title gets tip-<hex>; a taken one gets -2, -3...).",
    )
    summary: str = Field(default="", max_length=200, description="One line for the list and OG.")
    categories: list[CategoryValue] = Field(default_factory=list, description=CATEGORY_HELP)
    body: str = Field(default="", description="Markdown: problem, cause, fix, a short code block.")


class TipPatch(BaseModel):
    """Fields left out stay as they are."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", min_length=1, max_length=120)
    summary: str = Field(default="", max_length=200)
    categories: list[CategoryValue] = Field(default_factory=list, description=CATEGORY_HELP)
    body: str = Field(default="", description="The whole markdown body.")


def _summary_fields(tip: Tip) -> dict[str, object]:
    return {
        "id": tip.pk,
        "slug": tip.slug,
        "title": tip.title,
        "summary": tip.summary,
        "categories": tip.category_list(),
        "status": tip.status,
        "published_at": tip.published_at,
        "url": tip_path(tip.slug),
        "updated_at": tip.updated_at,
    }


def tip_path(slug: str) -> str:
    return f"/tips/{slug}"


def summary_of(tip: Tip) -> TipSummary:
    return TipSummary.model_validate(_summary_fields(tip))


def tip_out(tip: Tip) -> TipOut:
    return TipOut.model_validate(
        {**_summary_fields(tip), "body": tip.body, "created_at": tip.created_at}
    )


def _published() -> QuerySet[Tip]:
    return Tip.objects.filter(status=Tip.Status.PUBLISHED, published_at__isnull=False).order_by(
        "-published_at", "-id"
    )


def _in_category(query: QuerySet[Tip], category: str) -> QuerySet[Tip]:
    return query.filter(categories__contains=[category]) if category else query


def list_tips(
    published_only: bool = True, limit: int | None = None, category: str = ""
) -> list[TipSummary]:
    """Tips newest publication first; with `published_only=False` drafts come first."""
    if published_only:
        query = _published()
    else:  # drafts (no published_at yet) first, then newest publication first
        query = Tip.objects.order_by(F("published_at").desc(nulls_first=True), "-id")
    query = _in_category(query, category.strip())
    tips = query if limit is None else query[: max(limit, 0)]
    return [summary_of(t) for t in tips]


def _tip_or_404(slug: str) -> Tip:
    tip = Tip.objects.filter(slug=slug).first()
    if tip is None:
        raise NotFound(f"팁 {slug!r}이(가) 없습니다")
    return tip


def get_tip(slug: str) -> TipOut:
    """One tip with its body, draft or published (the owner's view)."""
    return tip_out(_tip_or_404(slug))


def slug_base(title: str) -> str:
    """A slug made from the title: its latin letters and digits, or `tip-<hex>` when it has
    fewer than three of them (a Korean title)."""
    base = slugify(title)[: SLUG_MAX_LENGTH - _SUFFIX_ROOM].strip("-")
    if len(re.sub(r"[^a-z0-9]", "", base)) < _MIN_LATIN:
        return f"tip-{secrets.token_hex(3)}"
    return base


def _free_slug(base: str) -> str:
    taken = set(Tip.objects.filter(slug__startswith=base).values_list("slug", flat=True))
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def create_tip(new: NewTip) -> TipOut:
    """A new draft. A given slug that is taken is a Conflict; a generated one gets -2, -3..."""
    if new.slug and Tip.objects.filter(slug=new.slug).exists():
        raise Conflict(f"주소 {new.slug!r}는 이미 쓰고 있습니다")
    tip = Tip(
        slug=new.slug or _free_slug(slug_base(new.title)),
        title=new.title,
        summary=new.summary,
        categories=list(new.categories),
        body=new.body,
    )
    try:
        with transaction.atomic():
            tip.save()
    except IntegrityError:
        raise Conflict(f"주소 {tip.slug!r}는 이미 쓰고 있습니다") from None
    return tip_out(tip)


def update_tip(slug: str, patch: TipPatch) -> TipOut:
    """Change the given fields. The slug does not change."""
    tip = _tip_or_404(slug)
    given = patch.model_fields_set
    if "title" in given:
        tip.title = patch.title
    if "summary" in given:
        tip.summary = patch.summary
    if "categories" in given:
        tip.categories = list(patch.categories)
    if "body" in given:
        tip.body = patch.body
    tip.save()
    return tip_out(tip)


def publish_tip(slug: str) -> TipOut:
    """Show the tip on /tips. The first publication sets `published_at`; later ones keep it."""
    tip = _tip_or_404(slug)
    tip.status = Tip.Status.PUBLISHED
    tip.save()  # the model fills published_at the first time
    return tip_out(tip)


def unpublish_tip(slug: str) -> TipOut:
    """Back to draft: gone from /tips and the sitemap at once. `published_at` is kept."""
    tip = _tip_or_404(slug)
    tip.status = Tip.Status.DRAFT
    tip.save()
    return tip_out(tip)


def delete_tip(slug: str) -> None:
    _tip_or_404(slug).delete()


# --- public side: published tips only, plain JSON for the shell ---


class CategoryRef(TypedDict):
    value: str
    label: str


class CategoryCount(CategoryRef):
    count: int


class TipCard(TypedDict):
    slug: str
    title: str
    summary: str
    categories: list[CategoryRef]
    published_at: str  # ISO 8601


class TipDetail(TypedDict):
    """For /tips/<slug>. `related`: up to three other published tips sharing a category, newest
    first. Mirrored by frontend/src/tips/types.ts."""

    card: TipCard
    body: str  # markdown
    related: list[TipCard]


class TipListing(TypedDict):
    """For /tips: one page of the newest-first list, the categories in use and which one is on.
    Mirrored by frontend/src/tips/types.ts."""

    tips: list[TipCard]
    categories: list[CategoryCount]
    category: CategoryRef | None  # None for every tip
    page: int  # 1-based
    pages: int  # at least 1 (an empty list is one empty page)
    total: int


def _refs(values: list[str]) -> list[CategoryRef]:
    return [CategoryRef(value=v, label=TipCategory(v).label) for v in values]


def _card(tip: Tip, published_at: datetime) -> TipCard:
    return TipCard(
        slug=tip.slug,
        title=tip.title,
        summary=tip.summary,
        categories=_refs(tip.category_list()),
        published_at=published_at.isoformat(),
    )


def card_of(tip: Tip) -> TipCard:
    assert tip.published_at is not None  # public tips always have it
    return _card(tip, tip.published_at)


def public_cards(limit: int | None = None) -> list[TipCard]:
    """Newest published tips as list cards (the home page's pool, issue 204)."""
    query = _published()
    tips = query if limit is None else query[: max(limit, 0)]
    return [card_of(t) for t in tips]


def category_ref(value: str) -> CategoryRef | None:
    """The category a `?category=` value names; None for an unknown one."""
    if value not in TipCategory.values:
        return None
    return _refs([value])[0]


def public_categories() -> list[CategoryCount]:
    """The categories published tips use, in the fixed order, with how many tips each."""
    counts: dict[str, int] = {}
    for values in _published().values_list("categories", flat=True):
        for value in values:
            counts[value] = counts.get(value, 0) + 1
    return [
        CategoryCount(value=c.value, label=c.label, count=counts[c.value])
        for c in TipCategory
        if counts.get(c.value)
    ]


def public_listing(
    category: str = "", page: int = 1, per_page: int = PAGE_SIZE
) -> TipListing | None:
    """One page of the public list; None for an unknown category or a page out of range."""
    category = category.strip()
    chosen = category_ref(category) if category else None
    if category and chosen is None:
        return None
    query = _in_category(_published(), category)
    total = query.count()
    pages = max(1, -(-total // per_page))
    if not 1 <= page <= pages:
        return None
    start = (page - 1) * per_page
    return TipListing(
        tips=[card_of(t) for t in query[start : start + per_page]],
        categories=public_categories(),
        category=chosen,
        page=page,
        pages=pages,
        total=total,
    )


def _related(tip: Tip) -> list[TipCard]:
    values = tip.category_list()
    if not values:
        return []
    shares = Q()
    for value in values:
        shares |= Q(categories__contains=[value])
    others = _published().exclude(pk=tip.pk).filter(shares)[:RELATED_SIZE]
    return [card_of(t) for t in others]


def public_detail(slug: str) -> TipDetail | None:
    tip = _published().filter(slug=slug).first()
    if tip is None:
        return None
    return TipDetail(card=card_of(tip), body=tip.body, related=_related(tip))


def public_modified_at(slug: str) -> str | None:
    """When a published tip last changed (ISO 8601), for `article:modified_time`/`dateModified`."""
    tip = _published().filter(slug=slug).only("updated_at", "published_at").first()
    if tip is None or tip.published_at is None:
        return None
    return max(tip.updated_at, tip.published_at).isoformat()


def public_modified_by_slug() -> dict[str, datetime]:
    """slug -> last change of every published tip, newest first, for sitemap `lastmod`."""
    rows = _published().values_list("slug", "updated_at", "published_at")
    return {slug: max(updated, published) for slug, updated, published in rows if published}


# --- preview: a signed, short-lived link to a tip as it will look, drafts included ---

PREVIEW_SALT = "tip-preview"


def issue_preview_url(slug: str) -> preview.PreviewLink:
    """A link (`/preview/tips/<token>`) that shows the tip, draft or published, as /tips/<slug>
    will, for `TIP_PREVIEW_MAX_AGE` seconds."""
    tip = _tip_or_404(slug)
    return preview.issue(
        salt=PREVIEW_SALT,
        value=tip.slug,
        path="/preview/tips/",
        max_age=settings.TIP_PREVIEW_MAX_AGE,
    )


def preview_detail(token: str) -> TipDetail:
    """The tip a preview link names, as `public_detail` would give it (a draft is dated by its
    last change and lists no related tips). `preview.BadPreviewToken`/`ExpiredPreviewToken`."""
    slug = preview.unsign(token, salt=PREVIEW_SALT, max_age=settings.TIP_PREVIEW_MAX_AGE)
    tip = Tip.objects.filter(slug=slug).first()
    if tip is None:
        raise preview.BadPreviewToken
    return TipDetail(card=_card(tip, tip.published_at or tip.updated_at), body=tip.body, related=[])

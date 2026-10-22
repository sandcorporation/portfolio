"""Portfolio items. Public reads hide hidden items; `get_item`/`all_items` do not.

Proposal `case-ref` blocks (and MCP tools) use the full lookups, because a hidden item can still
be cited in a proposal. Public pages use `public_cards` / `public_detail` / `public_slugs`.
"""

from typing import TypedDict

from content.models import PortfolioItem
from documents.validation import JSON


class PortfolioCard(TypedDict):
    slug: str
    title: str
    summary: str
    cover_url: str
    tags: list[str]
    period: str


class PortfolioDetail(TypedDict):
    """Embedded in the shell as #page-data on /work/<slug>. Mirrors frontend/src/work/types.ts."""

    card: PortfolioCard
    body: dict[str, JSON]


def card_of(item: PortfolioItem) -> PortfolioCard:
    # The only place that reads cover_url; #10 swaps it for a media reference here.
    return PortfolioCard(
        slug=item.slug,
        title=item.title,
        summary=item.summary,
        cover_url=item.cover_url,
        tags=item.tag_list(),
        period=item.period,
    )


def detail_of(item: PortfolioItem) -> PortfolioDetail:
    return PortfolioDetail(card=card_of(item), body=item.body)


# --- full lookups: include hidden items ---


def all_items() -> list[PortfolioItem]:
    return list(PortfolioItem.objects.all())


def get_item(slug: str) -> PortfolioItem | None:
    return PortfolioItem.objects.filter(slug=slug).first()


# --- public lookups: published items only ---


def public_items() -> list[PortfolioItem]:
    return list(PortfolioItem.objects.filter(is_public=True))


def public_cards() -> list[PortfolioCard]:
    return [card_of(item) for item in public_items()]


def public_slugs() -> list[str]:
    return [item.slug for item in public_items()]


def public_detail(slug: str) -> PortfolioDetail | None:
    item = PortfolioItem.objects.filter(slug=slug, is_public=True).first()
    return detail_of(item) if item else None

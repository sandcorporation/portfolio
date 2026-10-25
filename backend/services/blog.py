"""The blog 「기록」: posts are block documents written and published through MCP (#74).

Owner side (MCP tools; the `/mcp` bearer check makes every caller the owner): `list_posts`,
`get_post`, `create_post`, `update_post`, block edits `replace_block`/`insert_block`/
`delete_block` (the same `services.document_edit` path as proposals, then the whole document is
re-validated), `publish_post`/`unpublish_post`, `delete_post`. Writes take Pydantic inputs (only
the fields given change) and refuse with `services.errors`; a bad document is `Rejected` with
`body.tabs[..]` block paths and nothing is saved.

Public side (the shell and #75's screens): `public_cards`, `public_detail` (with the neighbouring
posts), `public_slugs`, `public_tags`, `feed_items`. Drafts never appear there.

`published_at` is set the first time a post is published and kept from then on (unpublishing and
publishing again does not move it); admin may edit it to change the order.
"""

import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypedDict

from django.db import IntegrityError, transaction
from django.db.models import F, Q, QuerySet
from django.utils.text import slugify
from pydantic import BaseModel, ConfigDict, Field

from content.models import BlogPost, empty_document, stored_document
from documents.validation import JSON, DocumentError, InvalidDocument
from services import document_edit, media
from services.errors import Conflict, NotFound, Rejected
from services.portfolio import SLUG_PATTERN, clean_tags, cover_media

SLUG_MAX_LENGTH = 80
_SUFFIX_ROOM = 6  # "-9999" and a little; generated slugs are cut so a suffix still fits
_MIN_LATIN = 3

type PostStatus = Literal["draft", "published"]


# --- owner side: Pydantic in, Pydantic out ---


class PostSummary(BaseModel):
    id: int
    slug: str
    title: str
    summary: str
    tags: list[str]
    status: PostStatus
    published_at: datetime | None
    cover_media_id: int | None
    url: str
    updated_at: datetime


class PostOut(PostSummary):
    body: dict[str, JSON]
    created_at: datetime


class NewPost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    slug: str = Field(
        default="",
        max_length=SLUG_MAX_LENGTH,
        pattern=r"^$|" + SLUG_PATTERN,
        description="URL part: /blog/<slug>. Omit to make one from the title (latin letters "
        "and digits; a mostly Korean title gets post-<hex>; a taken one gets -2, -3...).",
    )
    summary: str = Field(default="", max_length=300, description="List and OG description.")
    tags: list[str] = Field(default_factory=list)
    cover_media_id: int | None = Field(
        default=None, description="Id of a finished, public image upload; omit for no cover."
    )
    body: dict[str, object] = Field(
        default_factory=lambda: dict[str, object](empty_document()),
        description="Block document (see block_schema). Default: one empty tab 'main'.",
    )


class PostPatch(BaseModel):
    """Fields left out stay as they are. `cover_media_id: null` removes the cover."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", min_length=1, max_length=120)
    summary: str = Field(default="", max_length=300)
    tags: list[str] = Field(default_factory=list)
    cover_media_id: int | None = None
    body: dict[str, object] = Field(
        default_factory=dict, description="Whole block document (see block_schema)."
    )


def _summary_fields(post: BlogPost) -> dict[str, object]:
    return {
        "id": post.pk,
        "slug": post.slug,
        "title": post.title,
        "summary": post.summary,
        "tags": post.tag_list(),
        "status": post.status,
        "published_at": post.published_at,
        "cover_media_id": post.cover_id,
        "url": f"/blog/{post.slug}",
        "updated_at": post.updated_at,
    }


def summary_of(post: BlogPost) -> PostSummary:
    return PostSummary.model_validate(_summary_fields(post))


def post_out(post: BlogPost) -> PostOut:
    return PostOut.model_validate(
        {**_summary_fields(post), "body": post.body, "created_at": post.created_at}
    )


def _published() -> QuerySet[BlogPost]:
    return BlogPost.objects.filter(
        status=BlogPost.Status.PUBLISHED, published_at__isnull=False
    ).order_by("-published_at", "-id")


def _has_tag(post: BlogPost, tag: str) -> bool:
    return tag in post.tag_list()


def _posts(published_only: bool, tag: str) -> list[BlogPost]:
    if published_only:
        query = _published()
    else:  # drafts (no published_at yet) first, then newest publication first
        query = BlogPost.objects.order_by(F("published_at").desc(nulls_first=True), "-id")
    tag = tag.strip()
    if tag:  # the column holds "a, b": narrow in SQL, then match whole tags
        return [p for p in query.filter(tags__contains=tag) if _has_tag(p, tag)]
    return list(query)


def list_posts(
    published_only: bool = True, limit: int | None = None, tag: str = ""
) -> list[PostSummary]:
    """Posts newest publication first; with `published_only=False` drafts come first."""
    posts = _posts(published_only, tag)
    return [summary_of(p) for p in (posts if limit is None else posts[: max(limit, 0)])]


def _post_or_404(slug: str, *, published_only: bool = False) -> BlogPost:
    query = _published() if published_only else BlogPost.objects.all()
    post = query.filter(slug=slug).first()
    if post is None:
        raise NotFound(f"글 {slug!r}이(가) 없습니다")
    return post


def get_post(slug: str, published_only: bool = True) -> PostOut:
    """One post with its body. Publicly only a published one; the owner sees drafts too."""
    return post_out(_post_or_404(slug, published_only=published_only))


def _body(document: object) -> dict[str, JSON]:
    try:
        return stored_document(document)
    except InvalidDocument as exc:
        raise Rejected([DocumentError(f"body.{e.path}", e.reason) for e in exc.errors]) from exc


def slug_base(title: str) -> str:
    """A slug made from the title: its latin letters and digits, or `post-<hex>` when it has
    fewer than three of them (a Korean title)."""
    base = slugify(title)[: SLUG_MAX_LENGTH - _SUFFIX_ROOM].strip("-")
    if len(re.sub(r"[^a-z0-9]", "", base)) < _MIN_LATIN:
        return f"post-{secrets.token_hex(3)}"
    return base


def _free_slug(base: str) -> str:
    taken = set(BlogPost.objects.filter(slug__startswith=base).values_list("slug", flat=True))
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def create_post(new: NewPost) -> PostOut:
    """A new draft. A given slug that is taken is a Conflict; a generated one gets -2, -3..."""
    if new.slug and BlogPost.objects.filter(slug=new.slug).exists():
        raise Conflict(f"주소 {new.slug!r}는 이미 쓰고 있습니다")
    post = BlogPost(
        slug=new.slug or _free_slug(slug_base(new.title)),
        title=new.title,
        summary=new.summary,
        tags=", ".join(clean_tags(new.tags)),
        cover=cover_media(new.cover_media_id),
        body=_body(new.body),
    )
    try:
        with transaction.atomic():
            post.save()
    except IntegrityError:
        raise Conflict(f"주소 {post.slug!r}는 이미 쓰고 있습니다") from None
    return post_out(post)


def update_post(slug: str, patch: PostPatch) -> PostOut:
    """Change the metadata and/or replace the whole document. The slug does not change."""
    post = _post_or_404(slug)
    given = patch.model_fields_set
    if "title" in given:
        post.title = patch.title
    if "summary" in given:
        post.summary = patch.summary
    if "tags" in given:
        post.tags = ", ".join(clean_tags(patch.tags))
    if "cover_media_id" in given:
        post.cover = cover_media(patch.cover_media_id)
    if "body" in given:
        post.body = _body(patch.body)
    post.save()
    return post_out(post)


def _save_body(post: BlogPost) -> PostOut:
    post.body = _body(post.body)
    post.save()
    return post_out(post)


def replace_block(slug: str, block_id: str, block: dict[str, object]) -> PostOut:
    """Swap one block in place. A block without an `id` keeps `block_id`."""
    post = _post_or_404(slug)
    document_edit.replace_block(post.body, block_id, block)
    return _save_body(post)


def insert_block(
    slug: str,
    block: dict[str, object],
    tab_id: str | None = None,
    after_block_id: str | None = None,
) -> PostOut:
    """Add a block at the start of a tab (default: the first tab) or after `after_block_id`."""
    post = _post_or_404(slug)
    tab = tab_id if tab_id is not None else str(document_edit.tabs(post.body)[0]["id"])
    document_edit.insert_block(post.body, tab, block, after_block_id)
    return _save_body(post)


def delete_block(slug: str, block_id: str) -> PostOut:
    post = _post_or_404(slug)
    document_edit.delete_block(post.body, block_id)
    return _save_body(post)


def publish_post(slug: str) -> PostOut:
    """Show the post on /blog. The first publication sets `published_at`; later ones keep it."""
    post = _post_or_404(slug)
    post.status = BlogPost.Status.PUBLISHED
    post.save()  # the model fills published_at the first time
    return post_out(post)


def unpublish_post(slug: str) -> PostOut:
    """Back to draft: gone from /blog, the sitemap and the feed. `published_at` is kept."""
    post = _post_or_404(slug)
    post.status = BlogPost.Status.DRAFT
    post.save()
    return post_out(post)


def delete_post(slug: str) -> None:
    _post_or_404(slug).delete()


# --- public side: published posts only, plain JSON for the shell ---


class PostCard(TypedDict):
    slug: str
    title: str
    summary: str
    cover_url: str
    tags: list[str]
    published_at: str  # ISO 8601


class PostNeighbor(TypedDict):
    slug: str
    title: str


class PostDetail(TypedDict):
    """For /blog/<slug> (#75). `prev` is the post published just before (older), `next` the one
    just after (newer); None at either end."""

    card: PostCard
    body: dict[str, JSON]
    prev: PostNeighbor | None
    next: PostNeighbor | None


class TagCount(TypedDict):
    tag: str
    count: int


def card_of(post: BlogPost) -> PostCard:
    assert post.published_at is not None  # public posts always have it
    return PostCard(
        slug=post.slug,
        title=post.title,
        summary=post.summary,
        cover_url=(media.public_url(post.cover) or "") if post.cover else "",
        tags=post.tag_list(),
        published_at=post.published_at.isoformat(),
    )


def public_cards(limit: int | None = None, tag: str = "") -> list[PostCard]:
    """Published posts, newest first (optionally one tag's, at most `limit`)."""
    tag = tag.strip()
    query = _published().select_related("cover")
    if tag:  # the column holds "a, b": narrow in SQL, then match whole tags
        posts = [p for p in query.filter(tags__contains=tag) if _has_tag(p, tag)]
        posts = posts if limit is None else posts[: max(limit, 0)]
    else:
        posts = list(query if limit is None else query[: max(limit, 0)])
    return [card_of(p) for p in posts]


def _neighbor(post: BlogPost | None) -> PostNeighbor | None:
    return PostNeighbor(slug=post.slug, title=post.title) if post else None


def public_detail(slug: str) -> PostDetail | None:
    post = _published().select_related("cover").filter(slug=slug).first()
    if post is None:
        return None
    at = post.published_at
    older = (
        _published()
        .filter(Q(published_at__lt=at) | Q(published_at=at, id__lt=post.pk))
        .only("slug", "title")
        .first()
    )
    newer = (
        _published()
        .filter(Q(published_at__gt=at) | Q(published_at=at, id__gt=post.pk))
        .order_by("published_at", "id")
        .only("slug", "title")
        .first()
    )
    return PostDetail(
        card=card_of(post),
        body=media.resolve_document(post.body),
        prev=_neighbor(older),
        next=_neighbor(newer),
    )


def public_modified_at(slug: str) -> str | None:
    """When a published post last changed (ISO 8601), for `article:modified_time`/`dateModified`."""
    post = _published().filter(slug=slug).only("updated_at", "published_at").first()
    if post is None or post.published_at is None:
        return None
    return max(post.updated_at, post.published_at).isoformat()


def public_modified_by_slug() -> dict[str, datetime]:
    """slug -> last change of every published post, newest first, for sitemap `lastmod`."""
    rows = _published().values_list("slug", "updated_at", "published_at")
    return {slug: max(updated, published) for slug, updated, published in rows if published}


def public_slugs() -> list[str]:
    return list(_published().values_list("slug", flat=True))


def public_tags() -> list[TagCount]:
    """Tags of published posts with how many posts use each, most used first."""
    counts: dict[str, int] = {}
    for tags in _published().values_list("tags", flat=True):
        for tag in {t.strip() for t in tags.split(",") if t.strip()}:
            counts[tag] = counts.get(tag, 0) + 1
    return [
        TagCount(tag=tag, count=n)
        for tag, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


PAGE_SIZE = 20


class PostListing(TypedDict):
    """For /blog (#75): one page of the newest-first list, the tags to filter by and which one is
    on. Mirrored by frontend/src/blog/types.ts."""

    posts: list[PostCard]
    tags: list[TagCount]
    tag: str  # "" for all posts
    page: int  # 1-based
    pages: int  # at least 1 (an empty list is one empty page)
    total: int


def public_listing(tag: str = "", page: int = 1, per_page: int = PAGE_SIZE) -> PostListing | None:
    """One page of the public list; None when `page` is past the last one (or below 1)."""
    tag = tag.strip()
    cards = public_cards(tag=tag)
    pages = max(1, -(-len(cards) // per_page))
    if not 1 <= page <= pages:
        return None
    start = (page - 1) * per_page
    return PostListing(
        posts=cards[start : start + per_page],
        tags=public_tags(),
        tag=tag,
        page=page,
        pages=pages,
        total=len(cards),
    )


@dataclass(frozen=True)
class FeedItem:
    slug: str
    title: str
    summary: str
    tags: list[str]
    published_at: datetime


def feed_items(limit: int = 30) -> list[FeedItem]:
    """The newest published posts for /blog/feed.xml."""
    return [
        FeedItem(p.slug, p.title, p.summary, p.tag_list(), p.published_at)
        for p in _published()[:limit]
        if p.published_at is not None
    ]

"""MCP tools for the blog 「기록」 (services.blog): thin shells, one service call each."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from sandcorp_authkit.tokens import AccessToken

from mcpserver.tools import SEE_SCHEMA, NoInput, ToolResult, _failure, many, one, tool
from mcpserver.tools_proposals import SkeletonBlock, SkeletonTab
from services import blog
from services.errors import ServiceError

NOT_SAVED = " An invalid input is not saved; the error lists block paths. " + SEE_SCHEMA
MEDIA = (
    " gallery/video blocks and cover_media_id take a media_id from list_media (a finished, "
    "public upload; posts are public pages)."
)


READ_GUIDE = " Before writing or rewriting a post, read blog_guide."

BLOG_GUIDE = Path(__file__).with_name("blog_guide.md").read_text(encoding="utf-8")


class BlogGuide(BaseModel):
    guide: str
    skeleton: list[SkeletonTab]


# The recommended block order of a post's one tab. Types must be block types (tested).
BLOG_SKELETON: list[SkeletonTab] = [
    SkeletonTab(
        tab_id="main",
        title="본문",
        blocks=[
            SkeletonBlock(type=block_type, purpose=purpose)
            for block_type, purpose in (
                ("cover", "표지: 첫 블록"),
                ("markdown", "「왜 만들었나」 (level 2): 무엇을, 왜(제약)"),
                ("gallery", "시연: 본문 앞쪽, 호출 → 결과를 짝으로"),
                ("steps", "구조 (layout horizontal)"),
                ("table", "기능 목록"),
                ("callout", "원칙과 경고"),
                ("markdown", "「부딪힌 문제와 해결」: ### 소제목마다 증상 → 원인 → 해결"),
                ("markdown", "남은 한계"),
            )
        ],
    ),
]


class ListPostsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    published_only: bool = Field(default=False, description="true leaves drafts out.")
    limit: int | None = Field(default=None, ge=1, description="At most this many.")
    tag: str = Field(default="", description="Only posts with this tag.")


class PostSlugInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(description="The post's address (/blog/<slug>); see list_posts.")


class CreatePostInput(blog.NewPost):
    pass


class UpdatePostInput(blog.PostPatch):
    slug: str = Field(description="Which post; the slug itself cannot change.")


class PostBlockIdInput(PostSlugInput):
    block_id: str = Field(description="The block's id inside the post's document.")


class ReplacePostBlockInput(PostBlockIdInput):
    block: dict[str, object] = Field(description="The new block; without an id it keeps block_id.")


class InsertPostBlockInput(PostSlugInput):
    block: dict[str, object]
    tab_id: str | None = Field(default=None, description="Omit for the first tab ('main').")
    after_block_id: str | None = Field(default=None, description="Omit to insert at the tab start.")


@tool(
    "blog_guide",
    "Blog writing guide",
    "Read this first, before writing or rewriting a blog post. Returns `guide` (Korean markdown: "
    "what to write, what must never be published, structure and blocks, images, publishing) and "
    "`skeleton` (the recommended block order of the post's tab as {type, purpose}). Then call "
    "block_schema for the fields of each block.",
    NoInput,
)
def blog_guide(token: AccessToken, args: NoInput) -> ToolResult:
    return BlogGuide(guide=BLOG_GUIDE, skeleton=BLOG_SKELETON).model_dump(mode="json")


@tool(
    "list_posts",
    "List blog posts",
    "Blog posts (/blog), drafts first then newest publication first. No bodies; use get_post.",
    ListPostsInput,
)
def list_posts(token: AccessToken, args: ListPostsInput) -> ToolResult:
    return many(lambda: blog.list_posts(args.published_only, args.limit, args.tag))


@tool(
    "get_post",
    "Get a blog post",
    "One blog post with its body (block document), draft or published.",
    PostSlugInput,
)
def get_post(token: AccessToken, args: PostSlugInput) -> ToolResult:
    return one(lambda: blog.get_post(args.slug, published_only=False))


@tool(
    "create_post",
    "Create a blog post",
    "Start a blog post as a draft (not public until publish_post). Omit slug to make one from "
    "the title. body is a block document (default: one empty tab 'main')."
    + MEDIA
    + READ_GUIDE
    + NOT_SAVED,
    CreatePostInput,
    read_only=False,
)
def create_post(token: AccessToken, args: CreatePostInput) -> ToolResult:
    return one(lambda: blog.create_post(args))


@tool(
    "update_post",
    "Update a blog post",
    "Change a post by slug. Only the fields you send change; body replaces the whole block "
    "document, cover_media_id null removes the cover. A published post changes live."
    + MEDIA
    + READ_GUIDE
    + NOT_SAVED,
    UpdatePostInput,
    read_only=False,
)
def update_post(token: AccessToken, args: UpdatePostInput) -> ToolResult:
    patch = blog.PostPatch.model_validate(args.model_dump(exclude={"slug"}, exclude_unset=True))
    return one(lambda: blog.update_post(args.slug, patch))


@tool(
    "replace_post_block",
    "Replace a block of a blog post",
    "Swap one block of a post by block_id (same position); the rest is untouched."
    + READ_GUIDE
    + NOT_SAVED,
    ReplacePostBlockInput,
    read_only=False,
)
def replace_post_block(token: AccessToken, args: ReplacePostBlockInput) -> ToolResult:
    return one(lambda: blog.replace_block(args.slug, args.block_id, args.block))


@tool(
    "insert_post_block",
    "Insert a block into a blog post",
    "Add a block at the start of a tab (default the first) or right after after_block_id."
    + MEDIA
    + READ_GUIDE
    + NOT_SAVED,
    InsertPostBlockInput,
    read_only=False,
)
def insert_post_block(token: AccessToken, args: InsertPostBlockInput) -> ToolResult:
    return one(lambda: blog.insert_block(args.slug, args.block, args.tab_id, args.after_block_id))


@tool(
    "delete_post_block",
    "Delete a block of a blog post",
    "Remove one block of a post by block_id.",
    PostBlockIdInput,
    read_only=False,
)
def delete_post_block(token: AccessToken, args: PostBlockIdInput) -> ToolResult:
    return one(lambda: blog.delete_block(args.slug, args.block_id))


@tool(
    "issue_post_preview_url",
    "Blog post preview link",
    "A temporary link (path on the site, /preview/blog/...) showing the post, drafts included, "
    "as /blog/<slug> will. Not indexed, not counted as a visit; it expires (see expires_at). "
    "Show a draft through it before publish_post.",
    PostSlugInput,
)
def issue_post_preview_url(token: AccessToken, args: PostSlugInput) -> ToolResult:
    return one(lambda: blog.issue_preview_url(args.slug))


@tool(
    "publish_post",
    "Publish a blog post",
    "Show the post at /blog/<slug>, in the blog list, sitemap and /blog/feed.xml. The first "
    "publication sets published_at; publishing again later keeps it.",
    PostSlugInput,
    read_only=False,
)
def publish_post(token: AccessToken, args: PostSlugInput) -> ToolResult:
    return one(lambda: blog.publish_post(args.slug))


@tool(
    "unpublish_post",
    "Unpublish a blog post",
    "Turn a published post back into a draft: it leaves /blog, the sitemap and the feed at once. "
    "published_at is kept.",
    PostSlugInput,
    read_only=False,
)
def unpublish_post(token: AccessToken, args: PostSlugInput) -> ToolResult:
    return one(lambda: blog.unpublish_post(args.slug))


@tool(
    "delete_post",
    "Delete a blog post",
    "Delete a post for good (draft or published). Cannot be undone; unpublish_post hides one "
    "instead.",
    PostSlugInput,
    read_only=False,
)
def delete_post(token: AccessToken, args: PostSlugInput) -> ToolResult:
    try:
        blog.delete_post(args.slug)
    except ServiceError as exc:
        raise _failure(exc) from exc
    return {"deleted": args.slug}

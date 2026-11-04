"""MCP tools for development tips (/tips, services.tips, issue 203): one service call each."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from sandcorp_authkit.tokens import AccessToken

from content.models import TipCategory
from mcpserver.tools import NoInput, ToolResult, _failure, many, one, tool
from services import tips
from services.errors import ServiceError

READ_GUIDE = " Before writing or rewriting a tip, read tip_guide."

TIP_GUIDE = Path(__file__).with_name("tip_guide.md").read_text(encoding="utf-8")


class CategoryChoice(BaseModel):
    value: str
    label: str


class TipGuide(BaseModel):
    guide: str
    categories: list[CategoryChoice]


class ListTipsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    published_only: bool = Field(default=False, description="true leaves drafts out.")
    limit: int | None = Field(default=None, ge=1, description="At most this many.")
    category: str = Field(default="", description="Only tips in this category (its value).")


class TipSlugInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(description="The tip's address (/tips/<slug>); see list_tips.")


class CreateTipInput(tips.NewTip):
    pass


class UpdateTipInput(tips.TipPatch):
    slug: str = Field(description="Which tip; the slug itself cannot change.")


@tool(
    "tip_guide",
    "Tip writing guide",
    "Read this first, before writing or rewriting a development tip. Returns `guide` (Korean "
    "markdown: what a tip is, what must never be published, the body's shape, publishing) and "
    "`categories` (the fixed choices as {value, label}; tips take the values).",
    NoInput,
)
def tip_guide(token: AccessToken, args: NoInput) -> ToolResult:
    choices = [CategoryChoice(value=c.value, label=c.label) for c in TipCategory]
    return TipGuide(guide=TIP_GUIDE, categories=choices).model_dump(mode="json")


@tool(
    "list_tips",
    "List development tips",
    "Development tips (/tips), drafts first then newest publication first. No bodies; use get_tip.",
    ListTipsInput,
)
def list_tips(token: AccessToken, args: ListTipsInput) -> ToolResult:
    return many(lambda: tips.list_tips(args.published_only, args.limit, args.category))


@tool(
    "get_tip",
    "Get a development tip",
    "One tip with its markdown body, draft or published.",
    TipSlugInput,
)
def get_tip(token: AccessToken, args: TipSlugInput) -> ToolResult:
    return one(lambda: tips.get_tip(args.slug))


@tool(
    "create_tip",
    "Create a development tip",
    "Start a tip as a draft (not public until publish_tip). Omit slug to make one from the "
    "title. body is markdown (fenced code blocks with a language are highlighted)." + READ_GUIDE,
    CreateTipInput,
    read_only=False,
)
def create_tip(token: AccessToken, args: CreateTipInput) -> ToolResult:
    return one(lambda: tips.create_tip(args))


@tool(
    "update_tip",
    "Update a development tip",
    "Change a tip by slug. Only the fields you send change; body replaces the whole markdown, "
    "categories the whole list. A published tip changes live." + READ_GUIDE,
    UpdateTipInput,
    read_only=False,
)
def update_tip(token: AccessToken, args: UpdateTipInput) -> ToolResult:
    patch = tips.TipPatch.model_validate(args.model_dump(exclude={"slug"}, exclude_unset=True))
    return one(lambda: tips.update_tip(args.slug, patch))


@tool(
    "issue_tip_preview_url",
    "Tip preview link",
    "A temporary link (path on the site, /preview/tips/...) showing the tip, drafts included, "
    "as /tips/<slug> will. Not indexed, not counted as a visit; it expires (see expires_at). "
    "Show a draft through it before publish_tip.",
    TipSlugInput,
)
def issue_tip_preview_url(token: AccessToken, args: TipSlugInput) -> ToolResult:
    return one(lambda: tips.issue_preview_url(args.slug))


@tool(
    "publish_tip",
    "Publish a development tip",
    "Show the tip at /tips/<slug>, in the /tips list and the sitemap. The first publication "
    "sets published_at; publishing again later keeps it.",
    TipSlugInput,
    read_only=False,
)
def publish_tip(token: AccessToken, args: TipSlugInput) -> ToolResult:
    return one(lambda: tips.publish_tip(args.slug))


@tool(
    "unpublish_tip",
    "Unpublish a development tip",
    "Turn a published tip back into a draft: it leaves /tips and the sitemap at once. "
    "published_at is kept.",
    TipSlugInput,
    read_only=False,
)
def unpublish_tip(token: AccessToken, args: TipSlugInput) -> ToolResult:
    return one(lambda: tips.unpublish_tip(args.slug))


@tool(
    "delete_tip",
    "Delete a development tip",
    "Delete a tip for good (draft or published). Cannot be undone; unpublish_tip hides one "
    "instead.",
    TipSlugInput,
    read_only=False,
)
def delete_tip(token: AccessToken, args: TipSlugInput) -> ToolResult:
    try:
        tips.delete_tip(args.slug)
    except ServiceError as exc:
        raise _failure(exc) from exc
    return {"deleted": args.slug}

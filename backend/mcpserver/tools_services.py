"""MCP tools for the outsourced-work services (/services/<slug> and the home cards,
services.offerings, issue 215): one service call each. No delete: hide the card instead."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from sandcorp_authkit.tokens import AccessToken

from content.models import Inquiry
from mcpserver.tools import NoInput, ToolResult, many, one, tool
from services import offerings

READ_GUIDE = " Before writing or rewriting a service, read service_guide."

SERVICE_GUIDE = Path(__file__).with_name("service_guide.md").read_text(encoding="utf-8")


class ServiceGuide(BaseModel):
    guide: str
    inquiry_kinds: list[str]


class ServiceSlugInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(description="The service's address (/services/<slug>); see list_services.")


class CreateServiceInput(offerings.NewService):
    pass


class UpdateServiceInput(offerings.ServicePatch):
    slug: str = Field(description="Which service; the slug itself cannot change.")


@tool(
    "service_guide",
    "Service page writing guide",
    "Read this first, before writing or rewriting a service page or card. Returns `guide` "
    "(Korean markdown: the page's sections and how many lines each, what a case may say, price "
    "wording, publishing) and `inquiry_kinds` (the values inquiry_kind accepts).",
    NoInput,
)
def service_guide(token: AccessToken, args: NoInput) -> ToolResult:
    return ServiceGuide(guide=SERVICE_GUIDE, inquiry_kinds=list(Inquiry.Kind.values)).model_dump(
        mode="json"
    )


@tool(
    "list_services",
    "List services",
    "Every service in home card order (position, smaller first), hidden and unpublished ones "
    "included, with has_page (the page answers) and url (where the card links).",
    NoInput,
)
def list_services(token: AccessToken, args: NoInput) -> ToolResult:
    return many(offerings.list_services)


@tool(
    "get_service",
    "Get a service",
    "One service with all its page fields, including the cover and figure (media id, alt, "
    "caption and the url they are drawn from).",
    ServiceSlugInput,
)
def get_service(token: AccessToken, args: ServiceSlugInput) -> ToolResult:
    return one(lambda: offerings.get_service(args.slug))


@tool(
    "create_service",
    "Create a service",
    "Add a service, hidden (no home card) and unpublished (no page). Show its card with "
    "update_service is_visible, open its page with publish_service. cover_media_id and "
    "figure_media_id (finished public images) may be given at once." + READ_GUIDE,
    CreateServiceInput,
    read_only=False,
)
def create_service(token: AccessToken, args: CreateServiceInput) -> ToolResult:
    return one(lambda: offerings.create_service(args))


@tool(
    "update_service",
    "Update a service",
    "Change a service by slug. Only the fields you send change; a list replaces the whole list. "
    "is_visible shows or hides the home card, position orders the cards (smaller first). A "
    "published page changes live. Images: cover_media_id (under the title, cropped into the "
    "home card, the link preview) and figure_media_id (between 02 What and 03 Process, needs "
    "figure_alt) take a finished public image from start_upload/complete_upload; null removes."
    + READ_GUIDE,
    UpdateServiceInput,
    read_only=False,
)
def update_service(token: AccessToken, args: UpdateServiceInput) -> ToolResult:
    patch = offerings.ServicePatch.model_validate(
        args.model_dump(exclude={"slug"}, exclude_unset=True)
    )
    return one(lambda: offerings.update_service(args.slug, patch))


@tool(
    "issue_service_preview_url",
    "Service page preview link",
    "A temporary link (path on the site, /preview/services/...) showing the page, published or "
    "not, as /services/<slug> will. Not indexed, not counted as a visit; it expires (see "
    "expires_at). Needs a lead. Show the page through it before publish_service.",
    ServiceSlugInput,
)
def issue_service_preview_url(token: AccessToken, args: ServiceSlugInput) -> ToolResult:
    return one(lambda: offerings.issue_preview_url(args.slug))


@tool(
    "publish_service",
    "Publish a service page",
    "Open /services/<slug>, add it to the sitemap and point the home card at it. Refused while "
    "lead, audience, deliverables, steps or contact is empty.",
    ServiceSlugInput,
    read_only=False,
)
def publish_service(token: AccessToken, args: ServiceSlugInput) -> ToolResult:
    return one(lambda: offerings.publish_service(args.slug))


@tool(
    "unpublish_service",
    "Unpublish a service page",
    "Close /services/<slug> at once (404, out of the sitemap); the home card, if shown, goes "
    "back to opening the inquiry form.",
    ServiceSlugInput,
    read_only=False,
)
def unpublish_service(token: AccessToken, args: ServiceSlugInput) -> ToolResult:
    return one(lambda: offerings.unpublish_service(args.slug))

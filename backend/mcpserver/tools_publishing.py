"""MCP tools for publishing, PDFs, inquiries and view events (thin shells over services)."""

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from documents.validation import JSON
from mcpserver.tools import SlugInput, ToolResult, _failure, many, one, tool
from oauth.tokens import AccessToken
from services import inquiries, pdf, proposal_events, publishing
from services.errors import ServiceError

CODE_NOTE = (
    " The access code is in this response only (never stored in readable form, never in "
    "revisions): give it to the customer separately, not inside the proposal."
)


CHOOSE_NOTE = (
    " Optional access_code: a code you choose for the customer (4-32 characters; letters in any "
    "language such as Korean, digits, hyphen, underscore, spaces; no same-character repeats, "
    "runs like 1234 or abcd, common values like password/0000/admin/test, or the proposal slug "
    "or client code). Leave it out to get a generated 8-character code."
)


class PublishInput(SlugInput):
    access_code: str | None = Field(
        default=None,
        description="Your own access code (4-32 characters); empty to generate one.",
    )


class RevisionInput(SlugInput):
    number: int = Field(description="Revision number; see list_revisions.")


class PdfInput(SlugInput):
    number: int | None = Field(default=None, description="Revision number; default the latest.")


class ListInquiriesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unhandled_only: bool = False
    limit: int = Field(default=50, ge=1, le=500)


class InquiryIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inquiry_id: int


class EventsInput(SlugInput):
    limit: int = Field(default=200, ge=1, le=1000, description="The latest N events.")


@tool(
    "publish",
    "Publish a proposal",
    "Freeze the working draft as the next revision (v1, v2, ...) and show it to the customer at "
    "/p/<slug> now; a PDF is made in the background. The first publication returns access_code "
    "once; later ones return null (the customer keeps theirs)." + CODE_NOTE + CHOOSE_NOTE,
    PublishInput,
    read_only=False,
)
def publish(token: AccessToken, args: PublishInput) -> ToolResult:
    return one(lambda: publishing.publish(args.slug, args.access_code))


@tool(
    "reissue_access_code",
    "Reissue the access code",
    "Replace the customer's access code (the old one stops working). Use when it was lost or "
    "leaked." + CODE_NOTE + CHOOSE_NOTE,
    PublishInput,
    read_only=False,
)
def reissue_access_code(token: AccessToken, args: PublishInput) -> ToolResult:
    return one(lambda: publishing.reissue_access_code(args.slug, args.access_code))


@tool(
    "revoke",
    "Revoke a proposal",
    "Take a published proposal back for good: its page answers as if it never existed. To "
    "revise it, duplicate_proposal and publish the copy.",
    SlugInput,
    read_only=False,
)
def revoke(token: AccessToken, args: SlugInput) -> ToolResult:
    return one(lambda: publishing.revoke(args.slug))


@tool(
    "list_revisions",
    "List revisions",
    "A proposal's published revisions, newest first (number, document number, dates).",
    SlugInput,
)
def list_revisions(token: AccessToken, args: SlugInput) -> ToolResult:
    return many(lambda: publishing.list_revisions(args.slug))


@tool(
    "get_revision",
    "Get a revision",
    "One published revision with its frozen document. Never includes the access code.",
    RevisionInput,
)
def get_revision(token: AccessToken, args: RevisionInput) -> ToolResult:
    return one(lambda: publishing.get_revision(args.slug, args.number))


@tool(
    "pdf_status",
    "PDF status",
    "State of a revision's PDF: pending, running, done or failed (with the error).",
    PdfInput,
)
def pdf_status(token: AccessToken, args: PdfInput) -> ToolResult:
    return one(lambda: pdf.pdf_status(args.slug, args.number))


@tool(
    "retry_pdf",
    "Retry the PDF",
    "Make a revision's PDF again from scratch (after a failure, or for a revision published "
    "before PDFs existed). A running job is refused. Check pdf_status afterwards.",
    PdfInput,
    read_only=False,
)
def retry_pdf(token: AccessToken, args: PdfInput) -> ToolResult:
    return one(lambda: pdf.retry_revision(args.slug, args.number))


@tool(
    "list_inquiries",
    "List inquiries",
    "Inquiries from visitors, newest first, with site and kind (문의/…). unhandled_only hides "
    "the ones already marked handled.",
    ListInquiriesInput,
)
def list_inquiries(token: AccessToken, args: ListInquiriesInput) -> ToolResult:
    return many(
        lambda: inquiries.list_inquiries(unhandled_only=args.unhandled_only, limit=args.limit)
    )


@tool(
    "mark_inquiry_handled",
    "Mark an inquiry handled",
    "Record that an inquiry was dealt with (idempotent: keeps the first handled time).",
    InquiryIdInput,
    read_only=False,
)
def mark_inquiry_handled(token: AccessToken, args: InquiryIdInput) -> ToolResult:
    return one(lambda: inquiries.mark_handled(args.inquiry_id))


@tool(
    "list_proposal_events",
    "Customer view events",
    "What the customer did on a proposal, oldest first among the latest `limit`: first view, "
    "tab switches, PDF downloads, blocked attempts (with revision, time, IP).",
    EventsInput,
)
def list_proposal_events(token: AccessToken, args: EventsInput) -> ToolResult:
    try:
        rows = proposal_events.list_events(args.slug, args.limit)
    except ServiceError as exc:
        raise _failure(exc) from exc
    items: JSON = TypeAdapter(list[proposal_events.EventOut]).dump_python(rows, mode="json")
    return {"items": items}

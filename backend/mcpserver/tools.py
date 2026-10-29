"""MCP tools: thin shells over `services/`. A tool validates its input and shapes its output.

Add a tool with `@tool(name, title, description, InputModel)` on a function
`(token: AccessToken, args: InputModel) -> dict[str, JSON]` (`read_only=False` for tools that
write). The input model (Pydantic,
`extra="forbid"`) becomes the tool's `inputSchema`; raise `ToolError` for a failure the caller
should read (it becomes an `isError` result, not a protocol error).
Every tool runs behind the `/mcp` bearer check (scope `admin`), so it always has a token.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field
from sandcorp_authkit.tokens import AccessToken

from documents.validation import BLOCK_TYPES, JSON
from services import blocks, portfolio, profile
from services.errors import Conflict, NotFound, Rejected, ServiceError

type ToolResult = dict[str, JSON]


class ToolError(Exception):
    """A tool-level failure; the message is shown to the MCP client."""


class RegisteredTool(Protocol):
    @property
    def name(self) -> str: ...

    def definition(self) -> dict[str, JSON]: ...

    def call(self, token: AccessToken, arguments: dict[str, JSON]) -> ToolResult: ...


@dataclass(frozen=True)
class Tool[M: BaseModel]:
    name: str
    title: str
    description: str
    input_model: type[M]
    handler: Callable[[AccessToken, M], ToolResult]
    read_only: bool = True

    def definition(self) -> dict[str, JSON]:
        schema: dict[str, JSON] = self.input_model.model_json_schema()
        schema.pop("title", None)
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": schema,
            "annotations": {"readOnlyHint": self.read_only},
        }

    def call(self, token: AccessToken, arguments: dict[str, JSON]) -> ToolResult:
        return self.handler(token, self.input_model.model_validate(arguments))


TOOLS: dict[str, RegisteredTool] = {}


def tool[M: BaseModel](
    name: str, title: str, description: str, input_model: type[M], *, read_only: bool = True
) -> Callable[[Callable[[AccessToken, M], ToolResult]], Callable[[AccessToken, M], ToolResult]]:
    def register(
        handler: Callable[[AccessToken, M], ToolResult],
    ) -> Callable[[AccessToken, M], ToolResult]:
        if name in TOOLS:
            raise ValueError(f"MCP tool {name!r} is registered twice")
        TOOLS[name] = Tool(name, title, description, input_model, handler, read_only)
        return handler

    return register


class NoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BlockSchemaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str | None = Field(
        default=None,
        description="Block type to describe; omit to list every type. One of: "
        + ", ".join(sorted(BLOCK_TYPES)),
    )


@tool(
    "whoami",
    "Who am I",
    "The identity this connection acts as: the token's subject, client and scopes. Writing a "
    "proposal: proposal_guide (read it first) -> block_schema -> list_clients/create_client -> "
    "create_proposal -> replace_block/insert_block/add_tab -> issue_preview_url (look at it) -> "
    "publish (the access code is shown once; give it to the customer separately). Writing a blog "
    "post: blog_guide (read it first) -> block_schema -> create_post -> replace_post_block/"
    "insert_post_block (gallery/video take list_media ids) -> get_post (read it back) -> "
    "issue_post_preview_url (show the draft) -> publish_post.",
    NoInput,
)
def whoami(token: AccessToken, args: NoInput) -> ToolResult:
    return {
        "sub": token.sub,
        "client_id": token.client_id,
        "scopes": [scope for scope in sorted(token.scopes)],
        "expires_at": token.exp,
    }


@tool(
    "block_schema",
    "Block schema",
    "JSON Schema and a valid example for a block type of the block document (portfolio items "
    "and proposals are tabs of these blocks). Without `type`: every block type with a one-line "
    "description, plus the whole document schema.",
    BlockSchemaInput,
)
def block_schema(token: AccessToken, args: BlockSchemaInput) -> ToolResult:
    if args.type is None:
        return {
            "block_types": [
                {"type": summary["type"], "description": summary["description"]}
                for summary in blocks.block_types()
            ],
            "document_schema": blocks.document_schema(),
        }
    try:
        found = blocks.block_schema(args.type)
    except blocks.UnknownBlockType as exc:
        known = ", ".join(sorted(BLOCK_TYPES))
        raise ToolError(f"unknown block type {exc.block_type!r}; known types: {known}") from exc
    return {
        "type": found["type"],
        "description": found["description"],
        "schema": found["schema"],
        "example": found["example"],
    }


# --- site content: profile and portfolio (same service functions as the /api/admin routes) ---

SEE_SCHEMA = "Document fields are block documents: call block_schema first."


def _failure(exc: ServiceError) -> ToolError:
    """A refused write: nothing was saved. Block-path errors become one line each."""
    if isinstance(exc, Rejected):
        return ToolError(
            "저장하지 않았습니다. 고칠 곳:\n" + "\n".join(f"- {line}" for line in exc.lines())
        )
    if isinstance(exc, (NotFound, Conflict)):
        return ToolError(str(exc))
    return ToolError(f"{type(exc).__name__}: {exc}")


def one(call: Callable[[], BaseModel]) -> ToolResult:
    """Run a service call returning a model; a refusal becomes the tool's error."""
    try:
        return call().model_dump(mode="json")
    except ServiceError as exc:
        raise _failure(exc) from exc


def many(call: Callable[[], Sequence[BaseModel]]) -> ToolResult:
    """Like `one` for a list: `{"items": [...]}`."""
    try:
        return {"items": [row.model_dump(mode="json") for row in call()]}
    except ServiceError as exc:
        raise _failure(exc) from exc


class SlugInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(description="The item's address (/work/<slug>); see list_portfolio.")


class CreateInput(portfolio.NewItem):
    pass


class UpdateInput(portfolio.ItemPatch):
    slug: str = Field(
        description="Which item to change; to rename it send new_slug (old address redirects)."
    )


class ReorderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slugs: list[str] = Field(description="Every item's slug exactly once, in the new order.")


class VisibilityInput(SlugInput):
    is_public: bool = Field(description="true shows it on the home page, /work/<slug> and sitemap.")


@tool(
    "get_profile",
    "Get site profile",
    "The home page profile: tagline, contact fields, availability (the masthead's "
    '"새 프로젝트 받는 중" and its date), career_started_on and response_promise (the home '
    "evidence row), business_name / representative / business_number (the public footer, "
    "which also shows address) and the two block documents (company_intro, ceo_intro).",
    NoInput,
)
def get_profile(token: AccessToken, args: NoInput) -> ToolResult:
    return profile.get_profile().model_dump(mode="json")


@tool(
    "update_profile",
    "Update site profile",
    'Change the home page profile now (live at /). Only the fields you send change; send "" to '
    "clear a text field. company_intro and ceo_intro replace the whole document. "
    + SEE_SCHEMA
    + " An invalid document is not saved; the error lists block paths.",
    profile.ProfilePatch,
    read_only=False,
)
def update_profile(token: AccessToken, args: profile.ProfilePatch) -> ToolResult:
    try:
        return profile.update_profile(args).model_dump(mode="json")
    except ServiceError as exc:
        raise _failure(exc) from exc


@tool(
    "list_portfolio",
    "List portfolio items",
    "Every portfolio item in display order, hidden ones included (is_public tells which are "
    "live). No bodies; use get_portfolio for one.",
    NoInput,
)
def list_portfolio(token: AccessToken, args: NoInput) -> ToolResult:
    return {"items": [item.model_dump(mode="json") for item in portfolio.list_summaries()]}


@tool(
    "get_portfolio",
    "Get a portfolio item",
    "One portfolio item with its body (block document), hidden or not.",
    SlugInput,
)
def get_portfolio(token: AccessToken, args: SlugInput) -> ToolResult:
    try:
        return portfolio.read_item(args.slug).model_dump(mode="json")
    except ServiceError as exc:
        raise _failure(exc) from exc


@tool(
    "create_portfolio",
    "Create a portfolio item",
    "Add a portfolio item at the end of the list. It starts hidden: pass is_public=true or call "
    "set_portfolio_visibility to publish. body is a block document (default: one empty tab). "
    + SEE_SCHEMA
    + " cover_media_id must be a finished, public upload. An invalid input is not saved.",
    CreateInput,
    read_only=False,
)
def create_portfolio(token: AccessToken, args: CreateInput) -> ToolResult:
    try:
        return portfolio.create_item(args).model_dump(mode="json")
    except ServiceError as exc:
        raise _failure(exc) from exc


@tool(
    "update_portfolio",
    "Update a portfolio item",
    "Change an item by slug. Only the fields you send change; body replaces the whole block "
    "document, cover_media_id null removes the cover, new_slug changes the address "
    "(the old /work/<slug> keeps working as a 301 redirect). " + SEE_SCHEMA,
    UpdateInput,
    read_only=False,
)
def update_portfolio(token: AccessToken, args: UpdateInput) -> ToolResult:
    patch = portfolio.ItemPatch.model_validate(
        args.model_dump(exclude={"slug"}, exclude_unset=True)
    )
    try:
        return portfolio.update_item(args.slug, patch).model_dump(mode="json")
    except ServiceError as exc:
        raise _failure(exc) from exc


@tool(
    "reorder_portfolio",
    "Reorder portfolio items",
    "Set the display order. Pass every slug (hidden ones too, see list_portfolio) exactly once.",
    ReorderInput,
    read_only=False,
)
def reorder_portfolio(token: AccessToken, args: ReorderInput) -> ToolResult:
    try:
        items = portfolio.reorder(args.slugs)
    except ServiceError as exc:
        raise _failure(exc) from exc
    return {"items": [item.model_dump(mode="json") for item in items]}


@tool(
    "set_portfolio_visibility",
    "Show or hide a portfolio item",
    "Publish (is_public=true) or hide an item. Hidden items keep their data and disappear from "
    "the home page, /work/<slug> and the sitemap at once.",
    VisibilityInput,
    read_only=False,
)
def set_portfolio_visibility(token: AccessToken, args: VisibilityInput) -> ToolResult:
    try:
        return portfolio.set_visibility(args.slug, args.is_public).model_dump(mode="json")
    except ServiceError as exc:
        raise _failure(exc) from exc

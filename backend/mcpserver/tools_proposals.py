"""MCP tools for clients and proposal drafts (services.proposals): thin shells."""

from pydantic import BaseModel, ConfigDict, Field

from mcpserver.tools import SEE_SCHEMA, NoInput, SlugInput, ToolResult, many, one, tool
from oauth.tokens import AccessToken
from services import proposals


class ClientCodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_code: str | None = Field(
        default=None, description="Only this client's; see list_clients."
    )


class UpdateClientInput(proposals.ClientPatch):
    code: str = Field(description="Which client; the code itself cannot change.")


class UpdateProposalInput(proposals.ProposalPatch):
    slug: str = Field(description="Which proposal; see list_proposals.")


class DuplicateInput(SlugInput):
    client_code: str | None = Field(default=None, description="Copy to this client; default same.")


class ReplaceDocumentInput(SlugInput):
    document: dict[str, object] = Field(description="The whole block document ({tabs: [...]}).")


class BlockIdInput(SlugInput):
    block_id: str = Field(description="The block's id inside the proposal document.")


class ReplaceBlockInput(BlockIdInput):
    block: dict[str, object] = Field(description="The new block; without an id it keeps block_id.")


class InsertBlockInput(SlugInput):
    tab_id: str
    block: dict[str, object]
    after_block_id: str | None = Field(default=None, description="Omit to insert at the tab start.")


class AddTabInput(SlugInput):
    title: str
    tab_id: str | None = Field(default=None, description="Generated when omitted.")


class TabIdInput(SlugInput):
    tab_id: str


class RenameTabInput(TabIdInput):
    title: str


class ReorderTabsInput(SlugInput):
    tab_ids: list[str] = Field(description="Every tab id exactly once, in the new order.")


NOT_SAVED = " An invalid input is not saved; the error lists block paths. " + SEE_SCHEMA


@tool("list_clients", "List clients", "Every client: code, name, contact title, memo.", NoInput)
def list_clients(token: AccessToken, args: NoInput) -> ToolResult:
    return many(proposals.list_clients)


@tool(
    "create_client",
    "Create a client",
    "Add a customer to write proposals for. code is 2-6 uppercase letters and unique (it shows "
    "in document numbers).",
    proposals.NewClient,
    read_only=False,
)
def create_client(token: AccessToken, args: proposals.NewClient) -> ToolResult:
    return one(lambda: proposals.create_client(args))


@tool(
    "update_client",
    "Update a client",
    "Change a client by code. Only the fields you send change; the code never changes.",
    UpdateClientInput,
    read_only=False,
)
def update_client(token: AccessToken, args: UpdateClientInput) -> ToolResult:
    patch = proposals.ClientPatch.model_validate(
        args.model_dump(exclude={"code"}, exclude_unset=True)
    )
    return one(lambda: proposals.update_client(args.code, patch))


@tool(
    "list_proposals",
    "List proposals",
    "Proposals newest first (no documents): slug, client, title, dates, status "
    "(draft/published/revoked). Optionally one client's.",
    ClientCodeInput,
)
def list_proposals(token: AccessToken, args: ClientCodeInput) -> ToolResult:
    return many(lambda: proposals.list_proposals(args.client_code))


@tool(
    "get_proposal",
    "Get a proposal",
    "One proposal with its working document (block document with tabs and block ids).",
    SlugInput,
)
def get_proposal(token: AccessToken, args: SlugInput) -> ToolResult:
    return one(lambda: proposals.get_proposal(args.slug))


@tool(
    "create_proposal",
    "Create a proposal draft",
    "New draft for a client. Without `document` it starts with the tabs 견적 제안 and "
    "회사소개·수행사례. Not visible to the customer until publish." + NOT_SAVED,
    proposals.NewProposal,
    read_only=False,
)
def create_proposal(token: AccessToken, args: proposals.NewProposal) -> ToolResult:
    return one(lambda: proposals.create_proposal(args))


@tool(
    "duplicate_proposal",
    "Duplicate a proposal",
    "Copy a proposal's working document into a new draft (a new slug), optionally for another "
    "client. Also the way to revise a revoked proposal.",
    DuplicateInput,
    read_only=False,
)
def duplicate_proposal(token: AccessToken, args: DuplicateInput) -> ToolResult:
    return one(lambda: proposals.duplicate_proposal(args.slug, args.client_code))


@tool(
    "update_proposal",
    "Update proposal details",
    "Change title, subtitle, quote_date or valid_until (null clears it) by slug; the document "
    "has its own tools. Only the fields you send change.",
    UpdateProposalInput,
    read_only=False,
)
def update_proposal(token: AccessToken, args: UpdateProposalInput) -> ToolResult:
    patch = proposals.ProposalPatch.model_validate(
        args.model_dump(exclude={"slug"}, exclude_unset=True)
    )
    return one(lambda: proposals.update_proposal(args.slug, patch))


@tool(
    "replace_document",
    "Replace the whole document",
    "Replace a proposal's entire block document (all tabs). Prefer replace_block for small "
    "edits." + NOT_SAVED,
    ReplaceDocumentInput,
    read_only=False,
)
def replace_document(token: AccessToken, args: ReplaceDocumentInput) -> ToolResult:
    return one(lambda: proposals.replace_document(args.slug, args.document))


@tool(
    "replace_block",
    "Replace one block",
    "Swap one block in place by its id (same position)." + NOT_SAVED,
    ReplaceBlockInput,
    read_only=False,
)
def replace_block(token: AccessToken, args: ReplaceBlockInput) -> ToolResult:
    return one(lambda: proposals.replace_block(args.slug, args.block_id, args.block))


@tool(
    "insert_block",
    "Insert a block",
    "Add a block to a tab: at its start, or right after after_block_id. The block needs a "
    "unique id." + NOT_SAVED,
    InsertBlockInput,
    read_only=False,
)
def insert_block(token: AccessToken, args: InsertBlockInput) -> ToolResult:
    return one(
        lambda: proposals.insert_block(args.slug, args.tab_id, args.block, args.after_block_id)
    )


@tool(
    "delete_block",
    "Delete a block",
    "Remove a block by id.",
    BlockIdInput,
    read_only=False,
)
def delete_block(token: AccessToken, args: BlockIdInput) -> ToolResult:
    return one(lambda: proposals.delete_block(args.slug, args.block_id))


@tool(
    "add_tab",
    "Add a tab",
    "Append an empty tab to the proposal; its id is generated unless given.",
    AddTabInput,
    read_only=False,
)
def add_tab(token: AccessToken, args: AddTabInput) -> ToolResult:
    return one(lambda: proposals.add_tab(args.slug, args.title, args.tab_id))


@tool(
    "delete_tab",
    "Delete a tab",
    "Remove a tab and its blocks (the last tab cannot go).",
    TabIdInput,
    read_only=False,
)
def delete_tab(token: AccessToken, args: TabIdInput) -> ToolResult:
    return one(lambda: proposals.delete_tab(args.slug, args.tab_id))


@tool("rename_tab", "Rename a tab", "Change a tab's title.", RenameTabInput, read_only=False)
def rename_tab(token: AccessToken, args: RenameTabInput) -> ToolResult:
    return one(lambda: proposals.rename_tab(args.slug, args.tab_id, args.title))


@tool(
    "reorder_tabs",
    "Reorder tabs",
    "Set the tab order: every tab id exactly once.",
    ReorderTabsInput,
    read_only=False,
)
def reorder_tabs(token: AccessToken, args: ReorderTabsInput) -> ToolResult:
    return one(lambda: proposals.reorder_tabs(args.slug, args.tab_ids))


@tool(
    "issue_preview_url",
    "Preview link",
    "A temporary link (path on the site) showing the working draft as the customer will see "
    "it, drafts included. Open it before publish.",
    SlugInput,
)
def issue_preview_url(token: AccessToken, args: SlugInput) -> ToolResult:
    return one(lambda: proposals.issue_preview_url(args.slug))

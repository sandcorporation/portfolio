"""MCP tools for clients and proposal drafts (services.proposals): thin shells."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from sandcorp_authkit.tokens import AccessToken

from mcpserver.tools import SEE_SCHEMA, NoInput, SlugInput, ToolResult, many, one, tool
from services import pdf, proposals


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
READ_GUIDE = " Before writing a proposal, read proposal_guide."

PROPOSAL_GUIDE = Path(__file__).with_name("proposal_guide.md").read_text(encoding="utf-8")


class SkeletonBlock(BaseModel):
    type: str
    purpose: str


class SkeletonTab(BaseModel):
    tab_id: str
    title: str
    blocks: list[SkeletonBlock]


class ProposalGuide(BaseModel):
    guide: str
    skeleton: list[SkeletonTab]


def _blocks(*pairs: tuple[str, str]) -> list[SkeletonBlock]:
    return [SkeletonBlock(type=block_type, purpose=purpose) for block_type, purpose in pairs]


# The recommended order of blocks in the two default tabs. Types must be block types (tested).
PROPOSAL_SKELETON: list[SkeletonTab] = [
    SkeletonTab(
        tab_id="estimate",
        title="견적 제안",
        blocks=_blocks(
            ("cover", "표지: recipient는 담당자 실명·직함"),
            ("kpi", "견적 개요 3칸: 총액, 기간, 납품·처리 방식"),
            ("markdown", "머리말 한 문단; 요청문이 있으면 「이렇게 이해했습니다」와 핵심 요구"),
            ("callout", "kind warning: 제안을 가르는 제약 조건(보안·데이터·법규), 있을 때만"),
            ("table", "견적 금액: unit에 단위·부가세, 제안안 열은 highlight_column"),
            ("markdown", "총액 요약 한 문단: 구성식 A + B + C = 총액"),
            ("markdown", "운영비: 월 비용과 전제"),
            ("markdown", "비교용 비용: 참고안·기성 서비스, 확정 견적이 아님을 밝힘"),
            ("details", "비교용 비용의 요금 출처·계산식"),
            ("table", "납품 범위: 번호 붙은 제목"),
            ("gallery", "설명용 시안: 시스템 구성도(caption에 「설명용 시안 — 실제 화면 아님」)"),
            ("gallery", "설명용 시안: 핵심 화면 설계, 필요할 때만"),
            ("callout", "kind condition: 적용 조건, 산정 기준과 바뀌면 하는 일"),
            ("markdown", "근거 섹션 머리: 실제로 있는 시험·화면만"),
            ("audio-compare", "근거: 원본과 결과를 들어 비교, 자료가 있을 때만"),
            ("gallery", "근거: 화면, 자료가 있을 때만"),
            ("video", "근거: 시연 영상, 자료가 있을 때만"),
            ("details", "근거: 시험 조건·기록, 결론은 본문에 한두 문장"),
            ("table", "개발비 내역"),
            ("table", "개발 일정"),
            ("gallery", "설명용 시안: 일정 도식, 숫자는 위 표와 같게"),
            ("table", "사전시험 비용: 시험 후 종료 / 본개발 진행 때의 포함 관계"),
            ("table", "선택 항목: 신청하지 않아도 기본 시스템을 쓸 수 있음"),
            ("markdown", "비교 자료: 유사 사례·공개 예산과 출처"),
            ("table", "비교 자료 표"),
            ("markdown", "개발사 소개 한 문단"),
            ("cta", "사례 탭으로 가기 (target kind tab, tab_id company)"),
        ),
    ),
    SkeletonTab(
        tab_id="company",
        title="회사소개·수행사례",
        blocks=_blocks(
            ("markdown", "회사 소개 (create_proposal이 사이트 프로필에서 복사해 둠)"),
            ("markdown", "사례마다: 이탤릭 한 줄 맥락 → 한 일 → 「이번 개발과의 관련성」"),
            ("callout", "kind info: 팀 작업과 섞인 담당 범위, 필요할 때만"),
            ("gallery", "사례 화면: caption에 보이는 것, 실데이터 여부"),
            ("video", "사례 영상: caption에 길이·제작 방식"),
            ("details", "사례의 설계 자료·기록"),
            ("steps", "진행 방식"),
            ("case-ref", "수행사례 카드: highlight에 이번 제안과 이어지는 한 문장"),
            ("cta", "견적서로 돌아가기 (target kind tab, tab_id estimate)"),
        ),
    ),
]


@tool(
    "proposal_guide",
    "Proposal writing guide",
    "Read this first, before writing or rewriting a proposal. Returns `guide` (Korean markdown: "
    "what to check first, the estimate and case tab structure, number sourcing, caveats, tone, "
    "the pre-publish checklist) and `skeleton` (the recommended block order of each tab as "
    "{type, purpose}). Then call block_schema for the fields of each block.",
    NoInput,
)
def proposal_guide(token: AccessToken, args: NoInput) -> ToolResult:
    return ProposalGuide(guide=PROPOSAL_GUIDE, skeleton=PROPOSAL_SKELETON).model_dump(mode="json")


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
    "회사소개·수행사례. Not visible to the customer until publish." + READ_GUIDE + NOT_SAVED,
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
    "Change title, subtitle, quote_date, valid_until (null clears it) or platform_mode (외주 "
    "플랫폼 제출용: hides our company name, contacts and sandcorp addresses) by slug; the "
    "document has its own tools. Only the fields you send change.",
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
    "edits." + READ_GUIDE + NOT_SAVED,
    ReplaceDocumentInput,
    read_only=False,
)
def replace_document(token: AccessToken, args: ReplaceDocumentInput) -> ToolResult:
    return one(lambda: proposals.replace_document(args.slug, args.document))


@tool(
    "replace_block",
    "Replace one block",
    "Swap one block in place by its id (same position)." + READ_GUIDE + NOT_SAVED,
    ReplaceBlockInput,
    read_only=False,
)
def replace_block(token: AccessToken, args: ReplaceBlockInput) -> ToolResult:
    return one(lambda: proposals.replace_block(args.slug, args.block_id, args.block))


@tool(
    "insert_block",
    "Insert a block",
    "Add a block to a tab: at its start, or right after after_block_id. The block needs a "
    "unique id." + READ_GUIDE + NOT_SAVED,
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


class ExportPdfInput(SlugInput):
    platform_mode: bool | None = Field(
        default=None,
        description="Override the proposal's platform_mode for this PDF only (the setting is not "
        "changed); omit to use the proposal's own.",
    )


@tool(
    "export_proposal_pdf",
    "Export a proposal as PDF",
    "Render the proposal's current working document (draft or published) as an A4 PDF now and "
    "return a 10-minute download url with expires_at. With platform_mode (외주 플랫폼 제출용, "
    "위시켓·크몽) the PDF has no company name, contacts or sandcorp addresses from the server; "
    "`leaks` lists text in the document that still names us or carries an email / phone number "
    "— fix those blocks until it is empty. Takes up to about a minute.",
    ExportPdfInput,
    read_only=False,
)
def export_proposal_pdf(token: AccessToken, args: ExportPdfInput) -> ToolResult:
    return one(lambda: pdf.export_draft(args.slug, args.platform_mode))

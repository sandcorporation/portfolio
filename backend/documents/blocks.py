"""Block document schema: the single source of truth for every block type.

The JSON Schema in /schema/document.schema.json and the frontend types in
frontend/src/blocks/types.gen.ts are generated from these models (`make gen`).
To add a block type, follow frontend/src/blocks/README.md.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from documents.sanitize import sanitize_html

BlockId = Annotated[
    str,
    Field(
        pattern=r"^[A-Za-z0-9_-]{1,64}$",
        description="Unique within the document. Partial edits address blocks by this id.",
    ),
]

# A problem a block finds in itself after its fields parse: (path inside the block, reason).
# The path is relative to the block, e.g. "rows[2]".
Problem = tuple[str, str]


class BlockBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: BlockId

    def problems(self) -> list[Problem]:
        """Cross-field checks that a field type alone cannot express. Empty when valid."""
        return []

    def document_problems(
        self, tab_ids: frozenset[str], block_ids: frozenset[str]
    ) -> list[Problem]:
        """Checks that need the whole document (ids of every tab and block). Empty when valid."""
        return []


class CoverBlock(BlockBase):
    """Opening of a document: who it is for, its title and a short subtitle."""

    model_config = ConfigDict(title="CoverBlock")

    type: Literal["cover"]
    recipient: str | None = Field(default=None, description="받는 사람, e.g. '홍길순 대표님께'")
    title: str = Field(min_length=1)
    subtitle: str | None = None


class KpiItem(BaseModel):
    model_config = ConfigDict(extra="forbid", title="KpiItem")

    label: str = Field(min_length=1)
    value: str = Field(min_length=1, description="Shown as written, e.g. '5,950만원'")
    note: str | None = Field(default=None, description="보조 문구 under the value")


class KpiBlock(BlockBase):
    """Two to four headline figures shown as cards."""

    model_config = ConfigDict(title="KpiBlock")

    type: Literal["kpi"]
    title: str | None = Field(default=None, description="Listed in the table of contents")
    items: list[KpiItem] = Field(min_length=2, max_length=4)


class MarkdownBlock(BlockBase):
    """Prose. Its title (with a heading level) is what the table of contents is built from."""

    model_config = ConfigDict(title="MarkdownBlock")

    type: Literal["markdown"]
    title: str | None = Field(default=None, description="Section heading, listed in the TOC")
    level: Literal[2, 3] = Field(default=2, description="Heading level of the title")
    body: str = Field(default="", description="Markdown (GFM). Raw HTML is not rendered.")


class TableBlock(BlockBase):
    """A header row and data rows, with an optional highlighted column, unit and footnotes."""

    model_config = ConfigDict(title="TableBlock")

    type: Literal["table"]
    title: str | None = Field(default=None, description="Listed in the table of contents")
    columns: list[str] = Field(min_length=1, description="Header row")
    rows: list[list[str]] = Field(description="Each row has exactly one cell per column")
    highlight_column: int | None = Field(
        default=None, ge=0, description="Zero-based index of the emphasised column"
    )
    unit: str | None = Field(default=None, description="Unit note, e.g. '단위: 만원'")
    footnotes: list[str] = Field(default_factory=list)

    def problems(self) -> list[Problem]:
        found: list[Problem] = []
        width = len(self.columns)
        for index, row in enumerate(self.rows):
            if len(row) != width:
                found.append((f"rows[{index}]", f"칸이 {width}개여야 하는데 {len(row)}개입니다"))
        if self.highlight_column is not None and self.highlight_column >= width:
            found.append(
                (
                    "highlight_column",
                    f"열은 0부터 {width - 1}까지인데 {self.highlight_column}입니다",
                )
            )
        return found


class CalloutBlock(BlockBase):
    """A boxed note: information, a warning, or a condition the reader must accept."""

    model_config = ConfigDict(title="CalloutBlock")

    type: Literal["callout"]
    kind: Literal["info", "warning", "condition"]
    title: str | None = None
    body: str = Field(description="Markdown (GFM)")


class DetailsBlock(BlockBase):
    """Supplementary explanation, collapsed until the reader opens it."""

    model_config = ConfigDict(title="DetailsBlock")

    type: Literal["details"]
    summary: str = Field(min_length=1, description="Always-visible line that opens the body")
    body: str = Field(description="Markdown (GFM)")


class GalleryImage(BaseModel):
    model_config = ConfigDict(extra="forbid", title="GalleryImage")

    media_id: int = Field(
        ge=1,
        description="Id of an uploaded image. Private media only in proposal documents.",
    )
    alt: str = Field(min_length=1, description="Text for readers who cannot see the image")
    caption: str | None = None
    url: str | None = Field(
        default=None,
        description="Filled in by the server when the document is served; never stored.",
    )


class GalleryBlock(BlockBase):
    """Images in a grid; selecting one opens a larger viewer. Proposals may use private media."""

    model_config = ConfigDict(title="GalleryBlock")

    type: Literal["gallery"]
    title: str | None = Field(default=None, description="Listed in the table of contents")
    images: list[GalleryImage] = Field(min_length=1, max_length=30)


SERVED_URL = "Filled in by the server when the document is served; never stored."


class AudioTrack(BaseModel):
    model_config = ConfigDict(extra="forbid", title="AudioTrack")

    media_id: int = Field(ge=1, description="Id of an uploaded audio file (private in proposals)")
    label: str = Field(min_length=1, description="e.g. '원음 · 두 화자 혼합', '화자 A · 분리 결과'")
    transcript: str | None = Field(
        default=None, description="What speech-to-text made of this track (변환한 글)"
    )
    script: str | None = Field(
        default=None, description="The original script to compare the transcript with (원래 대본)"
    )
    url: str | None = Field(default=None, description=SERVED_URL)


class MetricsTable(BaseModel):
    model_config = ConfigDict(extra="forbid", title="MetricsTable")

    columns: list[str] = Field(min_length=1, description="Header row")
    rows: list[list[str]] = Field(description="Each row has exactly one cell per column")
    note: str | None = Field(default=None, description="How to read the figures")


class AudioCompareBlock(BlockBase):
    """One original recording and the tracks separated from it, played in one player so the
    listener can switch tracks at the same moment. Each track may carry its transcript and the
    original script side by side; an optional metrics table sums up the results."""

    model_config = ConfigDict(title="AudioCompareBlock")

    type: Literal["audio-compare"]
    title: str | None = Field(default=None, description="Listed in the table of contents")
    description: str | None = Field(default=None, description="How to listen, one paragraph")
    original: AudioTrack  # the mixed recording
    tracks: list[AudioTrack] = Field(min_length=1, max_length=8)  # separated from `original`
    metrics: MetricsTable | None = None

    def problems(self) -> list[Problem]:
        if self.metrics is None:
            return []
        width = len(self.metrics.columns)
        return [
            (f"metrics.rows[{i}]", f"칸이 {width}개여야 하는데 {len(row)}개입니다")
            for i, row in enumerate(self.metrics.rows)
            if len(row) != width
        ]


class VideoBlock(BlockBase):
    """A video with an optional poster image and caption."""

    model_config = ConfigDict(title="VideoBlock")

    type: Literal["video"]
    title: str | None = Field(default=None, description="Listed in the table of contents")
    media_id: int = Field(ge=1, description="Id of an uploaded video (private in proposals)")
    poster_media_id: int | None = Field(
        default=None, ge=1, description="Id of an image shown before playing"
    )
    caption: str | None = None
    allow_download: bool = Field(
        default=False, description="Show a download button for the video file"
    )
    url: str | None = Field(default=None, description=SERVED_URL)
    poster_url: str | None = Field(default=None, description=SERVED_URL)


class CaseSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", title="CaseSnapshot")

    slug: str = Field(description="The portfolio item's address when this was filled in")
    title: str
    summary: str = ""
    period: str = ""
    tags: list[str] = Field(default_factory=list)
    cover_url: str = Field(default="", description="Public URL of the cover image; empty if none")


class CaseRefItem(BaseModel):
    model_config = ConfigDict(extra="forbid", title="CaseRefItem")

    item_id: int = Field(
        ge=1,
        description="Id of a portfolio item (hidden items allowed). Not the slug: slugs change.",
    )
    highlight: str | None = Field(
        default=None,
        max_length=300,
        description="Emphasis line for this proposal; replaces the item's summary when set.",
    )
    case: CaseSnapshot | None = Field(
        default=None,
        description=(
            "The item's content. Never stored in a draft: the server fills it from the current "
            "portfolio when serving a draft or preview, and freezes it into a published revision."
        ),
    )


class CaseRefBlock(BlockBase):
    """Portfolio cases cited by reference, in the given order. A published revision carries the
    cases as they read at publish time."""

    model_config = ConfigDict(title="CaseRefBlock")

    type: Literal["case-ref"]
    title: str | None = Field(default=None, description="Listed in the table of contents")
    items: list[CaseRefItem] = Field(max_length=20)

    def problems(self) -> list[Problem]:
        seen: set[int] = set()
        out: list[Problem] = []
        for i, item in enumerate(self.items):
            if item.item_id in seen:
                out.append((f"items[{i}].item_id", f"항목 {item.item_id}가 겹칩니다"))
            seen.add(item.item_id)
        return out


class HtmlBlock(BlockBase):
    """Exception only: markup no other block can express. Sanitized on storage (allow-list)."""

    model_config = ConfigDict(title="HtmlBlock")

    type: Literal["html"]
    title: str | None = Field(default=None, description="Section heading, listed in the TOC")
    level: Literal[2, 3] = Field(default=2, description="Heading level of the title")
    html: str = Field(
        max_length=50_000,
        description=(
            "HTML limited to text, lists, tables, links and figures. Scripts, event attributes, "
            "style, images, iframes and non-http(s)/mailto/tel URLs are removed when stored."
        ),
    )

    @field_validator("html")
    @classmethod
    def _sanitize(cls, value: str) -> str:
        return sanitize_html(value)


class StepItem(BaseModel):
    model_config = ConfigDict(extra="forbid", title="StepItem")

    id: BlockId = Field(description="Unique within the block")
    title: str = Field(min_length=1, description="The step's name, one short line")
    body: str | None = Field(default=None, description="Short markdown under the title")
    caption: str | None = Field(
        default=None, description="Small note, e.g. who does it or how long"
    )


class StepsBlock(BlockBase):
    """An ordered flow of 2-8 steps joined by arrows (e.g. script -> voice -> video). Horizontal
    layout folds into a vertical one on narrow screens and on paper beyond four steps."""

    model_config = ConfigDict(title="StepsBlock")

    type: Literal["steps"]
    title: str | None = Field(default=None, description="Listed in the table of contents")
    layout: Literal["horizontal", "vertical"] = "horizontal"
    numbered: bool = Field(default=True, description="Show a step number badge")
    items: list[StepItem] = Field(min_length=2, max_length=8)

    def problems(self) -> list[Problem]:
        seen: set[str] = set()
        out: list[Problem] = []
        for i, item in enumerate(self.items):
            if item.id in seen:
                out.append((f"items[{i}].id", f"단계 id {item.id!r}가 겹칩니다"))
            seen.add(item.id)
        return out


class CtaTargetBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", title="CtaTargetBlock")

    kind: Literal["block"]
    block_id: BlockId = Field(
        description="A block of this document; opens its tab and scrolls to it"
    )


class CtaTargetTab(BaseModel):
    model_config = ConfigDict(extra="forbid", title="CtaTargetTab")

    kind: Literal["tab"]
    tab_id: BlockId = Field(description="A tab of this document")


class CtaTargetUrl(BaseModel):
    model_config = ConfigDict(extra="forbid", title="CtaTargetUrl")

    kind: Literal["url"]
    href: str = Field(
        pattern=r"^(https://|mailto:|tel:)\S+$",
        description="Only https:, mailto: or tel: addresses; opens in a new window",
    )


CtaTarget = Annotated[CtaTargetBlock | CtaTargetTab | CtaTargetUrl, Field(discriminator="kind")]


class CtaItem(BaseModel):
    model_config = ConfigDict(extra="forbid", title="CtaItem")

    label: str = Field(min_length=1, max_length=40, description="Button text, one short line")
    target: CtaTarget
    style: Literal["primary", "secondary"] = "primary"


class CtaBlock(BlockBase):
    """One to three link buttons that move the reader to another block or tab of this document,
    or to an outside address. On paper they become link text. Not in the table of contents."""

    model_config = ConfigDict(title="CtaBlock")

    type: Literal["cta"]
    items: list[CtaItem] = Field(min_length=1, max_length=3)

    def document_problems(
        self, tab_ids: frozenset[str], block_ids: frozenset[str]
    ) -> list[Problem]:
        out: list[Problem] = []
        for i, item in enumerate(self.items):
            target = item.target
            if isinstance(target, CtaTargetBlock) and target.block_id not in block_ids:
                out.append(
                    (
                        f"items[{i}].target.block_id",
                        f"문서에 없는 블록 id '{target.block_id}'입니다",
                    )
                )
            elif isinstance(target, CtaTargetTab) and target.tab_id not in tab_ids:
                out.append(
                    (f"items[{i}].target.tab_id", f"문서에 없는 탭 id '{target.tab_id}'입니다")
                )
        return out


# Every block type, discriminated by `type`. Add a new block class here.
Block = Annotated[
    CoverBlock
    | KpiBlock
    | MarkdownBlock
    | TableBlock
    | CalloutBlock
    | DetailsBlock
    | GalleryBlock
    | CaseRefBlock
    | AudioCompareBlock
    | VideoBlock
    | HtmlBlock
    | StepsBlock
    | CtaBlock,
    Field(discriminator="type"),
]


class Tab(BaseModel):
    model_config = ConfigDict(extra="forbid", title="Tab")

    id: BlockId
    title: str = Field(min_length=1)
    blocks: list[Block]


class Document(BaseModel):
    """A block document: tabs of blocks. Shared by public pages, portfolio and proposals."""

    model_config = ConfigDict(extra="forbid", title="Document")

    tabs: list[Tab] = Field(min_length=1)

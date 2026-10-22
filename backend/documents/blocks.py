"""Block document schema: the single source of truth for every block type.

The JSON Schema in /schema/document.schema.json and the frontend types in
frontend/src/blocks/types.gen.ts are generated from these models (`make gen`).
To add a block type, follow frontend/src/blocks/README.md.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

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

    media_id: int = Field(ge=1, description="Id of an uploaded public media item")
    alt: str = Field(min_length=1, description="Text for readers who cannot see the image")
    caption: str | None = None
    url: str | None = Field(
        default=None,
        description="Filled in by the server when the document is served; never stored.",
    )


class GalleryBlock(BlockBase):
    """Images in a grid; selecting one opens a larger viewer. Public media only."""

    model_config = ConfigDict(title="GalleryBlock")

    type: Literal["gallery"]
    title: str | None = Field(default=None, description="Listed in the table of contents")
    images: list[GalleryImage] = Field(min_length=1, max_length=30)


# Every block type, discriminated by `type`. Add a new block class here.
Block = Annotated[
    CoverBlock | KpiBlock | MarkdownBlock | TableBlock | CalloutBlock | DetailsBlock | GalleryBlock,
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

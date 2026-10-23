"""Block edits on a stored block document, shared by proposals and blog posts.

Each function changes the document in place and touches nothing else; the caller then saves it
through its own `stored_document` path, which re-validates the whole document (so a bad block is
refused as `Rejected` with a block path, and nothing is saved). Blocks are found by `block_id`,
tabs by `tab_id`; a missing one is `NotFound`.
"""

from documents.validation import JSON
from services.errors import NotFound


def tabs(document: dict[str, JSON]) -> list[dict[str, JSON]]:
    """The document's own tab list (edit it in place); stored documents hold only tab objects."""
    found: list[dict[str, JSON]] = document["tabs"]  # type: ignore[assignment]  # stored shape
    return found


def blocks(tab: dict[str, JSON]) -> list[JSON]:
    found = tab["blocks"]
    assert isinstance(found, list)
    return found


def find_tab(document: dict[str, JSON], tab_id: str) -> dict[str, JSON]:
    for tab in tabs(document):
        if tab["id"] == tab_id:
            return tab
    raise NotFound(f"탭 {tab_id!r}이(가) 없습니다")


def find_block(document: dict[str, JSON], block_id: str) -> tuple[list[JSON], int]:
    for tab in tabs(document):
        tab_blocks = blocks(tab)
        for index, block in enumerate(tab_blocks):
            if isinstance(block, dict) and block.get("id") == block_id:
                return tab_blocks, index
    raise NotFound(f"블록 {block_id!r}이(가) 없습니다")


def replace_block(document: dict[str, JSON], block_id: str, block: dict[str, object]) -> None:
    """Swap one block in place (same position). A block without an `id` keeps `block_id`."""
    tab_blocks, index = find_block(document, block_id)
    tab_blocks[index] = {"id": block_id, **block}  # type: ignore[dict-item]  # JSON from the caller


def insert_block(
    document: dict[str, JSON],
    tab_id: str,
    block: dict[str, object],
    after_block_id: str | None = None,
) -> None:
    """Add a block to a tab: at the start, or right after `after_block_id` (in that tab)."""
    tab_blocks = blocks(find_tab(document, tab_id))
    position = 0
    if after_block_id is not None:
        ids = [b.get("id") if isinstance(b, dict) else None for b in tab_blocks]
        if after_block_id not in ids:
            raise NotFound(f"탭 {tab_id!r}에 블록 {after_block_id!r}이(가) 없습니다")
        position = ids.index(after_block_id) + 1
    tab_blocks.insert(position, block)  # type: ignore[arg-type]  # JSON from the caller


def delete_block(document: dict[str, JSON], block_id: str) -> None:
    tab_blocks, index = find_block(document, block_id)
    del tab_blocks[index]

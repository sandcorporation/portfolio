"""Validate a block document and report every problem as (block path, reason)."""

from dataclasses import dataclass
from typing import get_args

from pydantic import ValidationError
from pydantic_core import ErrorDetails

from documents.blocks import Block, Document

type JSON = dict[str, JSON] | list[JSON] | str | int | float | bool | None


def _block_types() -> frozenset[str]:
    union = get_args(Block)[0]
    return frozenset(get_args(cls.model_fields["type"].annotation)[0] for cls in get_args(union))


BLOCK_TYPES = _block_types()

# Korean reasons for the pydantic error types an author is likely to hit.
_REASONS = {
    "missing": "필수 값이 없습니다",
    "extra_forbidden": "정의되지 않은 필드입니다",
    "string_type": "문자열이어야 합니다",
    "int_type": "정수여야 합니다",
    "list_type": "배열이어야 합니다",
    "model_type": "객체여야 합니다",
    "model_attributes_type": "객체여야 합니다",
    "dict_type": "객체여야 합니다",
    "literal_error": "허용된 값이 아닙니다",
    "string_pattern_mismatch": "형식이 맞지 않습니다",
    "union_tag_invalid": "알 수 없는 블록 타입입니다",
    "union_tag_not_found": "블록 타입(type)이 없습니다",
}


@dataclass(frozen=True)
class DocumentError:
    path: str
    reason: str


class InvalidDocument(Exception):
    def __init__(self, errors: list[DocumentError]) -> None:
        super().__init__("; ".join(f"{e.path}: {e.reason}" for e in errors))
        self.errors = errors


def validate_document(data: object) -> Document:
    """Parse a stored or submitted document. Raises InvalidDocument listing every problem."""
    try:
        document = Document.model_validate(data)
    except ValidationError as exc:
        raise InvalidDocument([_from_pydantic(detail) for detail in exc.errors()]) from None
    errors = _semantic_errors(document)
    if errors:
        raise InvalidDocument(errors)
    return document


def normalized(document: Document) -> dict[str, JSON]:
    """The form a document is stored in: defaults filled, JSON-safe."""
    return document.model_dump(mode="json")


def _semantic_errors(document: Document) -> list[DocumentError]:
    errors: list[DocumentError] = []
    seen_tabs: set[str] = set()
    seen_blocks: set[str] = set()
    for t, tab in enumerate(document.tabs):
        if tab.id in seen_tabs:
            errors.append(DocumentError(f"tabs[{t}].id", f"탭 id '{tab.id}'가 겹칩니다"))
        seen_tabs.add(tab.id)
        for b, block in enumerate(tab.blocks):
            path = f"tabs[{t}].blocks[{b}]"
            if block.id in seen_blocks:
                errors.append(DocumentError(f"{path}.id", f"블록 id '{block.id}'가 겹칩니다"))
            seen_blocks.add(block.id)
            errors.extend(DocumentError(f"{path}.{sub}", why) for sub, why in block.problems())
    return errors


def _from_pydantic(detail: ErrorDetails) -> DocumentError:
    return DocumentError(_path(detail["loc"]), _REASONS.get(detail["type"], detail["msg"]))


def _path(loc: tuple[int | str, ...]) -> str:
    """('tabs', 0, 'blocks', 3, 'table', 'rows', 2) -> 'tabs[0].blocks[3].rows[2]'.

    Pydantic puts the discriminator value after a block's index; it is noise for authors.
    """
    out = ""
    after_block_index = False
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
            after_block_index = out.endswith(f"blocks[{part}]")
            continue
        if after_block_index and part in BLOCK_TYPES:
            after_block_index = False
            continue
        after_block_index = False
        out += f".{part}" if out else part
    return out or "(문서)"

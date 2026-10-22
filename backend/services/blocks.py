"""Block catalog: every block type with its JSON Schema and one valid example.

The schemas come from the same Pydantic models and generator as /schema/document.schema.json
(`documents.schema_export`), so MCP clients see exactly what `validate_document` accepts.
A new block type needs an example here; tests fail until it has one.
"""

from typing import TypedDict, get_args

from pydantic import BaseModel, TypeAdapter

from documents.blocks import Block, Document
from documents.schema_export import ModelTitlesOnly
from documents.validation import JSON


class BlockTypeSummary(TypedDict):
    type: str
    description: str


class BlockSchema(TypedDict):
    type: str
    description: str
    schema: dict[str, JSON]
    example: dict[str, JSON]


class UnknownBlockType(Exception):
    def __init__(self, block_type: str) -> None:
        super().__init__(block_type)
        self.block_type = block_type


EXAMPLES: dict[str, dict[str, JSON]] = {
    "cover": {
        "id": "cover",
        "type": "cover",
        "recipient": "홍길순 대표님께",
        "title": "사내 업무 자동화 제안",
        "subtitle": "견적과 일정",
    },
    "kpi": {
        "id": "kpi",
        "type": "kpi",
        "title": "요약",
        "items": [
            {"label": "총액", "value": "5,950만원", "note": "부가세 별도"},
            {"label": "기간", "value": "12주"},
        ],
    },
    "markdown": {
        "id": "scope",
        "type": "markdown",
        "title": "범위",
        "level": 2,
        "body": "- 주문 접수 자동화\n- 정산 리포트",
    },
    "table": {
        "id": "price",
        "type": "table",
        "title": "견적",
        "columns": ["항목", "금액"],
        "rows": [["설계", "800"], ["개발", "5,150"]],
        "highlight_column": 1,
        "unit": "단위: 만원",
        "footnotes": ["부가세 별도"],
    },
    "callout": {
        "id": "terms",
        "type": "callout",
        "kind": "condition",
        "title": "조건",
        "body": "계약금 30%는 착수 시 지급합니다.",
    },
    "details": {
        "id": "faq",
        "type": "details",
        "summary": "유지보수는 어떻게 되나요?",
        "body": "납품 후 3개월은 무상입니다.",
    },
    "gallery": {
        "id": "shots",
        "type": "gallery",
        "title": "화면",
        "images": [{"media_id": 1, "alt": "대시보드 화면", "caption": "관리자 대시보드"}],
    },
    "audio-compare": {
        "id": "separation",
        "type": "audio-compare",
        "title": "원음과 분리음 비교",
        "description": "원음을 들은 뒤 화자 A와 화자 B로 바꿔 들어 보세요.",
        "original": {"media_id": 4, "label": "원음 · 두 화자 혼합"},
        "tracks": [
            {
                "media_id": 5,
                "label": "화자 A",
                "transcript": "네 확인해 보겠습니다",
                "script": "네, 확인해 보겠습니다.",
            },
            {"media_id": 6, "label": "화자 B"},
        ],
        "metrics": {
            "columns": ["시험", "글자 오류"],
            "rows": [["전화 음질·잡음", "9 / 237"]],
            "note": "글자 오류는 원래 대본과 다른 글자 수입니다.",
        },
    },
    "video": {
        "id": "demo",
        "type": "video",
        "title": "시연 영상",
        "media_id": 7,
        "poster_media_id": 1,
        "caption": "약 45초 · 자막",
        "allow_download": True,
    },
    "html": {
        "id": "flow",
        "type": "html",
        "title": "제작 흐름",
        "level": 3,
        "html": (
            "<ol><li><strong>대본</strong></li><li><strong>음성</strong></li>"
            "<li><strong>영상</strong></li></ol>"
        ),
    },
    "steps": {
        "id": "lecture-flow",
        "type": "steps",
        "title": "제작 흐름",
        "layout": "horizontal",
        "numbered": True,
        "items": [
            {
                "id": "script",
                "title": "강의 대본",
                "body": "대본을 쓰고 고칩니다",
            },
            {
                "id": "voice",
                "title": "본인 목소리 음성",
                "body": "녹음 음성을 기준으로 합성합니다",
            },
            {
                "id": "video",
                "title": "강의 영상",
                "body": "자막과 장면을 Remotion으로 합성합니다",
                "caption": "최종 산출물",
            },
        ],
    },
    "cta": {
        "id": "next-actions",
        "type": "cta",
        "items": [
            {
                "label": "제작 흐름 보기 →",
                "target": {"kind": "block", "block_id": "lecture-flow"},
                "style": "primary",
            },
            {
                "label": "회사 소개 보기",
                "target": {"kind": "url", "href": "https://example.com/about"},
                "style": "secondary",
            },
        ],
    },
    "case-ref": {
        "id": "cases",
        "type": "case-ref",
        "title": "수행사례",
        "items": [{"item_id": 1, "highlight": "이번 제안과 가장 닮은 사례"}],
    },
}


def _block_classes() -> dict[str, type[BaseModel]]:
    union = get_args(Block)[0]
    return {get_args(cls.model_fields["type"].annotation)[0]: cls for cls in get_args(union)}


def _schema(model: type[BaseModel]) -> dict[str, JSON]:
    schema: dict[str, JSON] = TypeAdapter(model).json_schema(
        mode="validation", schema_generator=ModelTitlesOnly
    )
    return schema


def _description(model: type[BaseModel]) -> str:
    return (model.__doc__ or "").strip()


def block_types() -> list[BlockTypeSummary]:
    return [
        BlockTypeSummary(type=name, description=_description(cls))
        for name, cls in _block_classes().items()
    ]


def block_schema(block_type: str) -> BlockSchema:
    cls = _block_classes().get(block_type)
    if cls is None:
        raise UnknownBlockType(block_type)
    return BlockSchema(
        type=block_type,
        description=_description(cls),
        schema=_schema(cls),
        example=EXAMPLES[block_type],
    )


def document_schema() -> dict[str, JSON]:
    """The whole document (tabs of blocks), as in /schema/document.schema.json."""
    return _schema(Document)

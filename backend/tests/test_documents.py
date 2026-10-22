"""Block documents: the site profile's documents are validated when saved through admin."""

import copy
import json
import re
from html import unescape
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from content.models import SiteProfile
from documents.blocks import CtaBlock, HtmlBlock
from documents.validation import JSON, InvalidDocument, validate_document

pytestmark = pytest.mark.django_db


def profile_form(company: JSON, ceo: JSON | None = None) -> dict[str, str]:
    empty = {"tabs": [{"id": "main", "title": "소개", "blocks": []}]}
    return {
        "tagline": "음성·영상 처리와 사내 시스템을 만듭니다",
        "company_intro": json.dumps(company, ensure_ascii=False),
        "ceo_intro": json.dumps(ceo if ceo is not None else empty, ensure_ascii=False),
        "contact_email": "hello@sandcorp.co.kr",
        "contact_phone": "010-0000-0000",
        "address": "",
    }


def change_url() -> str:
    return reverse("admin:content_siteprofile_change", args=[SiteProfile.load().pk])


def error_list(html: str) -> list[str]:
    """Field errors admin shows next to the form."""
    lists = re.findall(r'<ul class="errorlist"[^>]*>(.*?)</ul>', html, re.S)
    return [unescape(item) for block in lists for item in re.findall(r"<li>(.*?)</li>", block)]


def blocks(document: dict[str, JSON], tab: int) -> list[JSON]:
    tabs = document["tabs"]
    assert isinstance(tabs, list)
    chosen = tabs[tab]
    assert isinstance(chosen, dict)
    found = chosen["blocks"]
    assert isinstance(found, list)
    return found


def test_valid_document_is_saved_from_admin(
    admin_client: Client, example_document: dict[str, JSON]
) -> None:
    response = admin_client.post(change_url(), profile_form(example_document))

    assert response.status_code == 302
    saved = SiteProfile.load().company_intro
    assert [b["id"] for b in blocks(saved, 0) if isinstance(b, dict)][:3] == [
        "cover",
        "summary-kpi",
        "intro",
    ]


def test_invalid_document_is_rejected_with_block_paths(
    admin_client: Client, example_document: dict[str, JSON]
) -> None:
    broken = copy.deepcopy(example_document)
    estimate = blocks(broken, 0)
    table = estimate[4]
    assert isinstance(table, dict) and isinstance(table["rows"], list)
    table["rows"][2] = ["장비 구입 예산", "650"]  # two cells in a four-column table
    estimate[1] = {
        "id": "summary-kpi",
        "type": "kpi",
        "items": [{"label": "기간", "value": "12주"}],
    }
    count = len(estimate)
    estimate.append({"id": "cover", "type": "markdown", "body": "같은 id"})
    estimate.append({"id": "chart", "type": "chart"})

    response = admin_client.post(change_url(), profile_form(broken))

    assert response.status_code == 200  # the form is shown again, nothing saved
    errors = error_list(response.content.decode())
    assert any(e.startswith("tabs[0].blocks[1].items:") for e in errors)
    assert f"tabs[0].blocks[{count + 1}]: 알 수 없는 블록 타입입니다" in errors
    assert SiteProfile.load().company_intro != broken


def test_cross_field_problems_are_reported_once_fields_parse(
    admin_client: Client, example_document: dict[str, JSON]
) -> None:
    broken = copy.deepcopy(example_document)
    estimate = blocks(broken, 0)
    table = estimate[4]
    assert isinstance(table, dict) and isinstance(table["rows"], list)
    table["rows"][2] = ["장비 구입 예산", "650"]
    table["highlight_column"] = 7
    count = len(estimate)
    estimate.append({"id": "cover", "type": "markdown", "body": "같은 id"})

    response = admin_client.post(change_url(), profile_form(broken))

    errors = error_list(response.content.decode())
    assert errors == [
        "tabs[0].blocks[4].rows[2]: 칸이 4개여야 하는데 2개입니다",
        "tabs[0].blocks[4].highlight_column: 열은 0부터 3까지인데 7입니다",
        f"tabs[0].blocks[{count}].id: 블록 id 'cover'가 겹칩니다",
    ]


def test_validation_errors_name_the_field_inside_the_block() -> None:
    with pytest.raises(InvalidDocument) as caught:
        validate_document(
            {
                "tabs": [
                    {
                        "id": "t",
                        "title": "탭",
                        "blocks": [
                            {"id": "c", "type": "callout", "kind": "danger", "body": "x"},
                            {"id": "d", "type": "details", "body": "x", "extra": 1},
                        ],
                    }
                ]
            }
        )

    assert [(e.path, e.reason) for e in caught.value.errors] == [
        ("tabs[0].blocks[0].kind", "허용된 값이 아닙니다"),
        ("tabs[0].blocks[1].summary", "필수 값이 없습니다"),
        ("tabs[0].blocks[1].extra", "정의되지 않은 필드입니다"),
    ]


def test_profile_edited_in_admin_shows_on_home(
    admin_client: Client, client: Client, example_document: dict[str, JSON]
) -> None:
    ceo: JSON = {
        "tabs": [
            {
                "id": "ceo",
                "title": "대표 소개",
                "blocks": [{"id": "bio", "type": "markdown", "title": "한상진", "body": "대표"}],
            }
        ]
    }
    admin_client.post(change_url(), profile_form(example_document, ceo))

    html = client.get("/").content.decode()
    data_tag = re.search(r'<script id="page-data" type="application/json">(.*?)</script>', html)
    assert data_tag is not None
    data = json.loads(data_tag.group(1))
    assert data["company_intro"]["tabs"][0]["blocks"][0]["title"] == (
        "채권추심 녹취 분석 시스템 구축 제안"
    )
    assert data["ceo_intro"]["tabs"][0]["blocks"][0]["title"] == "한상진"
    assert data["contact"]["email"] == "hello@sandcorp.co.kr"


# --- html block ---

HOSTILE = (
    '<p onclick="steal()" style="position:fixed;inset:0" class="x" id="y">본문'
    '<script>alert(1)</script><a href="javascript:alert(1)">나쁜 링크</a>'
    '<a href="https://example.com/a" target="_blank" onmouseover="x()">좋은 링크</a>'
    '<img src="https://tracker.example/p.gif" onerror="x()">'
    '<svg onload="x()"><a xlink:href="javascript:1">s</a></svg>'
    '<iframe src="https://evil.example"></iframe>'
    '<a href="data:text/html,<script>1</script>">d</a><a href="#top">f</a>'
    "<!-- comment --></p>"
    '<table><tr><td colspan="2" onclick="x()">셀</td></tr></table>'
    '<form action="/x"><input name="a"></form>'
)


def html_block(markup: str) -> dict[str, JSON]:
    return {"id": "h", "type": "html", "html": markup}


def stored_html(markup: str) -> str:
    document = validate_document(
        {"tabs": [{"id": "t", "title": "T", "blocks": [html_block(markup)]}]}
    )
    block = document.tabs[0].blocks[0]
    assert isinstance(block, HtmlBlock)
    return block.html


def test_html_block_drops_scripts_event_attributes_and_dangerous_urls() -> None:
    cleaned = stored_html(HOSTILE)

    for forbidden in (
        "script", "alert", "onclick", "onerror", "onload", "onmouseover", "javascript:",
        "data:", "style", "position", "class=", "id=", "<img", "<svg", "<iframe", "<form",
        "<input", "comment", "tracker.example", 'href="#',
    ):  # fmt: skip
        assert forbidden not in cleaned, forbidden
    assert "본문" in cleaned and "나쁜 링크" in cleaned and "셀" in cleaned
    assert (
        '<a href="https://example.com/a" rel="noopener noreferrer nofollow">좋은 링크</a>'
        in cleaned
    )
    assert '<td colspan="2">셀</td>' in cleaned


def test_html_block_sanitizing_is_idempotent() -> None:
    once = stored_html(HOSTILE)

    assert stored_html(once) == once


def test_admin_stores_the_sanitized_html(admin_client: Client) -> None:
    block = html_block("<b>굵게</b><script>x()</script>")
    document: dict[str, JSON] = {"tabs": [{"id": "t", "title": "T", "blocks": [block]}]}

    response = admin_client.post(change_url(), profile_form(document))

    assert response.status_code == 302
    saved: Any = SiteProfile.load().company_intro  # Any: raw JSON
    assert saved["tabs"][0]["blocks"][0]["html"] == "<b>굵게</b>"


# --- steps block ---


def steps_errors(block: dict[str, JSON]) -> list[tuple[str, str]]:
    with pytest.raises(InvalidDocument) as caught:
        validate_document({"tabs": [{"id": "t", "title": "T", "blocks": [block]}]})
    return [(e.path, e.reason) for e in caught.value.errors]


def step(item_id: str, title: str = "단계") -> dict[str, JSON]:
    return {"id": item_id, "title": title}


def steps_block(items: list[JSON]) -> dict[str, JSON]:
    return {"id": "s", "type": "steps", "items": items}


def test_steps_block_accepts_two_to_eight_steps_with_defaults() -> None:
    for count in (2, 8):
        validate_document(
            {
                "tabs": [
                    {
                        "id": "t",
                        "title": "T",
                        "blocks": [steps_block([step(f"a{i}") for i in range(count)])],
                    }
                ]
            }
        )


@pytest.mark.parametrize("count", [0, 1, 9])
def test_steps_block_rejects_too_few_or_too_many_items(count: int) -> None:
    errors = steps_errors(steps_block([step(f"a{i}") for i in range(count)]))

    assert [path for path, _ in errors] == ["tabs[0].blocks[0].items"]


def test_steps_block_rejects_empty_title() -> None:
    errors = steps_errors(steps_block([step("a", ""), step("b")]))

    assert [path for path, _ in errors] == ["tabs[0].blocks[0].items[0].title"]


def test_steps_block_rejects_duplicate_item_ids() -> None:
    errors = steps_errors(steps_block([step("a"), step("b"), step("a")]))

    assert errors == [("tabs[0].blocks[0].items[2].id", "단계 id 'a'가 겹칩니다")]


# --- cta block ---


def cta_item(target: dict[str, JSON], label: str = "보기") -> dict[str, JSON]:
    return {"label": label, "target": target}


def cta_document(items: list[JSON]) -> dict[str, JSON]:
    return {
        "tabs": [
            {
                "id": "t1",
                "title": "첫 탭",
                "blocks": [{"id": "c", "type": "cta", "items": items}],
            },
            {
                "id": "t2",
                "title": "둘째 탭",
                "blocks": [{"id": "m", "type": "markdown", "body": "본문"}],
            },
        ]
    }


def cta_errors(items: list[JSON]) -> list[tuple[str, str]]:
    with pytest.raises(InvalidDocument) as caught:
        validate_document(cta_document(items))
    return [(e.path, e.reason) for e in caught.value.errors]


def test_cta_block_accepts_every_target_kind_with_default_style() -> None:
    document = validate_document(
        cta_document(
            [
                cta_item({"kind": "block", "block_id": "m"}),
                cta_item({"kind": "tab", "tab_id": "t2"}),
                cta_item({"kind": "url", "href": "https://example.com/a?b=1"}),
            ]
        )
    )
    block = document.tabs[0].blocks[0]
    assert isinstance(block, CtaBlock) and block.items[0].style == "primary"


@pytest.mark.parametrize(
    "href", ["javascript:alert(1)", "http://example.com", "data:text/html,x", "//example.com", ""]
)
def test_cta_block_rejects_url_schemes_other_than_https_mailto_tel(href: str) -> None:
    errors = cta_errors([cta_item({"kind": "url", "href": href})])

    assert [path for path, _ in errors] == ["tabs[0].blocks[0].items[0].target.href"]


@pytest.mark.parametrize("count", [0, 4])
def test_cta_block_takes_one_to_three_items(count: int) -> None:
    errors = cta_errors([cta_item({"kind": "tab", "tab_id": "t1"})] * count)

    assert [path for path, _ in errors] == ["tabs[0].blocks[0].items"]


def test_cta_block_rejects_long_label() -> None:
    errors = cta_errors([cta_item({"kind": "tab", "tab_id": "t1"}, "가" * 41)])

    assert [path for path, _ in errors] == ["tabs[0].blocks[0].items[0].label"]


def test_cta_block_rejects_targets_missing_from_the_document() -> None:
    errors = cta_errors(
        [
            cta_item({"kind": "block", "block_id": "ghost"}),
            cta_item({"kind": "tab", "tab_id": "ghost"}),
            cta_item({"kind": "tab", "tab_id": "t2"}),
        ]
    )

    assert errors == [
        ("tabs[0].blocks[0].items[0].target.block_id", "문서에 없는 블록 id 'ghost'입니다"),
        ("tabs[0].blocks[0].items[1].target.tab_id", "문서에 없는 탭 id 'ghost'입니다"),
    ]

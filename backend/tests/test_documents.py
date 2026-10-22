"""Block documents: the site profile's documents are validated when saved through admin."""

import copy
import json
import re
from html import unescape

import pytest
from django.test import Client
from django.urls import reverse

from content.models import SiteProfile
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
    estimate.append({"id": "cover", "type": "markdown", "body": "같은 id"})
    estimate.append({"id": "chart", "type": "chart"})

    response = admin_client.post(change_url(), profile_form(broken))

    assert response.status_code == 200  # the form is shown again, nothing saved
    errors = error_list(response.content.decode())
    assert any(e.startswith("tabs[0].blocks[1].items:") for e in errors)
    assert "tabs[0].blocks[9]: 알 수 없는 블록 타입입니다" in errors
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
    estimate.append({"id": "cover", "type": "markdown", "body": "같은 id"})

    response = admin_client.post(change_url(), profile_form(broken))

    errors = error_list(response.content.decode())
    assert errors == [
        "tabs[0].blocks[4].rows[2]: 칸이 4개여야 하는데 2개입니다",
        "tabs[0].blocks[4].highlight_column: 열은 0부터 3까지인데 7입니다",
        "tabs[0].blocks[8].id: 블록 id 'cover'가 겹칩니다",
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

import json
import re
from typing import Any
from xml.etree import ElementTree

import pytest
from django.test import Client

from adapters.fake_storage import FakeObjectStorage
from content.models import Media, PortfolioItem, SiteProfile
from documents.validation import JSON, normalized, validate_document
from services import media as media_service
from services.portfolio import all_items, get_item, public_slugs

pytestmark = pytest.mark.django_db


def make(
    slug: str,
    order: int = 0,
    public: bool = True,
    body: dict[str, JSON] | None = None,
    **fields: str | Media,
) -> PortfolioItem:
    fields.setdefault("title", slug.upper())
    item = PortfolioItem(slug=slug, sort_order=order, is_public=public, **fields)
    if body is not None:
        item.body = body
    item.save()
    return item


def page_data(html: str) -> dict[str, Any]:  # Any: test reads arbitrary JSON
    found = re.search(r'<script id="page-data" type="application/json">(.*?)</script>', html, re.S)
    assert found
    data: dict[str, Any] = json.loads(found.group(1))
    return data


def test_home_lists_only_public_items_in_sort_order(client: Client) -> None:
    make("late", order=2)
    make("early", order=1, summary="요약", tags="음성, 분석", period="2025.03")
    make("secret", order=0, public=False)

    cards = page_data(client.get("/").content.decode())["portfolio"]

    assert [c["slug"] for c in cards] == ["early", "late"]
    assert cards[0]["tags"] == ["음성", "분석"]


def test_sitemap_has_home_and_public_items_only(client: Client) -> None:
    make("b", order=2)
    make("a", order=1)
    make("secret", public=False)

    response = client.get("/sitemap.xml")
    locs = [
        e.text
        for e in ElementTree.fromstring(response.content).iter(
            "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
        )
    ]

    assert response["Content-Type"].startswith("application/xml")
    assert locs == [
        "https://sandcorp.co.kr/",
        "https://sandcorp.co.kr/work/a",
        "https://sandcorp.co.kr/work/b",
    ]


def test_hidden_item_detail_is_404_but_data_remains(client: Client) -> None:
    make("secret", public=False)

    assert client.get("/work/secret").status_code == 404
    assert client.get("/work/missing").status_code == 404
    assert PortfolioItem.objects.filter(slug="secret").exists()


def test_detail_shell_carries_item_og_meta_and_body(
    client: Client, example_document: dict[str, JSON], fake_storage: FakeObjectStorage
) -> None:
    cover = media_service.upload("c.png", "image/png", b"x", is_public=True)
    make(
        "voice",
        title="녹취 분석",
        summary="채권추심 녹취를 분석합니다",
        cover=cover,
        body=example_document,
    )

    response = client.get("/work/voice")
    html = response.content.decode()

    assert response.status_code == 200
    assert "<title>녹취 분석 | Sandcorp</title>" in html
    assert '<meta property="og:title" content="녹취 분석 | Sandcorp">' in html
    assert '<meta property="og:description" content="채권추심 녹취를 분석합니다">' in html
    assert (
        f'<meta property="og:image" content="{fake_storage.public_url(cover.object_key)}">' in html
    )
    assert '<meta property="og:url" content="http://testserver/work/voice">' in html
    assert '<meta name="robots" content="index, follow">' in html
    data = page_data(html)
    # Serving adds the public urls of gallery images, audio and video; apart from that the body
    # is the stored one.
    served: Any = data["body"]  # Any: test pokes into JSON
    expected: Any = normalized(validate_document(example_document))  # Any: ditto
    gallery = block_by_id(served, "case-gallery")["images"]
    assert [image["url"] for image in gallery] == [
        fake_storage.public_url(f"example-{n}.png") for n in (1, 2, 3)
    ]
    sep = block_by_id(served, "separation")
    assert sep["original"]["url"] == fake_storage.public_url("example-4")
    demo = block_by_id(served, "demo-video")
    assert (demo["url"], demo["poster_url"]) == (
        fake_storage.public_url("example-7"),
        fake_storage.public_url("example-1.png"),
    )
    for body in (served, expected):
        for image in block_by_id(body, "case-gallery")["images"]:
            image["url"] = None
        for block in all_blocks(body):
            if block["type"] == "audio-compare":
                for track in [block["original"], *block["tracks"]]:
                    track["url"] = None
            if block["type"] == "video":
                block["url"] = block["poster_url"] = None
    for ref in block_by_id(expected, "case-refs")["items"]:
        ref["case"] = None  # a stored document keeps references only
    assert served == expected


def all_blocks(document: Any) -> list[Any]:  # Any: raw JSON
    return [block for tab in document["tabs"] for block in tab["blocks"]]


def block_by_id(document: Any, block_id: str) -> Any:  # Any: raw JSON
    return next(block for block in all_blocks(document) if block["id"] == block_id)


def test_detail_without_cover_uses_the_default_og_image(client: Client) -> None:
    make("plain")
    html = client.get("/work/plain").content.decode()
    assert (
        '<meta property="og:image" content="http://testserver/static/core/og-default.png">' in html
    )


def test_robots_blocks_proposals_and_points_to_the_sitemap(client: Client) -> None:
    response = client.get("/robots.txt")

    assert response["Content-Type"].startswith("text/plain")
    body = response.content.decode()
    assert "Disallow: /p/" in body
    assert "Sitemap: https://sandcorp.co.kr/sitemap.xml" in body


def test_invalid_body_is_rejected_on_save() -> None:
    from documents.validation import InvalidDocument

    with pytest.raises(InvalidDocument):
        make("bad", body={"tabs": "nope"})


def test_full_lookups_include_hidden_items_while_public_ones_do_not() -> None:
    make("shown")
    make("secret", public=False)

    assert public_slugs() == ["shown"]
    assert {i.slug for i in all_items()} == {"shown", "secret"}
    secret = get_item("secret")
    assert secret is not None and not secret.is_public


def test_detail_carries_the_service_url_for_the_meta_row(client: Client) -> None:
    make("live", service_url="https://live.example/")

    data = page_data(client.get("/work/live").content.decode())

    assert data["service_url"] == "https://live.example/"


def test_home_carries_tagline_and_stack_for_the_hero(client: Client) -> None:
    profile = SiteProfile.load()
    profile.tagline = "끝까지 책임지는 1인 개발사"
    profile.github = {"stack_badges": ["Django", "React"]}
    profile.save()

    data = page_data(client.get("/").content.decode())

    assert data["tagline"] == "끝까지 책임지는 1인 개발사"
    assert data["stack"] == ["Django", "React"]


def test_home_without_a_profile_has_empty_tagline_and_stack(client: Client) -> None:
    data = page_data(client.get("/").content.decode())

    assert (data["tagline"], data["stack"]) == ("", [])


def test_status_and_outcome_reach_the_shell_card_and_blank_ones_stay_empty(client: Client) -> None:
    make("live", order=1, status="live", outcome="월 3천 건 처리")
    make("plain", order=2)

    cards = page_data(client.get("/").content.decode())["portfolio"]

    assert (cards[0]["status"], cards[0]["status_label"], cards[0]["outcome"]) == (
        "live",
        "운영 중",
        "월 3천 건 처리",
    )
    assert (cards[1]["status"], cards[1]["status_label"], cards[1]["outcome"]) == ("", "", "")


def test_the_work_page_data_carries_status_and_outcome(client: Client) -> None:
    make("ended", status="ended", outcome="2025년 종료")

    card = page_data(client.get("/work/ended").content.decode())["card"]

    assert (card["status_label"], card["outcome"]) == ("서비스 종료", "2025년 종료")


def test_status_values_are_the_three_choices_plus_none() -> None:
    from pydantic import ValidationError

    from services.portfolio import ItemPatch, NewItem

    for value in ("", "live", "building", "ended"):
        assert NewItem(slug="a", title="A", status=value).status == value
    with pytest.raises(ValidationError):
        ItemPatch(status="paused")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ItemPatch(outcome="가" * 161)


def test_create_and_update_set_and_clear_status_and_outcome() -> None:
    from services.portfolio import ItemPatch, NewItem, create_item, update_item

    made = create_item(NewItem(slug="s", title="S", status="building", outcome=" 한 줄 "))
    assert (made.status, made.outcome) == ("building", "한 줄")

    kept = update_item("s", ItemPatch(title="S2"))
    assert (kept.status, kept.outcome) == ("building", "한 줄")  # left out: unchanged

    cleared = update_item("s", ItemPatch(status="", outcome=""))
    assert (cleared.status, cleared.outcome) == ("", "")

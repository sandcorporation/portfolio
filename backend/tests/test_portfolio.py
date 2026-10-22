import json
import re
from typing import Any
from xml.etree import ElementTree

import pytest
from django.test import Client

from adapters.fake_storage import FakeObjectStorage
from content.models import Media, PortfolioItem
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
    # Serving adds each gallery image's public url; apart from that the body is the stored one.
    gallery = data["body"]["tabs"][1]["blocks"][3]["images"]
    assert [image["url"] for image in gallery] == [
        fake_storage.public_url(f"example-{n}.png") for n in (1, 2, 3)
    ]
    for image in gallery:
        image["url"] = None
    expected: Any = normalized(validate_document(example_document))  # Any: test pokes into JSON
    for image in expected["tabs"][1]["blocks"][3]["images"]:
        image["url"] = None
    for ref in expected["tabs"][1]["blocks"][4]["items"]:
        ref["case"] = None  # a stored document keeps references only
    # Audio and video get their public urls the same way.
    sep, demo = data["body"]["tabs"][2]["blocks"]
    assert sep["original"]["url"] == fake_storage.public_url("example-4")
    assert (demo["url"], demo["poster_url"]) == (
        fake_storage.public_url("example-7"),
        fake_storage.public_url("example-1.png"),
    )
    for body in (data["body"], expected):
        sep, demo = body["tabs"][2]["blocks"]
        for track in [sep["original"], *sep["tracks"]]:
            track["url"] = None
        demo["url"] = demo["poster_url"] = None
    assert data["body"] == expected


def test_detail_without_cover_has_no_og_image(client: Client) -> None:
    make("plain")
    assert "og:image" not in client.get("/work/plain").content.decode()


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

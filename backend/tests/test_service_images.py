"""The service images (issue 219): a cover (detail page, home card, og:image, JSON-LD image) and
one figure between 02 What and 03 Process, through MCP/offerings and admin rules, on both the
server HTML and the app's data. A service without images keeps the page it had."""

import json
import re
from typing import cast

import pytest
from django.test import Client
from django.utils import timezone

from content.models import Media, Service
from services import media, offerings
from services.errors import Rejected

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("services", "fake_storage")]

SLUG = "mcp-integration"


def _media(
    pk: int,
    *,
    content_type: str = "image/png",
    public: bool = True,
    done: bool = True,
    size: tuple[int, int] | None = (2400, 950),
) -> Media:
    return Media.objects.create(
        pk=pk,
        object_key=f"service-{pk}",
        content_type=content_type,
        size=1,
        original_filename=f"service-{pk}",
        is_public=public,
        uploaded_at=timezone.now() if done else None,
        width=size[0] if size else None,
        height=size[1] if size else None,
    )


def _patch(**fields: object) -> offerings.ServicePatch:
    return offerings.ServicePatch.model_validate(fields)


def _root(html: str) -> str:
    return re.search(r'<div id="root">(.*)</div>\s*<script', html, re.S).group(1)  # type: ignore[union-attr]


def _tags(html: str, key: str) -> list[str]:
    return re.findall(rf'<meta (?:property|name)="{re.escape(key)}" content="([^"]*)"', html)


def _ld(html: str) -> dict[str, object]:
    (text,) = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    return cast(dict[str, object], json.loads(text))


def _with_images() -> tuple[str, str]:
    cover, figure = _media(901), _media(902, size=(2400, 1000))
    offerings.update_service(
        SLUG,
        _patch(
            cover_media_id=cover.pk,
            cover_alt="구조도",
            figure_media_id=figure.pk,
            figure_alt="호출 순서",
            figure_caption="도구 호출 한 번의 순서",
        ),
    )
    return cast(str, media.public_url(cover)), cast(str, media.public_url(figure))


def test_a_service_without_images_draws_and_tags_as_before(client: Client) -> None:
    html = client.get(f"/services/{SLUG}").content.decode()
    body = _root(html)

    assert "<img" not in body and "<figure" not in body and "work-cover" not in body
    assert _tags(html, "og:image") == ["http://testserver/static/core/og-default.png"]
    assert _tags(html, "og:image:width") == ["1200"]
    assert _tags(html, "twitter:card") == ["summary_large_image"]
    assert "image" not in _ld(html)
    assert "service-thumb" not in _root(client.get("/").content.decode())
    card = next(c for c in offerings.cards() if c["slug"] == SLUG)
    assert card["cover"] is None
    out = offerings.get_service(SLUG)
    assert (out.cover_media_id, out.cover_url, out.figure_media_id, out.figure_alt) == (
        None,
        "",
        None,
        "",
    )


def test_images_draw_in_the_server_html_and_the_app_data(client: Client) -> None:
    cover_url, figure_url = _with_images()
    html = client.get(f"/services/{SLUG}").content.decode()
    body = _root(html)

    cover_tag = (
        f'<a class="service-zoom" href="{cover_url}" target="_blank" rel="noopener noreferrer">'
        f'<img class="work-cover sc-prose-cover" src="{cover_url}" alt="구조도" '
        'width="2400" height="950"></a>'
    )
    assert cover_tag in body  # not lazy: it is the first screen
    assert body.index("accent-rule") < body.index(cover_tag) < body.index("service-audience")
    figure = (
        f'<figure class="service-figure"><a class="service-zoom" href="{figure_url}" '
        'target="_blank" rel="noopener noreferrer">'
        f'<img class="sc-prose-cover" src="{figure_url}" '
        'alt="호출 순서" width="2400" height="1000" loading="lazy"></a>'
        "<figcaption>도구 호출 한 번의 순서</figcaption></figure>"
    )
    assert figure in body
    assert body.index("service-scope") < body.index(figure) < body.index("service-process")

    data = json.loads(re.search(r'id="page-data"[^>]*>(.*?)</script>', html, re.S).group(1))  # type: ignore[union-attr]
    assert data["offering"]["cover"] == {
        "url": cover_url,
        "width": 2400,
        "height": 950,
        "alt": "구조도",
        "caption": "",
    }
    assert data["offering"]["figure"]["caption"] == "도구 호출 한 번의 순서"


def test_the_cover_alt_falls_back_to_the_name_and_the_caption_is_optional(client: Client) -> None:
    offerings.update_service(
        SLUG,
        _patch(cover_media_id=_media(901).pk, figure_media_id=_media(902).pk, figure_alt="그림"),
    )
    body = _root(client.get(f"/services/{SLUG}").content.decode())

    assert f'alt="{Service.objects.get(slug=SLUG).name}"' in body
    assert "<figcaption" not in body


def test_the_home_card_gets_a_cropped_thumbnail_with_empty_alt(client: Client) -> None:
    cover_url, _ = _with_images()
    body = _root(client.get("/").content.decode())

    assert (
        '<span class="work-row-thumb service-thumb" aria-hidden="true">'
        f'<img src="{cover_url}" alt="" loading="lazy"></span>'
    ) in body
    assert body.count("service-thumb") == 1  # the other cards have no image


def test_link_preview_and_json_ld_use_the_cover(client: Client) -> None:
    cover_url, _ = _with_images()
    html = client.get(f"/services/{SLUG}").content.decode()

    assert _tags(html, "og:image") == [cover_url]
    assert _tags(html, "og:image:alt") == ["구조도"]
    assert _tags(html, "og:image:width") == ["2400"]
    assert _tags(html, "og:image:height") == ["950"]
    assert _tags(html, "twitter:card") == ["summary_large_image"]
    assert _ld(html)["image"] == cover_url
    assert _ld(html)["@type"] == "Service"


def test_a_cover_of_unknown_size_leaves_the_size_tags_out(client: Client) -> None:
    offerings.update_service(SLUG, _patch(cover_media_id=_media(901, size=None).pk))
    html = client.get(f"/services/{SLUG}").content.decode()

    assert _tags(html, "og:image:width") == []
    assert " width=" not in re.search(r"<img[^>]*work-cover[^>]*>", _root(html)).group(0)  # type: ignore[union-attr]


def test_null_removes_an_image_and_fields_left_out_stay() -> None:
    _with_images()
    offerings.update_service(SLUG, _patch(name="MCP 연동 구축"))
    assert offerings.get_service(SLUG).cover_media_id == 901

    out = offerings.update_service(SLUG, _patch(cover_media_id=None))
    assert out.cover_media_id is None and out.cover_url == ""
    assert out.figure_media_id == 902  # untouched


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"pk": 903, "done": False}, "cover_media_id"),
        ({"pk": 903, "public": False}, "cover_media_id"),
        ({"pk": 903, "content_type": "video/mp4"}, "cover_media_id"),
    ],
)
def test_a_media_that_is_unfinished_private_or_not_an_image_is_refused(
    kwargs: dict[str, object], field: str
) -> None:
    bad = _media(**kwargs)  # type: ignore[arg-type]
    for key in ("cover_media_id", "figure_media_id"):
        with pytest.raises(Rejected) as caught:
            offerings.update_service(SLUG, _patch(**{key: bad.pk}, figure_alt="x"))
        assert [e.path for e in caught.value.errors] == [key]
    with pytest.raises(Rejected, match="cover_media_id"):
        offerings.update_service(SLUG, _patch(cover_media_id=999999))
    assert Service.objects.get(slug=SLUG).cover_id is None


def test_a_figure_needs_its_alt_text_and_lengths_are_capped() -> None:
    with pytest.raises(Rejected) as caught:
        offerings.update_service(SLUG, _patch(figure_media_id=_media(902).pk))
    assert [e.path for e in caught.value.errors] == ["figure_alt"]
    with pytest.raises(ValueError):
        _patch(cover_alt="가" * 201)
    with pytest.raises(ValueError):
        _patch(figure_caption="가" * 201)


def test_admin_rules_see_the_same_problems() -> None:
    service = Service.objects.get(slug=SLUG)
    service.figure = _media(902)
    assert [e.path for e in offerings.problems(service)] == ["figure_alt"]
    service.figure_alt = "그림"
    service.cover = _media(903, public=False)
    assert [e.path for e in offerings.problems(service)] == ["cover"]


def test_create_service_takes_images_too() -> None:
    cover = _media(901)
    out = offerings.create_service(
        offerings.NewService(
            slug="new-one",
            name="새 서비스",
            summary="요약",
            inquiry_kind="MCP 연동",
            cover_media_id=cover.pk,
            cover_alt="대표",
        )
    )
    assert (out.cover_media_id, out.cover_alt) == (901, "대표")


def test_a_card_image_is_drawn_whole_and_without_one_the_cover_is_cropped(client: Client) -> None:
    cover_url, _ = _with_images()
    card = _media(903, size=(1200, 600))
    card_url = cast(str, media.public_url(card))
    assert next(c for c in offerings.cards() if c["slug"] == SLUG)["cropped"] is True

    out = offerings.update_service(SLUG, _patch(card_media_id=card.pk))
    assert (out.card_media_id, out.card_url) == (903, card_url)
    assert offerings.get_service(SLUG).cover_url == cover_url  # the page keeps its cover
    body = _root(client.get("/").content.decode())
    assert (
        '<span class="work-row-thumb service-thumb service-thumb-whole" aria-hidden="true">'
        f'<img src="{card_url}" alt="" loading="lazy"></span>'
    ) in body
    assert cover_url not in body
    assert body.count("service-thumb-whole") == 1
    page = client.get(f"/services/{SLUG}").content.decode()
    assert card_url not in page  # the detail page never draws the card image

    out = offerings.update_service(SLUG, _patch(card_media_id=None))
    assert out.card_media_id is None and out.card_url == ""
    assert "service-thumb-whole" not in _root(client.get("/").content.decode())


def test_a_card_media_that_is_unfinished_or_private_is_refused() -> None:
    for bad in (_media(903, done=False), _media(904, public=False)):
        with pytest.raises(Rejected) as caught:
            offerings.update_service(SLUG, _patch(card_media_id=bad.pk))
        assert [e.path for e in caught.value.errors] == ["card_media_id"]
    service = Service.objects.get(slug=SLUG)
    service.card = _media(905, content_type="video/mp4")
    assert [e.path for e in offerings.problems(service)] == ["card"]

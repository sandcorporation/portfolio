"""Generated link-preview cards of works and blog posts with a cover (#125)."""

import io
import re
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest
from django.test import Client
from django.utils import timezone
from PIL import Image, ImageDraw
from pytest_django.fixtures import Settings

from adapters.fake_storage import FakeObjectStorage
from adapters.storage import Bucket
from content.models import BlogPost, Media, PortfolioItem
from services import og_card

pytestmark = pytest.mark.django_db


def tags(html: str, key: str) -> list[str]:
    return re.findall(rf'<meta (?:property|name)="{re.escape(key)}" content="([^"]*)"', html)


def cover_png(width: int, height: int) -> bytes:
    image = Image.new("RGB", (width, height), (240, 242, 248))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 40), fill=(200, 30, 30))
    draw.rectangle((10, 60, width - 10, height - 10), outline=(30, 58, 138), width=4)
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


@pytest.fixture(autouse=True)
def cache_dir(tmp_path: Path, settings: Settings) -> Path:
    settings.OG_CACHE_DIR = str(tmp_path / "og")
    return tmp_path / "og"


@pytest.fixture
def composed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Titles of the cards actually composed (a cache hit adds nothing)."""
    titles: list[str] = []
    real = og_card.compose

    def spy(title: str, cover: bytes) -> bytes:
        titles.append(title)
        return real(title, cover)

    monkeypatch.setattr(og_card, "compose", spy)
    return titles


MakeCover = Callable[..., Media]


@pytest.fixture
def make_cover(fake_storage: FakeObjectStorage) -> MakeCover:
    def make(
        width: int = 676, height: int = 483, key: str = "cover.png", data: bytes | None = None
    ) -> Media:
        media = Media.objects.create(
            object_key=key,
            content_type="image/png",
            size=1000,
            original_filename=key,
            uploaded_at=timezone.now(),
        )
        fake_storage.simulate_client_put(
            Bucket.PUBLIC, key, data if data is not None else cover_png(width, height), "image/png"
        )
        return media

    return make


def card_url(html: str) -> str:
    (url,) = tags(html, "og:image")
    return url.removeprefix("http://testserver")


def png_size(content: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(content)).size


@pytest.mark.parametrize("size", [(676, 483), (960, 698), (1440, 900)])
def test_a_work_with_a_cover_gets_a_1200x630_card_under_300kb(
    client: Client, make_cover: MakeCover, size: tuple[int, int], cache_dir: Path
) -> None:
    PortfolioItem.objects.create(slug="w", title="한국어 제목", cover=make_cover(*size))

    html = client.get("/work/w").content.decode()
    url = card_url(html)
    response = client.get(url)

    assert re.fullmatch(r"/og/work/w\.png\?v=[0-9a-f]{10}", url)
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert response["Cache-Control"] == "public, max-age=86400"
    assert response["ETag"]
    body = response.content
    assert png_size(body) == (1200, 630)
    assert len(body) <= 300 * 1024
    assert tags(html, "og:image:width") == ["1200"] and tags(html, "og:image:height") == ["630"]
    assert tags(html, "og:image:alt") == ["한국어 제목"]
    assert tags(html, "twitter:image") == tags(html, "og:image")
    assert '"image": "http://testserver' + url + '"' in html.replace("\\u0026", "&")


def test_a_blog_post_with_a_cover_gets_a_card(client: Client, make_cover: MakeCover) -> None:
    BlogPost.objects.create(
        slug="b",
        title="글",
        status=BlogPost.Status.PUBLISHED,
        published_at=timezone.now() - timedelta(days=1),
        cover=make_cover(),
    )

    html = client.get("/blog/b").content.decode()

    assert re.fullmatch(r"/og/blog/b\.png\?v=[0-9a-f]{10}", card_url(html))
    assert png_size(client.get(card_url(html)).content) == (1200, 630)
    assert tags(html, "og:image:alt") == ["글"]


def test_without_a_cover_the_default_image_stays(client: Client) -> None:
    PortfolioItem.objects.create(slug="n", title="N")

    html = client.get("/work/n").content.decode()

    assert tags(html, "og:image") == ["http://testserver/static/core/og-default.png"]
    assert tags(html, "og:image:alt") == ["Sandcorp 로고"]
    assert client.get("/og/work/n.png").status_code == 200  # the stand-in, kept briefly
    assert client.get("/og/work/n.png")["Cache-Control"] == "public, max-age=60"


def test_the_second_request_uses_the_cache_and_etag_gives_304(
    client: Client, make_cover: MakeCover, composed: list[str], fake_storage: FakeObjectStorage
) -> None:
    PortfolioItem.objects.create(slug="w", title="T", cover=make_cover())

    first = client.get("/og/work/w.png")
    second = client.get("/og/work/w.png")
    again = client.get("/og/work/w.png", headers={"If-None-Match": first["ETag"]})

    assert first.content == second.content
    assert composed == ["T"]
    assert [c for c in fake_storage.calls if c[0] == "download_file"].__len__() == 1
    assert again.status_code == 304


def test_a_lost_cache_directory_is_composed_again(
    client: Client, make_cover: MakeCover, composed: list[str], cache_dir: Path
) -> None:
    PortfolioItem.objects.create(slug="w", title="T", cover=make_cover())
    client.get("/og/work/w.png")
    for file in cache_dir.iterdir():
        file.unlink()

    assert client.get("/og/work/w.png").status_code == 200
    assert composed == ["T", "T"]


def test_a_new_title_or_cover_makes_a_new_card_and_version(
    client: Client, make_cover: MakeCover, composed: list[str], cache_dir: Path
) -> None:
    item = PortfolioItem.objects.create(slug="w", title="One", cover=make_cover())
    v1 = card_url(client.get("/work/w").content.decode())
    client.get(v1)

    item.title = "Two"
    item.save()
    v2 = card_url(client.get("/work/w").content.decode())
    client.get(v2)

    item.cover = make_cover(960, 698, key="other.png")
    item.save()
    v3 = card_url(client.get("/work/w").content.decode())
    client.get(v3)

    assert len({v1, v2, v3}) == 3
    assert composed == ["One", "Two", "Two"]
    assert len(list(cache_dir.iterdir())) == 1  # older cards of the item are dropped


def test_a_broken_cover_falls_back_to_the_default_image_briefly(
    client: Client, make_cover: MakeCover
) -> None:
    PortfolioItem.objects.create(slug="w", title="T", cover=make_cover(data=b"not an image"))

    response = client.get("/og/work/w.png")

    assert response.status_code == 200
    assert response["Cache-Control"] == "public, max-age=60"
    assert png_size(response.content) == (1200, 630)


def test_a_missing_cover_object_falls_back_too(client: Client, make_cover: MakeCover) -> None:
    media = make_cover()
    PortfolioItem.objects.create(slug="w", title="T", cover=media)
    Media.objects.filter(pk=media.pk).update(object_key="gone.png")

    response = client.get("/og/work/w.png")

    assert response.status_code == 200 and response["Cache-Control"] == "public, max-age=60"


def test_hidden_or_unknown_items_are_404_and_old_slugs_redirect(
    client: Client, make_cover: MakeCover
) -> None:
    cover = make_cover()
    PortfolioItem.objects.create(slug="hid", title="H", cover=cover, is_public=True)
    PortfolioItem.objects.filter(slug="hid").update(is_public=False)
    BlogPost.objects.create(slug="draft", title="D", cover=cover)
    item = PortfolioItem.objects.create(slug="old", title="O", cover=cover)
    item.slug = "new"
    item.save()

    assert client.get("/og/work/hid.png").status_code == 404
    assert client.get("/og/work/none.png").status_code == 404
    assert client.get("/og/blog/draft.png").status_code == 404
    assert client.get("/og/other/new.png").status_code == 404
    moved = client.get("/og/work/old.png")
    assert moved.status_code == 301 and moved["Location"] == "/og/work/new.png"


def test_proposal_pages_still_have_no_image_meta(client: Client) -> None:
    assert not tags(client.get("/p/none").content.decode(), "og:image")


def test_a_long_title_and_odd_covers_compose(make_cover: MakeCover) -> None:
    title = "아주 긴 한국어 제목 " * 12 + "Supercalifragilisticexpialidocious" * 3
    rgba = io.BytesIO()
    Image.new("RGBA", (300, 900), (0, 0, 0, 0)).save(rgba, "PNG")  # tall and transparent

    assert png_size(og_card.compose(title, rgba.getvalue())) == (1200, 630)

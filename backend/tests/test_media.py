import re
from datetime import timedelta
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from adapters.fake_storage import FakeObjectStorage
from adapters.storage import Bucket, StorageNotConfigured, get_storage
from content.models import Media, PortfolioItem, SiteProfile
from documents.validation import JSON, InvalidDocument
from services import media as media_service
from services.portfolio import public_cards, public_detail

pytestmark = pytest.mark.django_db


def gallery(*media_ids: int) -> dict[str, JSON]:
    images: list[JSON] = [{"media_id": mid, "alt": "사진"} for mid in media_ids]
    block: dict[str, JSON] = {"id": "g", "type": "gallery", "images": images}
    return {"tabs": [{"id": "main", "title": "본문", "blocks": [block]}]}


def test_presigned_flow_start_put_complete(fake_storage: FakeObjectStorage) -> None:
    ticket = media_service.start_upload("내 사진.png", "image/png", 3, is_public=True)

    media = ticket.media
    assert not media.is_complete
    assert media.original_filename == "내 사진.png"
    assert media.object_key.endswith(".png") and "내" not in media.object_key
    assert ticket.upload.url.startswith(f"https://upload.test/public/{media.object_key}")
    assert ticket.upload.headers == {"Content-Type": "image/png"}
    assert fake_storage.calls == [("presign_put", Bucket.PUBLIC, media.object_key)]

    fake_storage.simulate_client_put(Bucket.PUBLIC, media.object_key, b"abc", "image/png")
    done = media_service.complete_upload(media.pk)

    assert done.is_complete
    assert fake_storage.calls[-1] == ("head", Bucket.PUBLIC, media.object_key)


def test_complete_without_an_uploaded_object_fails_and_stays_pending(
    fake_storage: FakeObjectStorage,
) -> None:
    media = media_service.start_upload("a.png", "image/png", 3, is_public=True).media

    with pytest.raises(media_service.InvalidUpload):
        media_service.complete_upload(media.pk)

    media.refresh_from_db()
    assert not media.is_complete


def test_complete_rejects_and_removes_an_object_that_differs_from_the_promise(
    fake_storage: FakeObjectStorage,
) -> None:
    media = media_service.start_upload("a.png", "image/png", 3, is_public=True).media
    fake_storage.simulate_client_put(Bucket.PUBLIC, media.object_key, b"abcdef", "image/png")

    with pytest.raises(media_service.InvalidUpload):
        media_service.complete_upload(media.pk)

    assert (Bucket.PUBLIC, media.object_key) not in fake_storage.objects
    assert not Media.objects.filter(pk=media.pk).exists()


@pytest.mark.parametrize(
    ("content_type", "size"),
    [("image/svg+xml", 10), ("text/html", 10), ("image/png", 0), ("image/png", 21 * 1024 * 1024)],
)
def test_start_upload_rejects_unsupported_files(
    fake_storage: FakeObjectStorage, content_type: str, size: int
) -> None:
    with pytest.raises(media_service.InvalidUpload):
        media_service.start_upload("x", content_type, size, is_public=True)
    assert Media.objects.count() == 0
    assert fake_storage.calls == []


def test_public_media_has_a_public_url_and_private_media_has_none(
    fake_storage: FakeObjectStorage,
) -> None:
    public = media_service.upload("a.png", "image/png", b"a", is_public=True)
    private = media_service.upload("b.png", "image/png", b"b", is_public=False)

    assert media_service.public_url(public) == f"https://public.test/{public.object_key}"
    assert media_service.public_url(private) is None
    assert (Bucket.PRIVATE, private.object_key) in fake_storage.objects
    assert (Bucket.PUBLIC, private.object_key) not in fake_storage.objects


def test_unfinished_media_has_no_url(fake_storage: FakeObjectStorage) -> None:
    pending = media_service.start_upload("a.png", "image/png", 1, is_public=True).media
    assert media_service.public_url(pending) is None


def test_list_media_hides_unfinished_by_default(fake_storage: FakeObjectStorage) -> None:
    done = media_service.upload("a.png", "image/png", b"a", is_public=True)
    pending = media_service.start_upload("b.png", "image/png", 1, is_public=True).media
    media_service.upload("c.png", "image/png", b"c", is_public=False)

    assert [m.pk for m in media_service.list_media(public_only=True)] == [done.pk]
    assert pending.pk in [m.pk for m in media_service.list_media(complete_only=False)]


def test_gallery_cannot_reference_unfinished_private_or_missing_media(
    fake_storage: FakeObjectStorage,
) -> None:
    pending = media_service.start_upload("a.png", "image/png", 1, is_public=True).media
    private = media_service.upload("b.png", "image/png", b"b", is_public=False)
    ok = media_service.upload("c.png", "image/png", b"c", is_public=True)

    with pytest.raises(InvalidDocument) as caught:
        PortfolioItem(
            slug="s", title="t", body=gallery(pending.pk, private.pk, 99999, ok.pk)
        ).save()

    paths = {e.path: e.reason for e in caught.value.errors}
    assert set(paths) == {f"tabs[0].blocks[0].images[{i}].media_id" for i in range(3)}
    assert "끝나지 않았" in paths["tabs[0].blocks[0].images[0].media_id"]
    assert "공개" in paths["tabs[0].blocks[0].images[1].media_id"]
    assert "없습니다" in paths["tabs[0].blocks[0].images[2].media_id"]
    PortfolioItem(slug="s", title="t", body=gallery(ok.pk)).save()


def test_cover_must_be_finished_public_media(fake_storage: FakeObjectStorage) -> None:
    from django.core.exceptions import ValidationError

    private = media_service.upload("b.png", "image/png", b"b", is_public=False)
    pending = media_service.start_upload("a.png", "image/png", 1, is_public=True).media

    for bad in (private, pending):
        with pytest.raises(ValidationError):
            PortfolioItem(slug="s", title="t", cover=bad).save()


def test_cover_becomes_the_cards_public_url(fake_storage: FakeObjectStorage) -> None:
    cover = media_service.upload("a.png", "image/png", b"a", is_public=True)
    PortfolioItem.objects.create(slug="s", title="t", cover=cover)
    PortfolioItem.objects.create(slug="n", title="n", sort_order=1)

    cards = public_cards()

    assert cards[0]["cover_url"] == f"https://public.test/{cover.object_key}"
    assert cards[1]["cover_url"] == ""


def test_served_documents_get_urls_and_stored_ones_do_not(
    fake_storage: FakeObjectStorage,
) -> None:
    ok = media_service.upload("c.png", "image/png", b"c", is_public=True)
    doc = gallery(ok.pk)
    doc["tabs"][0]["blocks"][0]["images"][0]["url"] = "https://evil.test/x.png"  # type: ignore[index,call-overload]
    item = PortfolioItem.objects.create(slug="g", title="g", body=doc)

    assert item.body["tabs"][0]["blocks"][0]["images"][0]["url"] is None
    detail = public_detail("g")
    assert detail is not None
    image: Any = detail["body"]["tabs"][0]["blocks"][0]["images"][0]  # type: ignore[index,call-overload]
    assert image["url"] == f"https://public.test/{ok.object_key}"


def test_site_runs_without_storage_settings(settings: Any) -> None:
    settings.STORAGE_ENDPOINT_URL = ""
    with pytest.raises(StorageNotConfigured):
        get_storage()
    media = Media.objects.create(
        object_key="k.png", content_type="image/png", size=1, original_filename="k.png"
    )
    from django.utils import timezone

    media.uploaded_at = timezone.now()
    media.save()
    item = PortfolioItem.objects.create(slug="x", title="x")
    PortfolioItem.objects.filter(pk=item.pk).update(cover=media)

    assert public_cards()[0]["cover_url"] == ""
    SiteProfile.load()


def test_presigned_get_is_available_for_private_objects(fake_storage: FakeObjectStorage) -> None:
    private = media_service.upload("b.png", "image/png", b"b", is_public=False)
    url = fake_storage.presign_get(Bucket.PRIVATE, private.object_key, timedelta(minutes=5))
    assert url.startswith("https://download.test/private/")


# --- Django admin ---


@pytest.fixture
def admin_client(client: Client) -> Client:
    user = get_user_model().objects.create_superuser("root", "r@example.com", "pw")
    client.force_login(user)
    return client


def test_admin_upload_stores_the_file_and_it_becomes_a_cover(
    admin_client: Client, fake_storage: FakeObjectStorage
) -> None:
    response = admin_client.post(
        "/admin/content/media/add/",
        {
            "file": SimpleUploadedFile("shot.png", b"PNGDATA", content_type="image/png"),
            "is_public": "on",
        },
    )
    assert response.status_code == 302, response.content[:500]
    media = Media.objects.get()
    assert media.is_complete and media.original_filename == "shot.png"
    assert fake_storage.objects[(Bucket.PUBLIC, media.object_key)] == (b"PNGDATA", "image/png")

    item = PortfolioItem.objects.create(slug="s", title="t", cover=media, is_public=True)
    html = admin_client.get("/").content.decode()
    assert fake_storage.public_url(media.object_key) in html
    assert item.cover == media


def test_admin_upload_private_goes_to_the_private_bucket(
    admin_client: Client, fake_storage: FakeObjectStorage
) -> None:
    admin_client.post(
        "/admin/content/media/add/",
        {"file": SimpleUploadedFile("p.png", b"x", content_type="image/png")},
    )
    media = Media.objects.get()
    assert not media.is_public
    assert (Bucket.PRIVATE, media.object_key) in fake_storage.objects


def test_admin_upload_rejects_wrong_type(
    admin_client: Client, fake_storage: FakeObjectStorage
) -> None:
    response = admin_client.post(
        "/admin/content/media/add/",
        {"file": SimpleUploadedFile("a.html", b"<b>", content_type="text/html")},
    )
    assert response.status_code == 200
    assert "올릴 수 없습니다" in response.content.decode()
    assert Media.objects.count() == 0


def test_admin_upload_without_storage_shows_an_error(admin_client: Client, settings: Any) -> None:
    settings.STORAGE_ENDPOINT_URL = ""
    response = admin_client.post(
        "/admin/content/media/add/",
        {"file": SimpleUploadedFile("a.png", b"x", content_type="image/png")},
    )
    assert response.status_code == 200
    assert re.search("스토리지 설정이 없습니다", response.content.decode())
    assert Media.objects.count() == 0

"""Private media in proposals (#14): what may reference it, how it is frozen and who gets a URL.

The gate is tested at the HTTP edge: /p/<slug>/media/<id> (customer session) and
/preview/<token>/media/<id> (signed preview link).
"""

import time
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client as HttpClient
from django.utils import timezone

from adapters.fake_storage import FakeObjectStorage
from adapters.storage import Bucket
from content.models import Client, Media, PortfolioItem, ProposalRevision
from documents.validation import JSON, InvalidDocument
from services import media as media_service
from services import proposals as svc
from services import publishing
from services.errors import Rejected
from tests.test_portfolio import page_data
from tests.test_proposals import make_draft, preview_url

pytestmark = pytest.mark.django_db

IP = "203.0.113.7"


@pytest.fixture(autouse=True)
def cache_table(db: None) -> Iterator[None]:
    call_command("createcachetable", verbosity=0)
    cache.clear()
    yield
    cache.clear()


def private(content_type: str = "audio/mpeg", *, public: bool = False) -> Media:
    media = Media.objects.create(
        is_public=public,
        object_key=f"{Media.objects.count() + 100}-{content_type.replace('/', '-')}",
        content_type=content_type,
        size=10,
        original_filename="녹음 원본.mp3",
        uploaded_at=timezone.now(),
    )
    return media


def audio_compare(original: int, *tracks: int) -> dict[str, JSON]:
    return {
        "id": "sep",
        "type": "audio-compare",
        "title": "원음과 분리음",
        "original": {"media_id": original, "label": "원음"},
        "tracks": [{"media_id": t, "label": f"화자 {i}"} for i, t in enumerate(tracks)],
    }


def video(media_id: int, poster: int | None = None) -> dict[str, JSON]:
    block: dict[str, JSON] = {"id": "vid", "type": "video", "media_id": media_id}
    if poster is not None:
        block["poster_media_id"] = poster
    return block


def doc(*blocks: dict[str, JSON]) -> dict[str, object]:
    return {"tabs": [{"id": "main", "title": "본문", "blocks": list(blocks)}]}


def draft(**extra: Any) -> svc.ProposalOut:  # Any: NewProposal keyword fields
    """A draft for client NEXT; the first call also creates the client."""
    if not Client.objects.filter(code="NEXT").exists():
        return make_draft(**extra)
    return svc.create_proposal(svc.NewProposal(client_code="NEXT", title="다른 제안", **extra))


def published_with(*blocks: dict[str, JSON]) -> tuple[str, str]:
    p = draft()
    svc.replace_document(p.slug, doc(*blocks))
    result = publishing.publish(p.slug)
    assert result.access_code is not None
    return p.slug, result.access_code


def unlock(client: HttpClient, slug: str, code: str) -> None:
    assert client.post(f"/p/{slug}", {"code": code}, REMOTE_ADDR=IP).status_code == 302


def ask(client: HttpClient, path: str) -> Any:  # Any: the test client's response
    return client.get(path, REMOTE_ADDR=IP)


# --- where private media may be referenced ---


def test_only_proposal_documents_may_reference_private_media(
    fake_storage: FakeObjectStorage,
) -> None:
    a, b, v = private(), private(), private("video/mp4")
    body = doc(audio_compare(a.pk, b.pk), video(v.pk))

    p = make_draft()
    saved: Any = svc.replace_document(p.slug, body).document  # Any: raw JSON
    assert saved["tabs"][0]["blocks"][0]["tracks"][0]["media_id"] == b.pk

    with pytest.raises(InvalidDocument) as caught:
        PortfolioItem(slug="s", title="t", body=body).save()
    assert {e.path for e in caught.value.errors} == {
        "tabs[0].blocks[0].original.media_id",
        "tabs[0].blocks[0].tracks[0].media_id",
        "tabs[0].blocks[1].media_id",
    }


def test_each_reference_must_be_media_of_its_kind(fake_storage: FakeObjectStorage) -> None:
    image, sound, clip = private("image/png"), private(), private("video/mp4")
    p = make_draft()

    with pytest.raises(Rejected) as caught:
        svc.replace_document(
            p.slug, doc(audio_compare(image.pk, clip.pk), video(sound.pk, sound.pk))
        )

    assert {(e.path, e.reason) for e in caught.value.errors} == {
        ("document.tabs[0].blocks[0].original.media_id", f"미디어 {image.pk}는 오디오가 아닙니다"),
        ("document.tabs[0].blocks[0].tracks[0].media_id", f"미디어 {clip.pk}는 오디오가 아닙니다"),
        ("document.tabs[0].blocks[1].media_id", f"미디어 {sound.pk}는 영상이 아닙니다"),
        ("document.tabs[0].blocks[1].poster_media_id", f"미디어 {sound.pk}는 이미지가 아닙니다"),
    }


def test_stored_documents_never_keep_a_url(fake_storage: FakeObjectStorage) -> None:
    a, v = private(), private("video/mp4")
    block = audio_compare(a.pk, a.pk)
    block["original"] = {"media_id": a.pk, "label": "원음", "url": "https://stale"}
    clip = video(v.pk)
    clip["url"] = "https://stale"

    saved = svc.replace_document(make_draft().slug, doc(block, clip))

    assert "https://stale" not in str(saved.document)


# --- frozen as ids, URLs issued when serving ---


def test_a_revision_freezes_media_ids_and_the_page_issues_short_urls(
    fake_storage: FakeObjectStorage,
) -> None:
    a, b, v = private(), private(), private("video/mp4")
    slug, code = published_with(audio_compare(a.pk, b.pk), video(v.pk))
    revision = ProposalRevision.objects.get(proposal__slug=slug)
    frozen: Any = revision.document["tabs"]  # Any: raw JSON
    original = frozen[0]["blocks"][0]["original"]
    assert (original["media_id"], original["url"]) == (a.pk, None)
    assert frozen[0]["blocks"][1]["url"] is None

    client = HttpClient()
    unlock(client, slug, code)
    data = page_data(ask(client, f"/p/{slug}").content.decode())
    blocks = data["document"]["tabs"][0]["blocks"]

    assert (
        blocks[0]["original"]["url"] == f"https://download.test/private/{a.object_key}?expires=600"
    )
    assert blocks[1]["url"] == f"https://download.test/private/{v.object_key}?expires=600"
    assert data["media_endpoint"] == f"/p/{slug}/media"


def test_public_pages_never_get_a_private_url(fake_storage: FakeObjectStorage) -> None:
    a = private()
    blocks: list[JSON] = [audio_compare(a.pk, a.pk)]
    stored: dict[str, JSON] = {"tabs": [{"id": "main", "title": "본문", "blocks": blocks}]}

    resolved: Any = media_service.resolve_document(stored)  # Any: raw JSON

    assert resolved["tabs"][0]["blocks"][0]["original"].get("url") is None
    assert not any(call[0] == "presign_get" for call in fake_storage.calls)


def test_media_deleted_after_publishing_has_no_url(fake_storage: FakeObjectStorage) -> None:
    a, b = private(), private()
    slug, code = published_with(audio_compare(a.pk, b.pk))
    b.delete()  # a published revision protects its media, so the row goes the way a fault would
    client = HttpClient()
    unlock(client, slug, code)

    tracks = page_data(ask(client, f"/p/{slug}").content.decode())["document"]["tabs"][0]["blocks"][
        0
    ]["tracks"]

    assert tracks[0].get("url") is None
    assert ask(client, f"/p/{slug}/media/{b.pk}").status_code == 404


# --- /p/<slug>/media/<id>: the customer's refresh ---


def test_the_customer_gets_a_fresh_url_for_media_in_the_revision(
    fake_storage: FakeObjectStorage,
) -> None:
    a, b = private(), private()
    slug, code = published_with(audio_compare(a.pk, b.pk))
    client = HttpClient()
    unlock(client, slug, code)

    response = ask(client, f"/p/{slug}/media/{b.pk}")

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert response.json() == {"url": f"https://download.test/private/{b.object_key}?expires=600"}
    assert fake_storage.calls[-1] == ("presign_get", Bucket.PRIVATE, b.object_key)


def test_without_a_session_there_is_no_url(fake_storage: FakeObjectStorage) -> None:
    a = private()
    slug, _ = published_with(audio_compare(a.pk, a.pk))

    response = ask(HttpClient(), f"/p/{slug}/media/{a.pk}")

    assert response.status_code == 403
    assert "download.test" not in response.content.decode()


def test_another_proposals_session_does_not_open_this_ones_media(
    fake_storage: FakeObjectStorage,
) -> None:
    a = private()
    slug, _ = published_with(audio_compare(a.pk, a.pk))
    other, other_code = published_with(audio_compare(a.pk, a.pk))
    client = HttpClient()
    unlock(client, other, other_code)
    assert ask(client, f"/p/{other}/media/{a.pk}").status_code == 200

    assert ask(client, f"/p/{slug}/media/{a.pk}").status_code == 403
    # Nor with the other session's cookie copied onto this proposal's name.
    client.cookies[f"proposal_{slug}"] = client.cookies[f"proposal_{other}"].value
    assert ask(client, f"/p/{slug}/media/{a.pk}").status_code == 403


def test_a_session_gets_no_url_for_media_outside_its_revision(
    fake_storage: FakeObjectStorage,
) -> None:
    a, elsewhere, added_later = private(), private(), private()
    slug, code = published_with(audio_compare(a.pk, a.pk))
    # Referenced by the draft after publishing, but not by what the customer was sent.
    svc.replace_document(slug, doc(audio_compare(a.pk, added_later.pk)))
    client = HttpClient()
    unlock(client, slug, code)

    assert ask(client, f"/p/{slug}/media/{elsewhere.pk}").status_code == 404
    assert ask(client, f"/p/{slug}/media/{added_later.pk}").status_code == 404
    assert ask(client, f"/p/{slug}/media/999999").status_code == 404


def test_revoked_and_expired_proposals_give_no_url(
    fake_storage: FakeObjectStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = private()
    slug, code = published_with(audio_compare(a.pk, a.pk))
    p = draft(valid_until=timezone.localdate() + timedelta(days=1))
    svc.replace_document(p.slug, doc(audio_compare(a.pk, a.pk)))
    expiring_code = publishing.publish(p.slug).access_code
    assert expiring_code
    client = HttpClient()
    unlock(client, slug, code)
    unlock(client, p.slug, expiring_code)
    assert ask(client, f"/p/{p.slug}/media/{a.pk}").status_code == 200

    publishing.revoke(slug)
    later = timezone.now() + timedelta(days=3)
    monkeypatch.setattr(timezone, "now", lambda: later)

    assert ask(client, f"/p/{slug}/media/{a.pk}").status_code == 404
    assert ask(client, f"/p/{p.slug}/media/{a.pk}").status_code == 403


def test_a_download_url_saves_under_the_original_name(fake_storage: FakeObjectStorage) -> None:
    v = private("video/mp4")
    block = video(v.pk)
    block["allow_download"] = True
    slug, code = published_with(block)
    client = HttpClient()
    unlock(client, slug, code)

    url = ask(client, f"/p/{slug}/media/{v.pk}?download=1").json()["url"]

    assert url.endswith("&download=녹음 원본.mp3")


# --- /preview/<token>/media/<id>: the owner's preview ---


def test_the_preview_shows_private_media_and_refreshes_through_its_link(
    fake_storage: FakeObjectStorage,
) -> None:
    a, b = private(), private()
    p = make_draft()
    svc.replace_document(p.slug, doc(audio_compare(a.pk, b.pk)))
    link = preview_url(p.slug)
    client = HttpClient()

    data = page_data(client.get(link).content.decode())
    refreshed = client.get(f"{link}/media/{b.pk}")

    assert data["media_endpoint"] == f"{link}/media"
    original = data["document"]["tabs"][0]["blocks"][0]["original"]
    assert original["url"] == f"https://download.test/private/{a.object_key}?expires=600"
    assert refreshed.status_code == 200
    assert refreshed.json()["url"].startswith(f"https://download.test/private/{b.object_key}")


def test_the_preview_link_gates_its_media(
    fake_storage: FakeObjectStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, outside = private(), private()
    p = make_draft()
    svc.replace_document(p.slug, doc(audio_compare(a.pk, a.pk)))
    link = preview_url(p.slug)
    token = link.removeprefix("/preview/")
    client = HttpClient()

    assert client.get(f"{link}/media/{outside.pk}").status_code == 404
    assert client.get(f"/preview/{token[:-2]}xx/media/{a.pk}").status_code == 404
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now + timedelta(minutes=31).total_seconds())
    assert client.get(f"{link}/media/{a.pk}").status_code == 410


# --- uploads ---


def test_audio_and_video_uploads_have_their_own_size_limit() -> None:
    media_service.validate_upload("audio/mpeg", 90 * 1024 * 1024)
    media_service.validate_upload("video/mp4", 100 * 1024 * 1024)
    with pytest.raises(media_service.InvalidUpload):
        media_service.validate_upload("video/mp4", 100 * 1024 * 1024 + 1)
    with pytest.raises(media_service.InvalidUpload):
        media_service.validate_upload("image/png", 21 * 1024 * 1024)
    with pytest.raises(media_service.InvalidUpload):
        media_service.validate_upload("application/pdf", 10)


def test_a_portfolio_cover_must_be_an_image() -> None:
    sound = private(public=True)
    item = PortfolioItem(slug="s", title="t", cover=sound)

    with pytest.raises(ValidationError):
        item.check_cover()

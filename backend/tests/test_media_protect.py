"""Media a published revision or a live page shows cannot be deleted (admin one by one, in bulk,
and the service); draft-only and unused media can, bucket object included."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client as HttpClient

from adapters.fake_storage import FakeObjectStorage
from adapters.storage import Bucket
from content.models import Media, PortfolioItem, ProposalRevision, SiteProfile
from documents.validation import JSON
from services import media as media_service
from services import proposals as svc
from services import publishing
from tests.test_private_media import audio_compare, doc, draft, private, published_with

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client: HttpClient) -> HttpClient:
    user = get_user_model().objects.create_superuser("root", "r@example.com", "pw")
    client.force_login(user)
    return client


def stored(media: Media, fake: FakeObjectStorage) -> Media:
    bucket = Bucket.PUBLIC if media.is_public else Bucket.PRIVATE
    fake.objects[(bucket, media.object_key)] = (b"x", media.content_type)
    return media


def has_object(media: Media, fake: FakeObjectStorage) -> bool:
    bucket = Bucket.PUBLIC if media.is_public else Bucket.PRIVATE
    return (bucket, media.object_key) in fake.objects


def delete_one(client: HttpClient, media: Media) -> str:
    response = client.post(f"/admin/content/media/{media.pk}/delete/", {"post": "yes"}, follow=True)
    return response.content.decode()


def delete_bulk(client: HttpClient, *medias: Media) -> str:
    response = client.post(
        "/admin/content/media/",
        {
            "action": "delete_selected",
            "_selected_action": [m.pk for m in medias],
            "post": "yes",
        },
        follow=True,
    )
    return response.content.decode()


def doc_number_of(slug: str) -> str:
    return ProposalRevision.objects.get(proposal__slug=slug).doc_number


def test_a_published_revisions_media_cannot_be_deleted_anywhere(
    admin_client: HttpClient, fake_storage: FakeObjectStorage
) -> None:
    a = stored(private(), fake_storage)
    b = stored(private(), fake_storage)
    slug, _ = published_with(audio_compare(a.pk, b.pk))
    number = doc_number_of(slug)

    html = delete_one(admin_client, a)
    assert number in html and "지울 수 없습니다" in html
    html = delete_bulk(admin_client, a, b)
    assert number in html and "지울 수 없습니다" in html
    with pytest.raises(media_service.MediaInUse, match=number):
        media_service.delete_media(a)

    assert Media.objects.filter(pk__in=[a.pk, b.pk]).count() == 2
    assert has_object(a, fake_storage) and has_object(b, fake_storage)


def test_a_revoked_revision_still_protects_its_media(
    admin_client: HttpClient, fake_storage: FakeObjectStorage
) -> None:
    a = stored(private(), fake_storage)
    slug, _ = published_with(audio_compare(a.pk, a.pk))
    publishing.revoke(slug)

    assert doc_number_of(slug) in delete_one(admin_client, a)
    assert Media.objects.filter(pk=a.pk).exists()


def test_unused_media_is_deleted_with_its_object_one_by_one_and_in_bulk(
    admin_client: HttpClient, fake_storage: FakeObjectStorage
) -> None:
    one = stored(private(), fake_storage)
    two = stored(private(), fake_storage)
    three = stored(private(), fake_storage)
    kept = stored(private(), fake_storage)
    published_with(audio_compare(kept.pk, kept.pk))

    delete_one(admin_client, one)
    html = delete_bulk(admin_client, two, three, kept)

    assert not Media.objects.filter(pk__in=[one.pk, two.pk, three.pk]).exists()
    assert not any(has_object(m, fake_storage) for m in (one, two, three))
    assert Media.objects.filter(pk=kept.pk).exists() and has_object(kept, fake_storage)
    assert "지울 수 없습니다" in html  # the bulk run said why `kept` stayed


def test_media_only_a_draft_uses_can_be_deleted_with_a_warning(
    admin_client: HttpClient, fake_storage: FakeObjectStorage
) -> None:
    a = stored(private(), fake_storage)
    p = draft()
    svc.replace_document(p.slug, doc(audio_compare(a.pk, a.pk)))

    html = delete_one(admin_client, a)

    assert not Media.objects.filter(pk=a.pk).exists() and not has_object(a, fake_storage)
    assert p.slug in html and "더 이상 제공되지 않습니다" in html


def test_a_portfolio_cover_blocks_deletion(
    admin_client: HttpClient, fake_storage: FakeObjectStorage
) -> None:
    cover = stored(private("image/png", public=True), fake_storage)
    PortfolioItem.objects.create(slug="s", title="대표작", cover=cover)

    html = delete_one(admin_client, cover)

    assert "대표작" in html and "지울 수 없습니다" in html
    assert Media.objects.filter(pk=cover.pk).exists()
    assert PortfolioItem.objects.get().cover_id == cover.pk


def test_a_public_document_gallery_blocks_deletion(
    fake_storage: FakeObjectStorage,
) -> None:
    image = stored(private("image/png", public=True), fake_storage)
    gallery: dict[str, JSON] = {
        "id": "g",
        "type": "gallery",
        "images": [{"media_id": image.pk, "alt": "사진"}],
    }
    profile, _ = SiteProfile.objects.get_or_create()
    profile.company_intro = {"tabs": [{"id": "main", "title": "소개", "blocks": [gallery]}]}
    profile.save()

    with pytest.raises(media_service.MediaInUse, match="회사 프로필"):
        media_service.delete_media(image)


def test_a_frozen_case_cover_counts_as_use(fake_storage: FakeObjectStorage) -> None:
    cover = stored(private("image/png", public=True), fake_storage)
    item = PortfolioItem.objects.create(slug="s", title="사례", cover=cover)
    block: dict[str, JSON] = {"id": "c", "type": "case-ref", "items": [{"item_id": item.pk}]}
    p = draft()
    svc.replace_document(p.slug, doc(block))
    publishing.publish(p.slug)
    item.cover = None  # the page no longer shows it; only the published copy's frozen URL does
    item.save()

    with pytest.raises(media_service.MediaInUse, match=doc_number_of(p.slug)):
        media_service.delete_media(cover)
    assert has_object(cover, fake_storage)


def test_the_admin_change_page_lists_where_a_media_is_used(
    admin_client: HttpClient, fake_storage: FakeObjectStorage
) -> None:
    a = stored(private(), fake_storage)
    unused = stored(private(), fake_storage)
    slug, _ = published_with(audio_compare(a.pk, a.pk))

    used_html = admin_client.get(f"/admin/content/media/{a.pk}/change/").content.decode()
    unused_html = admin_client.get(f"/admin/content/media/{unused.pk}/change/").content.decode()

    assert "사용처" in used_html and doc_number_of(slug) in used_html
    assert "사용 안 함" in unused_html

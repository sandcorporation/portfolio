"""/print/<token>: one revision as the print layout, opened by the PDF renderer."""

import time
from collections.abc import Iterator
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client as HttpClient

from adapters.fake_storage import FakeObjectStorage
from content.models import ProposalRevision
from services import proposals as svc
from services import publishing
from tests.test_portfolio import page_data
from tests.test_private_media import audio_compare, doc, draft, private, video
from tests.test_proposals import preview_url

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def cache_table(db: None) -> Iterator[None]:
    call_command("createcachetable", verbosity=0)
    cache.clear()
    yield
    cache.clear()


def print_url_of_published(fake_storage: FakeObjectStorage) -> tuple[str, str, int, int]:
    """(print path, slug, audio media id, video media id) of a published revision."""
    a, v = private(), private("video/mp4")
    p = draft()
    svc.replace_document(p.slug, doc(audio_compare(a.pk, a.pk), video(v.pk)))
    publishing.publish(p.slug)
    revision = ProposalRevision.objects.get(proposal__slug=p.slug)
    return svc.issue_print_url(revision), p.slug, a.pk, v.pk


def test_the_print_page_shows_the_revision_without_a_customer_session(
    fake_storage: FakeObjectStorage,
) -> None:
    path, slug, a, _ = print_url_of_published(fake_storage)
    token = path.removeprefix("/print/")

    response = HttpClient().get(path)
    data = page_data(response.content.decode())

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert response["X-Robots-Tag"] == "noindex, nofollow"
    assert '<meta name="robots" content="noindex, nofollow">' in response.content.decode()
    assert data["print_mode"] is True
    assert data["preview"] is False
    assert data["csrf_token"] is None
    assert data["public_url"] == f"https://sandcorp.co.kr/p/{slug}"
    assert data["media_endpoint"] == f"/print/{token}/media"
    assert data["revision"]["number"] == 1
    original = data["document"]["tabs"][0]["blocks"][0]["original"]
    assert original["url"].startswith("https://download.test/private/")
    assert original["media_id"] == a


def test_without_a_valid_token_there_is_no_print_page(fake_storage: FakeObjectStorage) -> None:
    path, _, _, _ = print_url_of_published(fake_storage)
    client = HttpClient()

    assert client.get("/print/garbage").status_code == 404
    assert client.get(path[:-2] + "xx").status_code == 404


def test_an_expired_token_is_refused(
    fake_storage: FakeObjectStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _, _, v = print_url_of_published(fake_storage)
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now + timedelta(minutes=11).total_seconds())
    client = HttpClient()

    assert client.get(path).status_code == 410
    assert client.get(f"{path}/media/{v}").status_code == 410


def test_a_preview_token_does_not_open_the_print_page(fake_storage: FakeObjectStorage) -> None:
    p = draft()
    token = preview_url(p.slug).removeprefix("/preview/")

    assert HttpClient().get(f"/print/{token}").status_code == 404
    assert HttpClient().get(f"/print/{token}/media/1").status_code == 404


def test_a_print_token_does_not_open_the_preview(fake_storage: FakeObjectStorage) -> None:
    path, _, _, _ = print_url_of_published(fake_storage)
    token = path.removeprefix("/print/")

    assert HttpClient().get(f"/preview/{token}").status_code == 404


def test_the_print_token_issues_urls_only_for_media_in_its_revision(
    fake_storage: FakeObjectStorage,
) -> None:
    path, _, a, v = print_url_of_published(fake_storage)
    outside = private()
    client = HttpClient()

    ok = client.get(f"{path}/media/{v}")
    assert ok.status_code == 200
    assert ok.json()["url"].startswith("https://download.test/private/")
    assert client.get(f"{path}/media/{a}").status_code == 200
    assert client.get(f"{path}/media/{outside.pk}").status_code == 404


def test_robots_keeps_crawlers_off_print_pages() -> None:
    assert "Disallow: /print/" in HttpClient().get("/robots.txt").content.decode()

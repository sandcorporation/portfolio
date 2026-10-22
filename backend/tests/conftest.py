"""Shared fixtures for backend HTTP-boundary tests.

Static fixture files live in tests/fixtures/.
Fake adapters are fixtures here (fake_storage, auth_server, notifier).
"""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from django.core.management.color import no_style
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from pytest_django.fixtures import Settings

from adapters.fake_jwks import FakeAuthServer
from adapters.fake_notify import FakeNotifier
from adapters.fake_storage import FakeObjectStorage
from content.models import Media, PortfolioItem
from core.vite import _read_manifest
from documents.validation import JSON
from oauth.tokens import JwksCache

FIXTURES = Path(__file__).parent / "fixtures"
# Fixtures shared with the frontend renderer tests live at the repo root.
SHARED_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture
def example_document(db: None) -> dict[str, JSON]:
    """The GanadaTrade proposal as a block document. The frontend renderer tests read it too.

    Its gallery points at media 1-3 (images), its audio-compare blocks at 4-6, 8-12 and 13-15
    (audio), its videos at 7 and 16 with posters 1 and 2, and its case-ref at portfolio items
    1-2, so they exist (finished, public media; one hidden item) while the test runs.
    """
    for media_id in (1, 2, 3):
        Media.objects.create(
            pk=media_id,
            object_key=f"example-{media_id}.png",
            content_type="image/png",
            size=1,
            original_filename=f"example-{media_id}.png",
            uploaded_at=timezone.now(),
        )
    audio = (4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15)
    for media_id, content_type in [(i, "audio/mpeg") for i in audio] + [
        (7, "video/mp4"),
        (16, "video/mp4"),
    ]:
        Media.objects.create(
            pk=media_id,
            object_key=f"example-{media_id}",
            content_type=content_type,
            size=1,
            original_filename=f"example-{media_id}",
            uploaded_at=timezone.now(),
        )
    PortfolioItem.objects.create(pk=1, slug="ramaba", title="라마바 통화 분석")
    PortfolioItem.objects.create(pk=2, slug="hidden-case", title="비공개 사례", is_public=False)
    # Rows with explicit pks leave the id sequences at 1, so the next auto-pk insert in a test
    # would collide with them (order-dependent failures). Move the sequences past them.
    with connection.cursor() as cursor:
        for sql in connection.ops.sequence_reset_sql(no_style(), [Media, PortfolioItem]):
            cursor.execute(sql)
    path = SHARED_FIXTURES / "documents" / "example-proposal.json"
    data: dict[str, JSON] = json.loads(path.read_text(encoding="utf-8"))
    return data


@pytest.fixture(autouse=True)
def vite_manifest() -> Iterator[None]:
    """Serve the shell against a fixed Vite manifest so tests never need a frontend build."""
    _read_manifest.cache_clear()
    with override_settings(
        VITE_DEV_SERVER_URL="", VITE_MANIFEST_PATH=FIXTURES / "vite-manifest.json"
    ):
        yield
    _read_manifest.cache_clear()


@pytest.fixture
def fake_storage(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStorage:
    """Replace the object storage every service uses; assert on its `calls` and `objects`."""
    storage = FakeObjectStorage()
    monkeypatch.setattr("services.media.get_storage", lambda: storage)
    monkeypatch.setattr("content.admin.get_storage", lambda: storage)
    return storage


@pytest.fixture
def auth_server(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> FakeAuthServer:
    """A fake sandcorp-auth: sign tokens with `auth_server.issue()` / `.bearer()`.

    Its JWKS, frozen clock and token endpoint replace the real ones; `AUTH_OWNER_SUB` is its
    owner and `AUTH_CLIENT_ID`/`AUTH_CLIENT_SECRET` its registered admin-login client.
    """
    server = FakeAuthServer()
    cache = JwksCache(server.fetch_jwks, server.clock)
    settings.AUTH_OWNER_SUB = server.owner_sub
    settings.AUTH_CLIENT_ID = server.client_id
    settings.AUTH_CLIENT_SECRET = server.client_secret
    monkeypatch.setattr("oauth.login.get_exchange_code", lambda: server.exchange_code)
    monkeypatch.setattr("oauth.bearer.get_jwks_cache", lambda: cache)
    monkeypatch.setattr("oauth.bearer.get_clock", lambda: server.clock)
    return server


@pytest.fixture
def notifier(monkeypatch: pytest.MonkeyPatch) -> FakeNotifier:
    """Replace the owner-alert channel; assert on `notifier.sent`, set `notifier.failing`."""
    fake = FakeNotifier()
    monkeypatch.setattr("services.inquiries.get_notifier", lambda: fake)
    return fake

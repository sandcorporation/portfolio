"""Shared fixtures for backend HTTP-boundary tests.

Static fixture files live in tests/fixtures/. Fake adapters are fixtures here (fake_storage).
"""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from django.test import override_settings
from django.utils import timezone

from adapters.fake_storage import FakeObjectStorage
from content.models import Media
from core.vite import _read_manifest
from documents.validation import JSON

FIXTURES = Path(__file__).parent / "fixtures"
# Fixtures shared with the frontend renderer tests live at the repo root.
SHARED_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture
def example_document(db: None) -> dict[str, JSON]:
    """The GanadaTrade proposal as a block document. The frontend renderer tests read it too.

    Its gallery points at media 1-3, so they exist (finished, public) while the test runs.
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

"""Shared fixtures for backend HTTP-boundary tests.

Static fixture files live in tests/fixtures/.
Fake adapters are fixtures here (fake_storage, auth_server, notifier).
"""

import importlib
import json
import os
import resource
import time
from collections.abc import Generator, Iterator
from pathlib import Path

import pytest
from _pytest.reports import TestReport
from _pytest.runner import CallInfo
from django.core.management.color import no_style
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from pytest_django.fixtures import Settings
from sandcorp_authkit.testing import FakeJwks, FakeTokenEndpoint, FixedClock

from adapters import foresight as foresight_adapter
from adapters import metrics as metrics_adapter
from adapters import youtube as youtube_adapter
from adapters.fake_foresight import FakeForesight
from adapters.fake_metrics import FakeMetrics
from adapters.fake_notify import FakeNotifier
from adapters.fake_renderer import FakeRenderer
from adapters.fake_storage import FakeObjectStorage
from adapters.fake_youtube import FakeYoutube
from content.models import Media, PortfolioItem
from core.vite import _read_manifest
from documents.validation import JSON
from oauth import auth
from tests.site_auth import SiteAuth

_CPU_SPENT = pytest.StashKey[float]()
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
    monkeypatch.setattr("services.pdf.get_storage", lambda: storage)
    monkeypatch.setattr("services.og_card.get_storage", lambda: storage)
    return storage


@pytest.fixture
def auth_server(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> SiteAuth:
    """A fake sandcorp-auth: sign tokens with `auth_server.issue()` / `.bearer()`.

    The package's fake JWKS, fixed clock and token endpoint replace the real ones through the
    `oauth.auth` seams; `AUTH_OWNER_SUB` is `owner` and `AUTH_CLIENT_ID`/`AUTH_CLIENT_SECRET`
    the registered admin-login client.
    """
    clock = FixedClock()
    jwks = FakeJwks()
    cache = jwks.cache(clock)
    settings.AUTH_OWNER_SUB = "owner"
    settings.AUTH_CLIENT_ID = "portfolio-admin"
    settings.AUTH_CLIENT_SECRET = "test-client-secret"
    endpoint = FakeTokenEndpoint(jwks, clock, client_id="portfolio-admin")
    monkeypatch.setattr(auth, "clock", clock)
    monkeypatch.setattr(auth, "jwks_cache", lambda: cache)
    monkeypatch.setattr(auth, "token_transport", lambda: endpoint)
    return SiteAuth(jwks, endpoint, clock)


@pytest.fixture
def notifier(monkeypatch: pytest.MonkeyPatch) -> FakeNotifier:
    """Replace the owner-alert channel; assert on `notifier.sent`, set `notifier.failing`."""
    fake = FakeNotifier()
    monkeypatch.setattr("services.inquiries.get_notifier", lambda: fake)
    monkeypatch.setattr("services.proposal_events.get_notifier", lambda: fake)
    return fake


@pytest.fixture
def renderer(monkeypatch: pytest.MonkeyPatch) -> FakeRenderer:
    """Replace the PDF renderer; assert on `renderer.urls`, set `renderer.failing`."""
    fake = FakeRenderer()
    monkeypatch.setattr("services.pdf.get_renderer", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def foresight() -> Iterator[FakeForesight]:
    """No test reaches news.sandcorp.co.kr: the Foresight gateway is always this fake.
    Assert on `foresight.calls`, set `foresight.failing` or `foresight.articles`."""
    fake = FakeForesight()
    foresight_adapter.set_gateway(fake)
    yield fake
    foresight_adapter.set_gateway(None)


@pytest.fixture(autouse=True)
def youtube() -> Iterator[FakeYoutube]:
    """No test reaches youtube.com: the oEmbed gateway is always this fake.
    Set `youtube.titles` or `youtube.failing`, assert on `youtube.calls`."""
    fake = FakeYoutube()
    youtube_adapter.set_gateway(fake)
    yield fake
    youtube_adapter.set_gateway(None)


@pytest.fixture(autouse=True)
def metrics() -> Iterator[FakeMetrics]:
    """No test reaches metrics.sandcorp.co.kr: the metrics gateway is always this fake.
    Assert on `metrics.calls`, set `metrics.failing` or `metrics.data`."""
    fake = FakeMetrics()
    metrics_adapter.set_gateway(fake)
    yield fake
    metrics_adapter.set_gateway(None)


# --- 시험 하나의 CPU 한도 (#137) -----------------------------------------------------------
# 시험 본문(call 단계)의 CPU 초(이 프로세스 + 자식)를 재서 한도를 넘고 통과한 시험은 실패로 바꾼다.
# 준비·정리(픽스처)는 재지 않는다. 한도를 올리지 않고 원인을 줄인다. 시험별 예외는 두지 않는다.
# 환경변수 PORTFOLIO_TEST_CPU_LIMIT(초, 0이면 끔)로 환경별로만
# 조정한다. junit에는 `cpu_seconds`가 남는다.
_CPU_LIMIT_SECONDS = float(os.environ.get("PORTFOLIO_TEST_CPU_LIMIT", "1.0"))


def _cpu_seconds() -> float:
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return time.process_time() + children.ru_utime + children.ru_stime


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None]:
    started = _cpu_seconds()
    try:
        return (yield)
    finally:
        item.stash[_CPU_SPENT] = _cpu_seconds() - started


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: CallInfo[None]
) -> Generator[None, TestReport, TestReport]:
    report = yield
    spent = item.stash.get(_CPU_SPENT, None)
    if report.when == "call" and spent is not None:
        # junitxml은 teardown 보고서의 user_properties를 쓰고
        # pytest는 보고서마다 item의 목록을 복사한다 — item과 report 양쪽에 넣어야 junit에 남는다.
        item.user_properties.append(("cpu_seconds", round(spent, 3)))
        report.user_properties.append(("cpu_seconds", round(spent, 3)))
        if _CPU_LIMIT_SECONDS > 0 and spent > _CPU_LIMIT_SECONDS and report.passed:
            report.outcome = "failed"
            report.longrepr = (
                f"시험 본문이 CPU {spent:.2f}초를 썼다 — 한도 {_CPU_LIMIT_SECONDS:.2f}초"
                " (PORTFOLIO_TEST_CPU_LIMIT). 원인을 찾아 줄인다; 한도를 늘리지 않는다."
            )
    return report


@pytest.fixture
def services(db: None) -> None:
    """The service rows the data migration put in (content 0025, 0029). A transactional
    test elsewhere flushes the tables, so this puts them back the migration's own way."""
    from django.apps import apps

    for name in ("0025_service", "0029_service_ai_work_automation"):
        importlib.import_module(f"content.migrations.{name}").seed(apps, None)

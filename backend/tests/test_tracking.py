"""Viewing trail and owner alerts (#18), through the customer's HTTP edges."""

import json
from collections.abc import Iterator
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client as HttpClient
from django.urls import reverse
from django.utils import timezone

from adapters.fake_notify import ExplodingNotifier, FakeNotifier
from adapters.fake_renderer import FakeRenderer
from adapters.fake_storage import FakeObjectStorage
from content.models import Proposal, ProposalEvent
from services import proposal_events as events
from services import proposals as svc
from services import publishing
from services.errors import NotFound
from tests.test_proposals import make_draft, preview_url
from tests.test_publishing import published, screen, unlock

pytestmark = pytest.mark.django_db

IP = "203.0.113.7"


@pytest.fixture(autouse=True)
def cache_table(db: None) -> Iterator[None]:
    call_command("createcachetable", verbosity=0)
    cache.clear()
    yield
    cache.clear()


def kinds(slug: str) -> list[str]:
    return [e.kind for e in events.list_events(slug)]


def opened(slug: str, code: str, ua: str = "Mozilla/5.0 Test") -> HttpClient:
    client = HttpClient(HTTP_USER_AGENT=ua)
    unlock(client, slug, code)
    return client


def titles(notifier: FakeNotifier) -> list[str]:
    return [n.title for n in notifier.sent]


def test_the_first_view_of_a_revision_alerts_once_however_often_it_is_opened(
    notifier: FakeNotifier,
) -> None:
    slug, code = published()
    client = opened(slug, code)
    for _ in range(4):
        screen(client, slug)
    other_device = opened(slug, code, ua="Safari")
    screen(other_device, slug)

    assert titles(notifier) == ["가나다상사(NEXT)가 v1을 처음 열었습니다"]
    alert = notifier.sent[0]
    doc_number = publishing.latest_revision(Proposal.objects.get(slug=slug)).doc_number  # type: ignore[union-attr]
    assert doc_number in [f.value for f in alert.fields]
    assert sum(e.first for e in ProposalEvent.objects.filter(proposal__slug=slug)) == 1


def test_a_new_revision_alerts_again_on_its_first_view(notifier: FakeNotifier) -> None:
    slug, code = published()
    client = opened(slug, code)
    screen(client, slug)
    publishing.publish(slug)  # v2; the session stays valid (same code)
    screen(client, slug)
    screen(client, slug)

    assert len(notifier.sent) == 2
    assert "v1" in notifier.sent[0].title and "v2" in notifier.sent[1].title


def test_reloads_within_half_an_hour_are_one_view_and_a_later_return_is_another() -> None:
    slug, code = published()
    client = opened(slug, code)
    screen(client, slug)
    screen(client, slug)
    assert kinds(slug).count("viewed") == 1

    ProposalEvent.objects.filter(kind="viewed").update(
        created_at=timezone.now() - timedelta(minutes=events.VIEW_DEDUPE_SECONDS // 60 + 1)
    )
    screen(client, slug)
    assert kinds(slug).count("viewed") == 2
    assert sum(e.first for e in ProposalEvent.objects.all()) == 1


def test_code_tries_are_logged_with_ip_agent_and_revision() -> None:
    slug, code = published()
    client = HttpClient(HTTP_USER_AGENT="X" * 400)
    unlock(client, slug, "WRONG234")
    unlock(client, slug, code)
    screen(client, slug)

    assert kinds(slug) == ["code_wrong", "code_ok", "viewed"]
    wrong = ProposalEvent.objects.filter(kind="code_wrong").get()
    assert wrong.ip == IP and wrong.revision is not None and wrong.revision.number == 1
    assert len(wrong.user_agent) == 255


def test_blocking_is_logged_and_alerts_once(notifier: FakeNotifier) -> None:
    slug, code = published()
    client = HttpClient()
    for _ in range(7):
        unlock(client, slug, "WRONG234")

    assert kinds(slug).count("blocked") == 1
    assert kinds(slug).count("code_wrong") == 5
    assert len(notifier.sent) == 1
    assert "차단" in notifier.sent[0].title and IP in [f.value for f in notifier.sent[0].fields]


def test_a_pdf_download_is_logged_and_alerts(
    notifier: FakeNotifier, fake_storage: FakeObjectStorage, renderer: FakeRenderer
) -> None:
    slug, code = published()
    client = opened(slug, code)
    call_command("pdf_worker", "--once")
    notifier.sent.clear()

    assert client.get(f"/p/{slug}/pdf", REMOTE_ADDR=IP).status_code == 302
    assert HttpClient().get(f"/p/{slug}/pdf").status_code == 403  # no session: nothing recorded

    assert kinds(slug).count("pdf") == 1
    assert len(notifier.sent) == 1 and "PDF" in notifier.sent[0].title


def test_preview_and_print_leave_no_trace(
    notifier: FakeNotifier, fake_storage: FakeObjectStorage
) -> None:
    p = make_draft()
    client = HttpClient()
    assert client.get(preview_url(p.slug)).status_code == 200
    publishing.publish(p.slug)
    revision = publishing.latest_revision(Proposal.objects.get(slug=p.slug))
    assert revision is not None
    assert client.get(svc.issue_print_url(revision)).status_code == 200

    assert ProposalEvent.objects.count() == 0
    assert notifier.sent == []


def post_tab(client: HttpClient, slug: str, tab: object, csrf: str = "") -> int:
    return client.post(
        f"/p/{slug}/tab",
        json.dumps({"tab": tab}),
        content_type="application/json",
        REMOTE_ADDR=IP,
        HTTP_X_CSRFTOKEN=csrf,
    ).status_code


def test_tab_switches_are_logged_for_a_customer_with_a_session_only() -> None:
    slug, code = published()
    assert post_tab(HttpClient(), slug, "company") == 403
    client = opened(slug, code)

    assert post_tab(client, slug, "company") == 204
    assert post_tab(client, slug, "nope") == 400
    assert post_tab(client, slug, 5) == 400
    tab = ProposalEvent.objects.get(kind="tab")
    assert tab.tab_id == "company" and tab.revision is not None and tab.ip == IP


def test_tab_reports_are_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(events, "TAB_LIMIT", 3)
    slug, code = published()
    client = opened(slug, code)
    codes = [post_tab(client, slug, "estimate") for _ in range(5)]
    assert codes == [204, 204, 204, 429, 429]


def test_the_page_tells_the_browser_where_to_report_tabs() -> None:
    slug, code = published()
    client = opened(slug, code)
    assert screen(client, slug)["tab_endpoint"] == f"/p/{slug}/tab"


def test_a_failing_or_exploding_alert_channel_does_not_fail_the_customer(
    notifier: FakeNotifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    notifier.failing = True
    slug, code = published()
    client = opened(slug, code)
    assert screen(client, slug)["title"]

    monkeypatch.setattr("services.proposal_events.get_notifier", lambda: ExplodingNotifier())
    publishing.publish(slug)
    assert screen(client, slug)["title"]
    for _ in range(5):
        assert unlock(HttpClient(), slug, "WRONG234").status_code in (400, 429)


def test_list_events_is_in_time_order_and_unknown_proposals_are_not_found() -> None:
    slug, code = published()
    client = opened(slug, code)
    screen(client, slug)
    post_tab(client, slug, "company")

    listed = events.list_events(slug)
    assert [e.kind for e in listed] == ["code_ok", "viewed", "tab"]
    assert [e.at for e in listed] == sorted(e.at for e in listed)
    assert listed[1].revision == 1 and listed[1].doc_number
    with pytest.raises(NotFound):
        events.list_events("missing")


def test_admin_shows_the_trail_oldest_first() -> None:
    slug, code = published()
    client = opened(slug, code)
    screen(client, slug)
    post_tab(client, slug, "company")
    ProposalEvent.objects.filter(kind="code_ok").update(
        created_at=timezone.now() - timedelta(hours=2)
    )
    ProposalEvent.objects.filter(kind="viewed").update(
        created_at=timezone.now() - timedelta(hours=1)
    )

    staff = get_user_model().objects.create_superuser("owner", "o@example.com", "pw")
    admin = HttpClient()
    admin.force_login(staff)
    pk = Proposal.objects.get(slug=slug).pk
    html = admin.get(reverse("admin:content_proposal_change", args=[pk])).content.decode()
    ok = html.index("코드 인증 성공")
    viewed = html.index(">열람<", ok)
    tab = html.index("탭 전환", viewed)
    assert ok < viewed < tab
    assert admin.get(reverse("admin:content_proposalevent_changelist")).status_code == 200

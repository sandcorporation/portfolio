"""Inquiries over HTTP: the browser form, the news site's server-to-server post, the admin."""

from collections.abc import Iterator, Mapping

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client
from pytest_django.fixtures import Settings

from adapters.fake_notify import ExplodingNotifier, FakeNotifier
from adapters.notify import Notification, discord_payload
from content.models import Inquiry
from services import offerings

URL = "/api/inquiries"
FORM = {
    "name": "김대표",
    "company": "가나다상사",
    "contact": "010-1234-5678",
    "message": "견적 문의",
}
SECRET = "shared-secret-value"


@pytest.fixture(autouse=True)
def cache_table(db: None) -> Iterator[None]:
    call_command("createcachetable", verbosity=0)
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def secret(settings: Settings) -> str:
    settings.INQUIRY_SHARED_SECRET = SECRET
    return SECRET


def post(
    client: Client, body: Mapping[str, object], ip: str = "203.0.113.5", **headers: str
) -> int:
    return client.post(
        URL, body, content_type="application/json", headers={"x-forwarded-for": ip, **headers}
    ).status_code


def test_a_browser_inquiry_is_saved_and_alerted_once(
    client: Client, notifier: FakeNotifier
) -> None:
    assert post(client, FORM) == 201

    saved = Inquiry.objects.get()
    assert (saved.name, saved.company, saved.site, saved.kind) == (
        "김대표",
        "가나다상사",
        "portfolio",
        "문의",
    )
    assert saved.handled_at is None
    (alert,) = notifier.sent
    text = " ".join([alert.title, alert.text, *(f"{f.name} {f.value}" for f in alert.fields)])
    for expected in ("portfolio", "문의", "김대표", "가나다상사", "010-1234-5678", "견적 문의"):
        assert expected in text


def test_a_filled_honeypot_looks_successful_but_keeps_and_alerts_nothing(
    client: Client, notifier: FakeNotifier
) -> None:
    assert post(client, {**FORM, "website": "http://spam.example"}) == 201

    assert Inquiry.objects.count() == 0
    assert notifier.sent == []


def test_past_the_limit_an_ip_is_refused_and_others_are_not(
    client: Client, notifier: FakeNotifier, settings: Settings
) -> None:
    settings.INQUIRY_RATE_LIMIT = 2
    assert [post(client, FORM) for _ in range(3)] == [201, 201, 429]
    assert Inquiry.objects.count() == 2
    assert len(notifier.sent) == 2

    assert post(client, FORM, ip="198.51.100.9") == 201


def test_a_failing_discord_still_gives_a_success_receipt(
    client: Client, notifier: FakeNotifier
) -> None:
    notifier.failing = True
    assert post(client, FORM) == 201
    assert Inquiry.objects.count() == 1


def test_a_crashing_notifier_does_not_turn_into_a_server_error(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("services.inquiries.get_notifier", lambda: ExplodingNotifier())
    assert post(client, FORM) == 201
    assert Inquiry.objects.count() == 1


def test_the_news_site_with_the_secret_names_its_site_and_kind(
    client: Client, notifier: FakeNotifier, secret: str, settings: Settings
) -> None:
    settings.INQUIRY_RATE_LIMIT = 1
    body = {**FORM, "site": "news", "kind": "제안", "website": "filled-by-nobody-but-ignored"}
    statuses = [post(client, body, **{"x-inquiry-secret": secret}) for _ in range(2)]

    assert statuses == [201, 201]  # the limit and the honeypot do not apply to it
    assert {(i.site, i.kind) for i in Inquiry.objects.all()} == {("news", "제안")}
    assert "news" in notifier.sent[0].title and "제안" in notifier.sent[0].title


@pytest.mark.parametrize("headers", [{}, {"x-inquiry-secret": "wrong"}])
def test_without_a_valid_secret_the_site_is_ignored(
    client: Client, notifier: FakeNotifier, secret: str, headers: dict[str, str]
) -> None:
    assert post(client, {**FORM, "site": "news"}, **headers) == 201
    assert Inquiry.objects.get().site == "portfolio"


def test_an_unset_secret_setting_never_matches(
    client: Client, notifier: FakeNotifier, settings: Settings
) -> None:
    settings.INQUIRY_SHARED_SECRET = ""
    for header in ("", "anything"):
        assert (
            post(client, {**FORM, "site": "news", "website": "bot"}, **{"x-inquiry-secret": header})
            == 201
        )
    assert Inquiry.objects.count() == 0  # honeypot still applied: nobody was trusted


@pytest.mark.parametrize(
    "bad",
    [{"name": ""}, {"contact": " "}, {"message": ""}, {"kind": "광고"}, {"message": "x" * 4001}],
)
def test_invalid_input_is_a_client_error_and_not_saved(
    client: Client, notifier: FakeNotifier, secret: str, bad: dict[str, str]
) -> None:
    status = post(client, {**FORM, **bad}, **{"x-inquiry-secret": secret})
    assert 400 <= status < 500
    assert post(client, {**FORM, **bad}) in (400, 422)
    assert Inquiry.objects.count() == 0
    assert notifier.sent == []


def test_a_bad_site_name_from_the_news_server_is_refused(client: Client, secret: str) -> None:
    status = post(client, {**FORM, "site": "News Site!"}, **{"x-inquiry-secret": secret})
    assert status == 422


def test_a_cross_site_browser_post_is_refused(client: Client, notifier: FakeNotifier) -> None:
    assert post(client, FORM, origin="https://evil.example") == 403
    assert post(client, FORM, origin="http://testserver") == 201
    assert Inquiry.objects.count() == 1


def test_a_form_encoded_post_is_refused(client: Client) -> None:
    response = client.post(URL, FORM)  # what a hostile <form> on another site can send
    assert response.status_code in (400, 403, 415, 422)
    assert Inquiry.objects.count() == 0


def test_the_discord_payload_cannot_ping_anyone_and_respects_limits() -> None:
    payload = discord_payload(Notification(title="t" * 500, text="@everyone " * 1000))
    assert payload["allowed_mentions"] == {"parse": []}
    embed = payload["embeds"][0]  # type: ignore[index]
    assert len(embed["title"]) <= 256 and len(embed["description"]) <= 4096


@pytest.fixture
def owner_client(client: Client) -> Client:
    User.objects.create_superuser("owner", "o@example.com", "correct-horse-battery")
    client.login(username="owner", password="correct-horse-battery")
    return client


def test_admin_shows_site_and_kind_and_filters_unhandled(owner_client: Client) -> None:
    open_one = Inquiry.objects.create(
        site="news", kind="제안", name="열린", contact="a", message="m"
    )
    done = Inquiry.objects.create(name="끝난", contact="b", message="m")
    from services.inquiries import mark_handled

    mark_handled(done.pk)

    page = owner_client.get("/admin/content/inquiry/").content.decode()
    assert "열린" in page and "끝난" in page and "news" in page and "제안" in page

    filtered = owner_client.get("/admin/content/inquiry/?handled=no").content.decode()
    assert "열린" in filtered and "끝난" not in filtered
    assert open_one.pk


def test_admin_action_marks_inquiries_handled(owner_client: Client) -> None:
    a = Inquiry.objects.create(name="a", contact="c", message="m")
    b = Inquiry.objects.create(name="b", contact="c", message="m")
    owner_client.post(
        "/admin/content/inquiry/",
        {"action": "mark_done", "_selected_action": [a.pk]},
        follow=True,
    )
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.handled_at is not None and b.handled_at is None
    first = a.handled_at

    owner_client.post(
        "/admin/content/inquiry/", {"action": "mark_done", "_selected_action": [a.pk]}
    )
    a.refresh_from_db()
    assert a.handled_at == first


@pytest.mark.parametrize("kind", ["문의", "제안", "신규 개발", "유지보수", "기타"])
def test_every_inquiry_kind_is_accepted_saved_and_named_in_the_alert(
    client: Client, notifier: FakeNotifier, kind: str
) -> None:
    assert post(client, {**FORM, "kind": kind}) == 201

    assert Inquiry.objects.get().kind == kind
    assert kind in notifier.sent[0].title
    assert ("구분", kind) in [(f.name, f.value) for f in notifier.sent[0].fields]


def test_an_unknown_kind_is_still_refused_and_the_default_stays_inquiry(client: Client) -> None:
    assert post(client, {**FORM, "kind": "광고"}) == 422
    assert Inquiry.objects.count() == 0
    without_kind = {k: v for k, v in FORM.items() if k != "kind"}
    assert post(client, without_kind) == 201
    assert Inquiry.objects.get().kind == Inquiry.Kind.INQUIRY


def test_admin_lists_and_filters_the_new_kinds(owner_client: Client) -> None:
    Inquiry.objects.create(kind="신규 개발", name="가나", contact="a", message="m")
    Inquiry.objects.create(kind="문의", name="다라", contact="b", message="m")

    page = owner_client.get("/admin/content/inquiry/").content.decode()
    assert "신규 개발" in page and "유지보수" in page  # list rows and the filter's choices

    filtered = owner_client.get("/admin/content/inquiry/", {"kind": "신규 개발"}).content.decode()
    assert "가나" in filtered and "다라" not in filtered


@pytest.mark.parametrize(
    "offering", [*offerings.OFFERINGS, *offerings.CARD_ONLY], ids=lambda o: o["slug"]
)
def test_each_offering_is_an_inquiry_kind_by_its_name(
    client: Client, notifier: FakeNotifier, offering: offerings.Offering | offerings.OfferingCard
) -> None:
    assert offering["inquiry_kind"] in Inquiry.Kind.values
    assert post(client, {**FORM, "kind": offering["inquiry_kind"]}) == 201
    saved = Inquiry.objects.get()
    assert saved.kind == offering["inquiry_kind"]
    assert offering["inquiry_kind"] in notifier.sent[0].title
    assert len(saved.kind) == len(offering["inquiry_kind"])  # not cut by the column


def test_admin_shows_an_offering_kind(owner_client: Client) -> None:
    Inquiry.objects.create(kind="Claude Code 자동화", name="마바", contact="c", message="m")
    page = owner_client.get("/admin/content/inquiry/").content.decode()
    assert "Claude Code 자동화" in page

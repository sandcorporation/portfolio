"""Publishing, revisions and the customer's way in (/p/<slug>), at the HTTP and service edges."""

import re
import time
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client as HttpClient
from django.urls import reverse

from content.models import Proposal, ProposalRevision
from services import proposals as svc
from services import publishing
from services.errors import Conflict
from tests.test_portfolio import page_data
from tests.test_proposals import make_draft

pytestmark = pytest.mark.django_db

CODE = re.compile(r"^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{8}$")


@pytest.fixture(autouse=True)
def cache_table(db: None) -> Iterator[None]:
    call_command("createcachetable", verbosity=0)
    cache.clear()
    yield
    cache.clear()


def url(slug: str) -> str:
    return f"/p/{slug}"


def published(**extra: Any) -> tuple[str, str]:  # Any: NewProposal keyword fields
    """A published proposal: (slug, access code)."""
    p = make_draft(**extra)
    result = publishing.publish(p.slug)
    assert result.access_code is not None
    return p.slug, result.access_code


def unlock(client: HttpClient, slug: str, code: str, ip: str = "203.0.113.7") -> Any:
    return client.post(url(slug), {"code": code}, REMOTE_ADDR=ip)


def screen(  # Any: test reads raw JSON
    client: HttpClient, slug: str, ip: str = "203.0.113.7"
) -> dict[str, Any]:
    response = client.get(url(slug), REMOTE_ADDR=ip)
    assert response.status_code == 200
    data: dict[str, Any] = page_data(response.content.decode())
    return data


# --- publishing ---


def test_publishing_makes_a_revision_a_document_number_and_a_code_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 16:30 UTC on the 21st is already the 22nd in Seoul.
    monkeypatch.setattr(
        "django.utils.timezone.now", lambda: datetime(2026, 10, 21, 16, 30, tzinfo=UTC)
    )
    p = make_draft(valid_until=date(2026, 12, 31))

    first = publishing.publish(p.slug)

    assert first.revision.number == 1
    assert first.revision.doc_number == "SC-20261022-NEXT-001"
    assert first.access_code and CODE.match(first.access_code)
    stored = Proposal.objects.get(slug=p.slug)
    assert stored.status == "published"
    assert first.access_code not in stored.access_code_hash
    assert publishing.code_matches(stored, first.access_code.lower())
    # Republishing makes v2 with the client's next number and keeps the customer's code.
    second = publishing.publish(p.slug)
    assert (second.revision.number, second.revision.doc_number) == (2, "SC-20261022-NEXT-002")
    assert second.access_code is None
    assert [r.number for r in publishing.list_revisions(p.slug)] == [2, 1]


def test_document_numbers_count_per_client() -> None:
    a = make_draft()
    b = svc.create_proposal(svc.NewProposal(client_code="NEXT", title="두 번째"))
    svc.create_client(svc.NewClient(code="ACME", name="에이크미"))
    c = svc.create_proposal(svc.NewProposal(client_code="ACME", title="다른 고객"))

    numbers = [publishing.publish(s).revision.doc_number[-8:] for s in (a.slug, b.slug, c.slug)]
    numbers.append(publishing.publish(a.slug).revision.doc_number[-8:])

    assert numbers == ["NEXT-001", "NEXT-002", "ACME-001", "NEXT-003"]


def test_a_revision_never_changes() -> None:
    slug, _ = published()
    revision = ProposalRevision.objects.get(proposal__slug=slug)
    revision.title = "바꿈"

    with pytest.raises(ValueError):
        revision.save()


def test_a_revoked_proposal_cannot_be_published_or_reissued_again() -> None:
    slug, _ = published()
    publishing.revoke(slug)

    with pytest.raises(Conflict):
        publishing.publish(slug)
    with pytest.raises(Conflict):
        publishing.reissue_access_code(slug)
    with pytest.raises(Conflict):
        publishing.revoke(slug)
    with pytest.raises(Conflict):
        publishing.reissue_access_code(make_draft().slug)  # never published


# --- the customer page ---


def test_the_page_asks_for_the_code_and_says_nothing_about_the_customer() -> None:
    slug, _ = published()
    client = HttpClient()

    response = client.get(url(slug))
    html = response.content.decode()

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert response["X-Robots-Tag"] == "noindex, nofollow"
    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert '<meta property="og:title" content="제안서 | Sandcorp">' in html
    for secret in ("가나다상사", "홍길순", "업무 자동화"):
        assert secret not in html
    data = page_data(html)
    assert data["screen"] == "code" and data["error"] is None and data["csrf_token"]


def test_the_right_code_opens_a_seven_day_session(monkeypatch: pytest.MonkeyPatch) -> None:
    slug, code = published()
    client = HttpClient()

    assert unlock(client, slug, "WRONG234").status_code == 400
    response = unlock(client, slug, code[:4] + "-" + code[4:].lower())

    assert response.status_code == 302 and response["Location"] == url(slug)
    cookie = response.cookies[f"proposal_{slug}"]
    assert cookie["path"] == url(slug) and cookie["max-age"] == 7 * 24 * 60 * 60
    assert cookie["httponly"] and cookie["secure"] and cookie["samesite"] == "Lax"
    data = screen(client, slug)
    assert data["title"] == "업무 자동화 제안" and data["preview"] is False
    assert data["revision"]["number"] == 1
    assert data["revision"]["doc_number"].startswith("SC-") and data["csrf_token"]

    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now + timedelta(days=6, hours=23).total_seconds())
    assert screen(client, slug).get("title") == "업무 자동화 제안"
    monkeypatch.setattr(time, "time", lambda: now + timedelta(days=7, minutes=1).total_seconds())
    assert screen(client, slug)["screen"] == "code"


def test_the_code_form_works_with_csrf_checks_on() -> None:
    slug, code = published()
    client = HttpClient(enforce_csrf_checks=True)
    token = screen(client, slug)["csrf_token"]

    assert client.post(url(slug), {"code": code}).status_code == 403
    response = client.post(url(slug), {"code": code, "csrfmiddlewaretoken": token})

    assert response.status_code == 302
    assert "title" in screen(client, slug)


def test_a_session_opens_only_its_own_proposal() -> None:
    slug, code = published()
    other = svc.create_proposal(svc.NewProposal(client_code="NEXT", title="다른 제안"))
    other_code = publishing.publish(other.slug).access_code
    assert other_code
    client = HttpClient()
    unlock(client, slug, code)
    # Copy the cookie onto the other proposal's name: the slug-bound signature refuses it.
    client.cookies[f"proposal_{other.slug}"] = client.cookies[f"proposal_{slug}"].value

    assert unlock(client, other.slug, code).status_code == 400
    assert screen(client, other.slug)["screen"] == "code"


def test_locking_forgets_the_session() -> None:
    slug, code = published()
    client = HttpClient()
    unlock(client, slug, code)

    response = client.post(f"{url(slug)}/lock")

    assert response.status_code == 302 and response["Location"] == url(slug)
    assert response.cookies[f"proposal_{slug}"]["path"] == url(slug)
    assert response.cookies[f"proposal_{slug}"]["max-age"] == 0
    assert screen(client, slug)["screen"] == "code"
    assert client.get(f"{url(slug)}/lock").status_code == 405


def test_reissuing_the_code_ends_existing_sessions() -> None:
    slug, old_code = published()
    client = HttpClient()
    unlock(client, slug, old_code)

    new_code = publishing.reissue_access_code(slug).access_code

    assert CODE.match(new_code) and new_code != old_code
    assert screen(client, slug)["screen"] == "code"
    assert unlock(client, slug, old_code).status_code == 400
    assert unlock(client, slug, new_code).status_code == 302
    assert "title" in screen(client, slug)


def test_too_many_wrong_codes_block_even_the_right_one(monkeypatch: pytest.MonkeyPatch) -> None:
    slug, code = published()
    blocked: list[str] = []
    monkeypatch.setattr(
        "services.proposal_access.on_blocked", lambda p, ip: blocked.append(f"{p.slug} {ip}")
    )
    client = HttpClient()

    statuses = [unlock(client, slug, "WRONG234").status_code for _ in range(5)]
    refused = unlock(client, slug, code)

    assert statuses == [400, 400, 400, 400, 429]
    assert refused.status_code == 429
    assert page_data(refused.content.decode())["error"] == "blocked"
    assert f"proposal_{slug}" not in refused.cookies
    assert screen(client, slug)["error"] == "blocked"
    assert blocked == [f"{slug} 203.0.113.7"]  # the hook fires once, when the block starts
    # Another address (and another proposal) is unaffected.
    assert unlock(HttpClient(), slug, code, ip="198.51.100.9").status_code == 302


def test_an_expired_proposal_shows_whom_to_contact_even_with_the_code() -> None:
    slug, code = published(valid_until=date(2020, 1, 31))
    client = HttpClient()

    response = unlock(client, slug, code)
    data = screen(client, slug)

    assert response.status_code == 302 and f"proposal_{slug}" not in response.cookies
    assert data["screen"] == "expired" and data["valid_until"] == "2020-01-31"
    assert data["supplier"]["name"] == "샌드코프"
    assert "title" not in data and "document" not in data


def test_a_revoked_proposal_answers_like_one_that_never_existed() -> None:
    slug, code = published()
    client = HttpClient()
    unlock(client, slug, code)
    missing = client.get("/p/doesnotexist")

    publishing.revoke(slug)

    for response in (client.get(url(slug)), unlock(client, slug, code)):
        assert response.status_code == 404
        assert response.content == missing.content


def test_the_customer_sees_the_latest_revision_and_old_ones_stay(
    example_document: dict[str, Any],  # Any: raw JSON
) -> None:
    slug, code = published()
    client = HttpClient()
    unlock(client, slug, code)

    svc.update_proposal(slug, svc.ProposalPatch(title="고친 제안"))
    svc.replace_document(slug, dict[str, object](example_document))
    assert screen(client, slug)["title"] == "업무 자동화 제안"  # the draft is not published yet

    publishing.publish(slug)
    data = screen(client, slug)

    assert (data["title"], data["revision"]["number"]) == ("고친 제안", 2)
    assert data["document"]["tabs"][0]["blocks"]
    v1 = publishing.get_revision(slug, 1)
    v1_document: Any = v1.document  # Any: test reads raw JSON
    assert v1.title == "업무 자동화 제안" and v1_document["tabs"][0]["blocks"] == []
    assert v1.recipient == "홍길순 대표님께"


# --- admin ---


def changelist() -> str:
    return reverse("admin:content_proposal_changelist")


def act(admin_client: HttpClient, action: str, slug: str) -> Any:
    pk = Proposal.objects.get(slug=slug).pk
    return admin_client.post(changelist(), {"action": action, "_selected_action": [pk]})


def shown_code(html: str) -> str:
    found = re.search(r"<code[^>]*>([A-Z0-9]{8})</code>", html)
    assert found
    return found.group(1)


def test_admin_publish_shows_the_code_once_and_keeps_it_nowhere(
    admin_client: HttpClient,
) -> None:
    p = make_draft()

    response = act(admin_client, "publish", p.slug)
    html = response.content.decode()
    code = shown_code(html)

    assert response.status_code == 200 and "no-store" in response["Cache-Control"]
    assert "v1 SC-" in html
    assert "messages" not in admin_client.cookies
    assert code not in str(dict(admin_client.session))
    stored = Proposal.objects.get(slug=p.slug)
    assert publishing.code_matches(stored, code) and code not in stored.access_code_hash
    page = admin_client.get(reverse("admin:content_proposal_change", args=[stored.pk]))
    assert code not in page.content.decode()
    assert code not in admin_client.get(changelist()).content.decode()
    # Publishing again shows the new revision, and no code.
    again = act(admin_client, "publish", p.slug).content.decode()
    assert "v2 SC-" in again and "<code" not in again


def test_admin_reissue_and_revoke(admin_client: HttpClient) -> None:
    slug, old_code = published()

    code = shown_code(act(admin_client, "reissue_code", slug).content.decode())
    stored = Proposal.objects.get(slug=slug)
    assert code != old_code and publishing.code_matches(stored, code)

    revoked = act(admin_client, "revoke", slug)
    assert revoked.status_code == 302, revoked.content.decode()[-3000:]
    assert Proposal.objects.get(slug=slug).status == "revoked"
    revision = ProposalRevision.objects.get(proposal__slug=slug)
    page = admin_client.get(reverse("admin:content_proposalrevision_change", args=[revision.pk]))
    assert page.status_code == 200 and revision.doc_number in page.content.decode()


def test_admin_refuses_to_publish_a_revoked_proposal(admin_client: HttpClient) -> None:
    slug, _ = published()
    publishing.revoke(slug)

    html = act(admin_client, "publish", slug).content.decode()

    assert "회수된 제안서는 다시 발행할 수 없습니다" in html
    assert ProposalRevision.objects.filter(proposal__slug=slug).count() == 1

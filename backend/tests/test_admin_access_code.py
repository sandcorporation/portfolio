"""The admin shows a proposal's public address and access code, and takes a new code (issue 231)."""

import json
from typing import Any

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import Client as HttpClient
from django.test import override_settings
from django.urls import reverse

from content.models import Proposal
from services import access_code_box, proposals, publishing
from tests.test_proposals import admin_form, make_draft
from tests.test_publishing import act, cache_table, published, screen, shown_code, unlock

__all__ = ["cache_table"]  # autouse fixture: the code check uses the cache

pytestmark = pytest.mark.django_db

UNREADABLE = "다시 볼 수 없음"


def change_url(slug: str) -> str:
    return reverse("admin:content_proposal_change", args=[Proposal.objects.get(slug=slug).pk])


def change_page(admin_client: HttpClient, slug: str) -> tuple[str, Any]:
    response = admin_client.get(change_url(slug))
    assert response.status_code == 200
    return response.content.decode(), response


def save_with_code(admin_client: HttpClient, slug: str, code: str) -> Any:
    p = Proposal.objects.get(slug=slug)
    return admin_client.post(
        change_url(slug),
        admin_form(
            title=p.title,
            subtitle=p.subtitle,
            quote_date=p.quote_date.isoformat() if p.quote_date else "",
            document=json.dumps(p.document),
            new_access_code=code,
        ),
    )


def test_the_detail_shows_the_issued_code_and_the_public_address(
    admin_client: HttpClient,
) -> None:
    slug, code = published()

    html, response = change_page(admin_client, slug)

    assert code in html and "no-store" in response["Cache-Control"]
    assert f'href="http://testserver/p/{slug}"' in html or f"/p/{slug}" in html
    assert 'target="_blank" rel="noopener"' in html
    assert 'name="new_access_code"' in html
    listing = admin_client.get(reverse("admin:content_proposal_changelist")).content.decode()
    assert f"/p/{slug}" in listing and code not in listing


def test_the_sealed_copy_holds_no_plain_code_and_mcp_shows_none() -> None:
    slug, code = published()
    stored = Proposal.objects.get(slug=slug)

    assert stored.access_code_encrypted and code not in stored.access_code_encrypted
    assert access_code_box.open_(stored.access_code_encrypted) == code
    out = proposals.get_proposal(slug).model_dump_json()
    assert code not in out and stored.access_code_encrypted not in out


def test_reissue_by_mcp_and_admin_action_shows_the_new_code(admin_client: HttpClient) -> None:
    slug, _ = published()

    by_tool = publishing.reissue_access_code(slug).access_code
    assert by_tool in change_page(admin_client, slug)[0]

    by_action = shown_code(act(admin_client, "reissue_code", slug).content.decode())
    assert by_action in change_page(admin_client, slug)[0]
    assert unlock(HttpClient(), slug, by_action).status_code == 302


def test_a_new_code_in_the_form_replaces_the_old_one(admin_client: HttpClient) -> None:
    slug, old = published()
    customer = HttpClient()
    assert unlock(customer, slug, old).status_code == 302
    screen(customer, slug)  # the customer is in

    saved = save_with_code(admin_client, slug, "가나다상사-2026")

    assert saved.status_code == 302, saved.content.decode()[-2000:]
    assert unlock(HttpClient(), slug, old).status_code != 302
    assert unlock(HttpClient(), slug, "가나다상사-2026").status_code == 302
    assert "가나다상사-2026" in change_page(admin_client, slug)[0]
    gate = customer.get(f"/p/{slug}", REMOTE_ADDR="203.0.113.7").content.decode()
    assert '"tabs"' not in gate  # the old session ended: the gate again, not the document
    logged = " ".join(str(e.change_message) for e in LogEntry.objects.all())
    assert "가나다상사-2026" not in logged


def test_a_weak_code_is_a_form_error_and_an_empty_one_keeps_the_code(
    admin_client: HttpClient,
) -> None:
    slug, code = published()

    bad = save_with_code(admin_client, slug, "1234")
    assert bad.status_code == 200 and "너무 쉽습니다" in bad.content.decode()
    kept = save_with_code(admin_client, slug, "")
    assert kept.status_code == 302
    assert unlock(HttpClient(), slug, code).status_code == 302


def test_an_old_publication_without_a_sealed_copy_says_it_cannot_be_shown(
    admin_client: HttpClient,
) -> None:
    slug, code = published()
    Proposal.objects.filter(slug=slug).update(access_code_encrypted="")

    assert UNREADABLE in change_page(admin_client, slug)[0]
    assert unlock(HttpClient(), slug, code).status_code == 302


def test_another_secret_key_cannot_open_the_code(admin_client: HttpClient) -> None:
    slug, code = published()
    with override_settings(SECRET_KEY="another-test-only-key"):
        foreign = access_code_box.seal(code)  # as if SECRET_KEY changed after issuing
    Proposal.objects.filter(slug=slug).update(access_code_encrypted=foreign)

    html, _ = change_page(admin_client, slug)

    assert code not in html and UNREADABLE in html
    assert unlock(HttpClient(), slug, code).status_code == 302


def test_a_draft_has_no_address_code_or_field(admin_client: HttpClient) -> None:
    draft = make_draft()

    html, _ = change_page(admin_client, draft.slug)

    assert f"/p/{draft.slug}" not in html and 'name="new_access_code"' not in html


def test_a_revoked_proposal_has_no_address_code_or_field(admin_client: HttpClient) -> None:
    slug, code = published()
    publishing.revoke(slug)
    html, _ = change_page(admin_client, slug)
    assert code not in html and 'name="new_access_code"' not in html
    assert f"/p/{slug}" not in html


def test_staff_only(client: HttpClient) -> None:
    slug, _ = published()
    user = get_user_model().objects.create_user("guest", "g@example.com", "pw")
    client.force_login(user)

    response = client.get(change_url(slug))

    assert response.status_code == 302 and "/login" in response["Location"]

"""Proposal drafts: service functions (what #24's MCP tools wrap), the admin, and the preview."""

import copy
import time
from datetime import date, timedelta
from typing import Any

import pytest
from django.test import Client as HttpClient
from django.urls import reverse

from content.models import Client, Proposal
from documents.validation import JSON
from services import proposals as svc
from services.errors import Conflict, NotFound, Rejected
from tests.test_portfolio import page_data

pytestmark = pytest.mark.django_db


def make_client(code: str = "NEXT") -> None:
    svc.create_client(svc.NewClient(code=code, name="가나다상사", contact_title="홍길순 대표님"))


def make_draft(**extra: Any) -> svc.ProposalOut:  # Any: NewProposal keyword fields
    make_client()
    return svc.create_proposal(
        svc.NewProposal(client_code="NEXT", title="업무 자동화 제안", subtitle="견적", **extra)
    )


def md(block_id: str, body: str = "본문") -> dict[str, object]:
    return {"id": block_id, "type": "markdown", "title": block_id, "body": body}


def tab_blocks(p: svc.ProposalOut, tab: int) -> list[Any]:  # Any: test reads raw JSON
    tabs: Any = p.document["tabs"]
    return list(tabs[tab]["blocks"])


def tabs_of(p: svc.ProposalOut) -> list[Any]:  # Any: test reads raw JSON
    tabs: Any = p.document["tabs"]
    return list(tabs)


def block_ids(p: svc.ProposalOut, tab: int) -> list[str]:
    return [b["id"] for b in tab_blocks(p, tab)]


# --- clients ---


def test_client_codes_are_unique_uppercase_two_to_six_letters() -> None:
    make_client()

    with pytest.raises(Conflict):
        svc.create_client(svc.NewClient(code="NEXT", name="다른 회사"))
    for bad in ("N", "ganadatrade", "GANADATRADE", "NE1"):
        with pytest.raises(ValueError):
            svc.NewClient(code=bad, name="x")
    assert Client.objects.count() == 1


def test_client_update_changes_only_given_fields() -> None:
    make_client()

    out = svc.update_client("NEXT", svc.ClientPatch(memo="3월 재계약"))

    assert (out.memo, out.name, out.contact_title) == ("3월 재계약", "가나다상사", "홍길순 대표님")
    with pytest.raises(NotFound):
        svc.update_client("NOPE", svc.ClientPatch(memo="x"))


# --- proposals ---


def test_a_new_proposal_is_a_draft_with_two_tabs_and_an_unguessable_slug() -> None:
    p = make_draft()
    other = svc.create_proposal(svc.NewProposal(client_code="NEXT", title="두 번째"))

    assert p.status == "draft"
    assert [t["title"] for t in tabs_of(p)] == ["견적 제안", "회사소개·수행사례"]
    assert len(p.slug) >= 22 and p.slug != other.slug
    assert p.quote_date == date.today()


def test_proposal_for_an_unknown_client_is_not_found() -> None:
    with pytest.raises(NotFound):
        svc.create_proposal(svc.NewProposal(client_code="NOPE", title="x"))


def test_metadata_patch_changes_only_given_fields() -> None:
    p = make_draft(valid_until=date(2026, 12, 31))

    out = svc.update_proposal(p.slug, svc.ProposalPatch(subtitle="수정", valid_until=None))

    assert (out.title, out.subtitle, out.valid_until) == ("업무 자동화 제안", "수정", None)
    assert out.quote_date == p.quote_date


def test_replace_insert_and_delete_touch_only_their_block() -> None:
    p = make_draft()
    p = svc.replace_document(
        p.slug,
        {
            "tabs": [
                {"id": "estimate", "title": "견적 제안", "blocks": [md("a"), md("b"), md("c")]},
                {"id": "company", "title": "회사소개·수행사례", "blocks": [md("z")]},
            ]
        },
    )
    before = copy.deepcopy(p.document)

    replaced = svc.replace_block(p.slug, "b", md("b", "바뀐 본문"))
    assert block_ids(replaced, 0) == ["a", "b", "c"]
    assert tab_blocks(replaced, 0)[1]["body"] == "바뀐 본문"
    assert tab_blocks(replaced, 0)[0] == tab_blocks(p, 0)[0]
    assert tab_blocks(replaced, 0)[2] == tab_blocks(p, 0)[2]
    assert tabs_of(replaced)[1] == before["tabs"][1]  # type: ignore[index]

    inserted = svc.insert_block(p.slug, "estimate", md("new"), after_block_id="a")
    assert block_ids(inserted, 0) == ["a", "new", "b", "c"]
    first = svc.insert_block(p.slug, "estimate", md("top"))
    assert block_ids(first, 0)[0] == "top"

    deleted = svc.delete_block(p.slug, "a")
    assert block_ids(deleted, 0) == ["top", "new", "b", "c"]
    assert block_ids(deleted, 1) == ["z"]


def test_block_edits_are_refused_with_paths_and_save_nothing() -> None:
    p = make_draft()
    p = svc.insert_block(p.slug, "estimate", md("a"))

    with pytest.raises(Rejected) as bad:
        svc.replace_block(
            p.slug, "a", {"id": "a", "type": "table", "columns": ["x"], "rows": [["1", "2"]]}
        )
    assert [e.path for e in bad.value.errors] == ["document.tabs[0].blocks[0].rows[0]"]
    with pytest.raises(Rejected):
        svc.insert_block(p.slug, "company", md("a"))  # id already used in another tab
    with pytest.raises(NotFound):
        svc.delete_block(p.slug, "ghost")
    with pytest.raises(NotFound):
        svc.insert_block(p.slug, "ghost-tab", md("q"))
    with pytest.raises(NotFound):
        svc.insert_block(p.slug, "estimate", md("q"), after_block_id="ghost")
    assert svc.get_proposal(p.slug).document == p.document


def test_tabs_can_be_added_renamed_reordered_and_deleted() -> None:
    p = make_draft()

    p = svc.add_tab(p.slug, "일정", tab_id="schedule")
    p = svc.rename_tab(p.slug, "schedule", "진행 일정")
    p = svc.reorder_tabs(p.slug, ["schedule", "estimate", "company"])
    assert [(t["id"], t["title"]) for t in tabs_of(p)] == [
        ("schedule", "진행 일정"),
        ("estimate", "견적 제안"),
        ("company", "회사소개·수행사례"),
    ]
    auto = svc.add_tab(p.slug, "부록")
    assert tabs_of(auto)[3]["id"].startswith("tab-")
    p = svc.delete_tab(p.slug, "schedule")
    assert [t["id"] for t in tabs_of(p)][:2] == ["estimate", "company"]

    with pytest.raises(Rejected):
        svc.reorder_tabs(p.slug, ["estimate"])
    with pytest.raises(NotFound):
        svc.rename_tab(p.slug, "ghost", "x")
    with pytest.raises(Rejected):
        svc.add_tab(p.slug, "중복", tab_id="estimate")


def test_the_last_tab_cannot_be_deleted() -> None:
    p = make_draft()
    p = svc.delete_tab(p.slug, "company")

    with pytest.raises(Rejected):
        svc.delete_tab(p.slug, "estimate")


def test_only_drafts_are_edited() -> None:
    p = make_draft()
    Proposal.objects.filter(slug=p.slug).update(status=Proposal.Status.PUBLISHED)

    with pytest.raises(Conflict):
        svc.update_proposal(p.slug, svc.ProposalPatch(title="바꿈"))
    with pytest.raises(Conflict):
        svc.insert_block(p.slug, "estimate", md("x"))


def test_a_copy_is_a_new_draft_with_its_own_slug() -> None:
    p = make_draft()
    p = svc.insert_block(p.slug, "estimate", md("a"))
    Proposal.objects.filter(slug=p.slug).update(status=Proposal.Status.PUBLISHED)

    copy_ = svc.duplicate_proposal(p.slug)

    assert copy_.slug != p.slug and copy_.status == "draft"
    assert copy_.document == p.document and copy_.title == "업무 자동화 제안 (복사)"
    assert svc.get_proposal(p.slug).status == "published"


# --- the preview ---


def preview_url(slug: str) -> str:
    return svc.issue_preview_url(slug).url


def test_preview_shows_the_draft_for_the_customer_screen(
    client: HttpClient, example_document: dict[str, JSON]
) -> None:
    p = make_draft(quote_date=date(2026, 10, 1))
    svc.replace_document(p.slug, dict[str, object](example_document))

    response = client.get(preview_url(p.slug))
    html = response.content.decode()

    assert response.status_code == 200
    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert response["Cache-Control"] == "no-store"
    assert response["X-Robots-Tag"] == "noindex, nofollow"
    assert "홍길순" not in html.split("</head>")[0]  # nothing about the customer in <head>
    data = page_data(html)
    assert data["preview"] is True
    assert (data["recipient"], data["title"], data["quote_date"]) == (
        "홍길순 대표님께",
        "업무 자동화 제안",
        "2026-10-01",
    )
    assert data["supplier"]["name"] == "샌드코퍼레이션"
    assert data["document"]["tabs"][0]["id"] == "estimate"


def test_an_expired_preview_link_does_not_open(monkeypatch: pytest.MonkeyPatch) -> None:
    p = make_draft()
    client = HttpClient()
    url = preview_url(p.slug)
    now = time.time()

    monkeypatch.setattr(time, "time", lambda: now + timedelta(minutes=29).total_seconds())
    assert client.get(url).status_code == 200
    monkeypatch.setattr(time, "time", lambda: now + timedelta(minutes=31).total_seconds())
    response = client.get(url)

    assert response.status_code == 410
    assert "만료" in response.content.decode()
    assert "업무 자동화" not in response.content.decode()


def test_a_forged_preview_link_does_not_open(client: HttpClient) -> None:
    p = make_draft()
    token = preview_url(p.slug).removeprefix("/preview/")

    assert client.get("/preview/nonsense").status_code == 404
    assert client.get(f"/preview/{token[:-2]}xx").status_code == 404
    assert client.get(f"/preview/other:{token.split(':', 1)[1]}").status_code == 404


def test_a_draft_opens_only_through_its_preview(client: HttpClient) -> None:
    p = make_draft()

    assert client.get(f"/p/{p.slug}").status_code == 404
    assert client.get(f"/p/{p.slug}/").status_code == 404
    assert client.get(f"/work/{p.slug}").status_code == 404
    sitemap = client.get("/sitemap.xml").content.decode()
    assert p.slug not in sitemap
    assert p.slug not in client.get("/").content.decode()
    Proposal.objects.filter(slug=p.slug).update(status=Proposal.Status.REVOKED)
    assert client.get(f"/p/{p.slug}").status_code == 404


def test_robots_keeps_previews_out() -> None:
    assert "Disallow: /preview/" in HttpClient().get("/robots.txt").content.decode()


# --- admin ---


def admin_form(**over: Any) -> dict[str, Any]:  # Any: form fields
    client = Client.objects.get(code="NEXT")
    return {
        "client": client.pk,
        "title": "새 제안",
        "subtitle": "",
        "quote_date": "2026-10-01",
        "valid_until": "",
        "document": '{"tabs":[{"id":"a","title":"견적","blocks":[]}]}',
        **over,
    }


def test_admin_saves_a_valid_document_and_shows_error_paths(admin_client: HttpClient) -> None:
    make_client()
    add = reverse("admin:content_proposal_add")

    bad = admin_client.post(
        add,
        admin_form(
            document='{"tabs":[{"id":"a","title":"x","blocks":[{"id":"k","type":"kpi","items":[]}]}]}'
        ),
    )
    assert bad.status_code == 200
    assert "tabs[0].blocks[0].items" in bad.content.decode()
    assert Proposal.objects.count() == 0

    ok = admin_client.post(add, admin_form())
    assert ok.status_code == 302
    saved = Proposal.objects.get()
    assert saved.status == "draft" and len(saved.slug) >= 22


def test_admin_preview_link_redirects_to_a_fresh_signed_url(admin_client: HttpClient) -> None:
    p = make_draft()
    pk = Proposal.objects.get(slug=p.slug).pk

    change = admin_client.get(reverse("admin:content_proposal_change", args=[pk]))
    assert reverse("admin:content_proposal_preview", args=[pk]) in change.content.decode()
    go = admin_client.get(reverse("admin:content_proposal_preview", args=[pk]))

    assert go.status_code == 302 and go["Location"].startswith("/preview/")
    assert HttpClient().get(go["Location"]).status_code == 200


def test_admin_duplicate_action_makes_new_drafts(admin_client: HttpClient) -> None:
    p = make_draft()
    pk = Proposal.objects.get(slug=p.slug).pk

    response = admin_client.post(
        reverse("admin:content_proposal_changelist"),
        {"action": "duplicate", "_selected_action": [pk]},
    )

    assert response.status_code == 302
    assert Proposal.objects.count() == 2
    assert Proposal.objects.exclude(slug=p.slug).get().status == "draft"


def test_admin_client_code_is_unique(admin_client: HttpClient) -> None:
    make_client()

    response = admin_client.post(
        reverse("admin:content_client_add"),
        {"code": "NEXT", "name": "중복", "contact_title": "", "memo": ""},
    )

    assert response.status_code == 200
    assert Client.objects.count() == 1

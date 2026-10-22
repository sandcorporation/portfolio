"""`case-ref` blocks: drafts cite the portfolio, revisions freeze it (service and HTTP edges)."""

from typing import Any

import pytest
from django.test import Client as HttpClient
from django.urls import reverse

from content.models import PortfolioItem, Proposal
from services import proposals as svc
from services import publishing
from services.errors import Rejected
from tests.test_portfolio import make, page_data
from tests.test_proposals import make_draft, preview_url
from tests.test_publishing import screen, unlock

pytestmark = pytest.mark.django_db


def ref_block(*refs: tuple[int, str | None]) -> dict[str, object]:
    return {
        "id": "cases",
        "type": "case-ref",
        "title": "수행사례",
        "items": [{"item_id": pk, "highlight": hl} for pk, hl in refs],
    }


def cite(slug: str, *refs: tuple[int, str | None]) -> None:
    svc.replace_block(slug, "cases", ref_block(*refs))


def draft_with_cases(*refs: tuple[int, str | None]) -> svc.ProposalOut:
    p = make_draft()
    if refs:
        cite(p.slug, *refs)
    return p


def cases_of(document: Any) -> list[dict[str, Any]]:  # Any: test reads raw JSON
    block = next(b for tab in document["tabs"] for b in tab["blocks"] if b["type"] == "case-ref")
    return list(block["items"])


def customer_document(slug: str, code: str) -> Any:
    client = HttpClient()
    unlock(client, slug, code)
    return screen(client, slug)["document"]


def test_new_proposal_starts_with_company_intro_and_an_empty_case_ref() -> None:
    from services import profile

    profile.update_profile(
        profile.ProfilePatch(
            company_intro={
                "tabs": [
                    {
                        "id": "main",
                        "title": "소개",
                        "blocks": [
                            {"id": "hello", "type": "markdown", "title": "샌드", "body": "x"}
                        ],
                    }
                ]
            }
        )
    )
    p = make_draft()

    tabs: Any = p.document["tabs"]
    assert [t["title"] for t in tabs] == ["견적 제안", "회사소개·수행사례"]
    company = tabs[1]["blocks"]
    assert [b["id"] for b in company] == ["intro-hello", "cases"]
    assert company[0]["body"] == "x" and company[1] == {
        "id": "cases",
        "type": "case-ref",
        "title": "수행사례",
        "items": [],
    }


def test_preview_lists_cases_in_given_order_with_overridden_highlight(client: HttpClient) -> None:
    a = make("alpha", title="알파", summary="알파 요약", period="2025.01")
    b = make("beta", title="베타", summary="베타 요약", tags="web, ai")
    p = draft_with_cases((b.pk, "이 제안과 가장 닮은 사례"), (a.pk, None))

    data = page_data(client.get(preview_url(p.slug)).content.decode())

    items = cases_of(data["document"])
    assert [i["case"]["title"] for i in items] == ["베타", "알파"]
    assert items[0]["highlight"] == "이 제안과 가장 닮은 사례"
    assert items[0]["case"]["tags"] == ["web", "ai"]
    assert items[1]["highlight"] is None and items[1]["case"]["summary"] == "알파 요약"


def test_draft_stores_references_only(client: HttpClient) -> None:
    a = make("alpha", title="알파")
    p = draft_with_cases((a.pk, None))
    # A caller that sends content along with the reference has it dropped on save.
    block = ref_block((a.pk, "강조"))
    block["items"] = [{**block["items"][0], "case": {"slug": "x", "title": "가짜"}}]  # type: ignore[index]
    svc.replace_block(p.slug, "cases", block)

    stored = cases_of(svc.get_proposal(p.slug).document)
    assert stored == [{"item_id": a.pk, "highlight": "강조", "case": None}]


def test_unknown_item_is_a_validation_error_with_the_block_path() -> None:
    a = make("alpha")
    p = draft_with_cases()

    with pytest.raises(Rejected) as caught:
        cite(p.slug, (a.pk, None), (a.pk + 999, None))

    paths = [e.path for e in caught.value.errors]
    assert paths == ["document.tabs[1].blocks[0].items[1].item_id"]


def test_hidden_items_can_be_cited(client: HttpClient) -> None:
    hidden = make("secret", public=False, title="비공개 사례")
    p = draft_with_cases((hidden.pk, None))

    data = page_data(client.get(preview_url(p.slug)).content.decode())

    assert cases_of(data["document"])[0]["case"]["title"] == "비공개 사례"


def test_published_revision_does_not_follow_later_portfolio_edits() -> None:
    a = make("alpha", title="알파", summary="옛 요약")
    p = draft_with_cases((a.pk, "강조"))
    result = publishing.publish(p.slug)
    assert result.access_code is not None
    a.title, a.summary = "새 알파", "새 요약"
    a.save()

    before = cases_of(customer_document(p.slug, result.access_code))
    assert before[0]["case"]["title"] == "알파" and before[0]["case"]["summary"] == "옛 요약"
    assert before[0]["highlight"] == "강조"

    publishing.publish(p.slug)
    after = cases_of(customer_document(p.slug, result.access_code))
    assert after[0]["case"]["title"] == "새 알파" and after[0]["case"]["summary"] == "새 요약"
    first = publishing.get_revision(p.slug, 1)
    assert cases_of(first.document)[0]["case"]["title"] == "알파"  # revision 1 stays frozen


def test_revision_keeps_the_case_after_the_item_is_deleted() -> None:
    a = make("alpha", title="알파")
    p = draft_with_cases((a.pk, None))
    result = publishing.publish(p.slug)
    assert result.access_code is not None
    PortfolioItem.objects.filter(pk=a.pk).delete()

    shown = cases_of(customer_document(p.slug, result.access_code))
    assert [i["case"]["title"] for i in shown] == ["알파"]
    # The draft still cites a deleted item: the preview drops it rather than failing.
    assert cases_of(svc.page_data(Proposal.objects.get(slug=p.slug), preview=True).document) == []


def test_admin_form_rejects_an_unknown_item(admin_client: HttpClient) -> None:
    from tests.test_proposals import admin_form, make_client

    make_client()
    bad = admin_client.post(
        reverse("admin:content_proposal_add"),
        admin_form(
            document='{"tabs":[{"id":"a","title":"x","blocks":[{"id":"c","type":"case-ref",'
            '"items":[{"item_id":9999}]}]}]}'
        ),
    )

    assert bad.status_code == 200
    assert "tabs[0].blocks[0].items[0].item_id" in bad.content.decode()

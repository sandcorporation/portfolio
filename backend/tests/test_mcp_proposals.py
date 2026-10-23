"""The writing tools of #24 through /mcp: media, clients and proposals, publishing, PDFs,
inquiries and view events. Same services as the admin; here only the shell is under test."""

import re
from typing import Any, cast

import pytest
from django.test import Client

from adapters.fake_jwks import FakeAuthServer
from adapters.fake_storage import FakeObjectStorage
from adapters.storage import Bucket
from content.models import Inquiry, Proposal, ProposalEvent
from mcpserver.tools import TOOLS
from services import proposal_events
from tests.test_mcp import McpClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def mcp(client: Client, auth_server: FakeAuthServer) -> McpClient:
    return McpClient(client, auth_server)


type Data = dict[str, Any]  # Any: tool results are arbitrary JSON

EXPECTED_TOOLS = {
    "start_upload", "complete_upload", "list_media",
    "list_clients", "create_client", "update_client",
    "list_proposals", "get_proposal", "create_proposal", "duplicate_proposal", "update_proposal",
    "replace_document", "replace_block", "insert_block", "delete_block",
    "add_tab", "delete_tab", "rename_tab", "reorder_tabs", "issue_preview_url",
    "publish", "reissue_access_code", "revoke", "list_revisions", "get_revision",
    "pdf_status", "retry_pdf", "list_inquiries", "mark_inquiry_handled", "list_proposal_events",
}  # fmt: skip
READ_ONLY = {
    "list_media", "list_clients", "list_proposals", "get_proposal", "issue_preview_url",
    "list_revisions", "get_revision", "pdf_status", "list_inquiries", "list_proposal_events",
}  # fmt: skip


def ok(mcp: McpClient, name: str, arguments: Data) -> Data:
    result = mcp.call_tool(name, arguments)
    assert result["isError"] is False, result
    structured = result["structuredContent"]
    assert isinstance(structured, dict)
    return cast(Data, structured)


def refused(mcp: McpClient, name: str, arguments: Data) -> str:
    result = mcp.call_tool(name, arguments)
    assert result["isError"] is True
    content = result["content"]
    assert isinstance(content, list) and isinstance(content[0], dict)
    return str(content[0]["text"])


def new_proposal(mcp: McpClient, slug_title: str = "홈페이지 제작") -> Data:
    ok(mcp, "create_client", {"code": "ABC", "name": "에이비씨", "contact_title": "김 대표님"})
    return ok(mcp, "create_proposal", {"client_code": "ABC", "title": slug_title})


def first_block(proposal: Data) -> tuple[str, str]:
    for tab in proposal["document"]["tabs"]:
        if tab["blocks"]:
            return tab["id"], tab["blocks"][0]["id"]
    raise AssertionError("starting document has no block")


def test_every_tool_is_listed_and_only_readers_are_read_only(mcp: McpClient) -> None:
    listed = cast(Data, mcp.request("tools/list")["result"])
    by_name = {t["name"]: t for t in listed["tools"]}
    assert EXPECTED_TOOLS <= set(by_name) <= set(TOOLS)
    for name in EXPECTED_TOOLS:
        assert by_name[name]["annotations"]["readOnlyHint"] is (name in READ_ONLY), name


def test_upload_start_then_put_then_complete(
    mcp: McpClient, fake_storage: FakeObjectStorage
) -> None:
    started = ok(mcp, "start_upload", {"filename": "a.png", "content_type": "image/png", "size": 3})
    assert started["upload_method"] == "PUT"
    assert started["upload_headers"] == {"Content-Type": "image/png"}
    assert ok(mcp, "list_media", {})["items"] == []  # unfinished uploads stay hidden

    media_id = started["media_id"]
    key = re.search(r"/public/([^?]+)", started["upload_url"])
    assert key
    fake_storage.simulate_client_put(Bucket.PUBLIC, key.group(1), b"abc", "image/png")
    done = ok(mcp, "complete_upload", {"media_id": media_id})
    assert done["complete"] is True and done["url"]
    assert [m["media_id"] for m in ok(mcp, "list_media", {})["items"]] == [media_id]


def test_upload_refusals_are_readable(mcp: McpClient, fake_storage: FakeObjectStorage) -> None:
    assert "올릴 수 없습니다" in refused(
        mcp,
        "start_upload",
        {"filename": "a.exe", "content_type": "application/x-msdownload", "size": 3},
    )
    assert refused(mcp, "complete_upload", {"media_id": 99999})


def test_client_proposal_block_replace_and_preview(mcp: McpClient) -> None:
    proposal = new_proposal(mcp)
    slug = proposal["slug"]
    assert [c["code"] for c in ok(mcp, "list_clients", {})["items"]] == ["ABC"]
    assert ok(mcp, "update_client", {"code": "ABC", "memo": "소개받음"})["memo"] == "소개받음"
    assert [p["slug"] for p in ok(mcp, "list_proposals", {"client_code": "ABC"})["items"]] == [slug]

    tab_id, block_id = first_block(proposal)
    block = {"type": "markdown", "body": "바뀐 제목"}
    replaced = ok(mcp, "replace_block", {"slug": slug, "block_id": block_id, "block": block})
    blocks = {b["id"]: b for t in replaced["document"]["tabs"] for b in t["blocks"]}
    assert blocks[block_id]["body"] == "바뀐 제목"
    assert ok(mcp, "get_proposal", {"slug": slug})["document"] == replaced["document"]

    preview = ok(mcp, "issue_preview_url", {"slug": slug})
    assert preview["url"].startswith("/preview/")
    added = ok(mcp, "add_tab", {"slug": slug, "title": "부록", "tab_id": "extra"})
    assert added["document"]["tabs"][-1]["id"] == "extra"
    assert ok(mcp, "rename_tab", {"slug": slug, "tab_id": "extra", "title": "별첨"})
    ids = [t["id"] for t in added["document"]["tabs"]]
    reordered = ok(mcp, "reorder_tabs", {"slug": slug, "tab_ids": ids[::-1]})
    assert [t["id"] for t in reordered["document"]["tabs"]] == ids[::-1]
    assert ok(mcp, "delete_tab", {"slug": slug, "tab_id": "extra"})
    copy = ok(mcp, "duplicate_proposal", {"slug": slug})
    assert copy["slug"] != slug
    assert ok(mcp, "update_proposal", {"slug": slug, "title": "새 제목"})["title"] == "새 제목"


def test_an_invalid_document_is_refused_with_block_paths(mcp: McpClient) -> None:
    proposal = new_proposal(mcp)
    _, block_id = first_block(proposal)
    text = refused(
        mcp,
        "replace_block",
        {"slug": proposal["slug"], "block_id": block_id, "block": {"type": "nonsense"}},
    )
    assert text.startswith("저장하지 않았습니다") and "tabs" in text
    saved = ok(mcp, "get_proposal", {"slug": proposal["slug"]})
    assert saved["document"] == proposal["document"]


def test_publish_shows_the_access_code_only_in_its_response(
    mcp: McpClient, fake_storage: FakeObjectStorage
) -> None:
    proposal = new_proposal(mcp)
    slug = proposal["slug"]
    published = ok(mcp, "publish", {"slug": slug})
    code = published["access_code"]
    assert re.fullmatch(r"[A-Z0-9]{8}", code)

    for name, args in [
        ("list_revisions", {"slug": slug}),
        ("get_revision", {"slug": slug, "number": 1}),
        ("get_proposal", {"slug": slug}),
        ("list_proposals", {}),
    ]:
        assert code not in str(ok(mcp, name, args)), name

    second = ok(mcp, "publish", {"slug": slug})
    assert second["access_code"] is None and second["revision"]["number"] == 2
    assert [r["number"] for r in ok(mcp, "list_revisions", {"slug": slug})["items"]] == [2, 1]

    reissued = ok(mcp, "reissue_access_code", {"slug": slug})
    assert reissued["access_code"] != code

    assert ok(mcp, "pdf_status", {"slug": slug})["status"] == "pending"
    assert ok(mcp, "retry_pdf", {"slug": slug, "number": 1})["revision"] == 1

    assert ok(mcp, "revoke", {"slug": slug})["status"] == "revoked"
    assert "회수" in refused(mcp, "publish", {"slug": slug})
    assert refused(mcp, "get_revision", {"slug": slug, "number": 9})


def test_inquiries_list_then_mark_handled(mcp: McpClient) -> None:
    mine = Inquiry.objects.create(
        name="홍", contact="a@b.c", message="안녕", kind="문의", site="news"
    )
    Inquiry.objects.create(name="김", contact="d@e.f", message="견적", kind="문의")
    items = ok(mcp, "list_inquiries", {"unhandled_only": True})["items"]
    assert len(items) == 2 and {i["site"] for i in items} == {"news", "portfolio"}

    handled = ok(mcp, "mark_inquiry_handled", {"inquiry_id": mine.pk})
    assert handled["handled_at"]
    left = ok(mcp, "list_inquiries", {"unhandled_only": True})["items"]
    assert [i["name"] for i in left] == ["김"]
    assert refused(mcp, "mark_inquiry_handled", {"inquiry_id": 99999})


def test_view_events_are_listed(mcp: McpClient) -> None:
    proposal = new_proposal(mcp)
    slug = proposal["slug"]
    ok(mcp, "publish", {"slug": slug})
    p = Proposal.objects.get(slug=slug)
    revision = p.revisions.get()
    proposal_events.record(
        p, ProposalEvent.Kind.VIEWED, ip="1.2.3.4", user_agent="UA", revision=revision
    )
    events = ok(mcp, "list_proposal_events", {"slug": slug})["items"]
    assert [(e["kind"], e["revision"], e["ip"]) for e in events] == [("viewed", 1, "1.2.3.4")]
    assert refused(mcp, "list_proposal_events", {"slug": "nope"})


def test_tools_need_the_admin_scope(client: Client, auth_server: FakeAuthServer) -> None:
    body = (
        '{"jsonrpc":"2.0","id":1,"method":"tools/call",'
        '"params":{"name":"publish","arguments":{"slug":"x"}}}'
    )
    response = client.post(
        "/mcp",
        body,
        content_type="application/json",
        headers={**auth_server.bearer(scope="login"), "Accept": "application/json"},
    )
    assert response.status_code == 403


def test_deleting_a_cta_target_is_refused_with_the_cta_path(mcp: McpClient) -> None:
    proposal = new_proposal(mcp)
    slug = proposal["slug"]
    ok(mcp, "add_tab", {"slug": slug, "title": "부록", "tab_id": "extra"})
    cta = {
        "type": "cta",
        "items": [{"label": "부록 보기", "target": {"kind": "tab", "tab_id": "extra"}}],
    }
    tab_id, _ = first_block(proposal)
    ok(mcp, "insert_block", {"slug": slug, "tab_id": tab_id, "block": {"id": "go", **cta}})

    text = refused(mcp, "delete_tab", {"slug": slug, "tab_id": "extra"})
    assert text.startswith("저장하지 않았습니다") and "items[0].target.tab_id" in text
    assert ok(mcp, "delete_block", {"slug": slug, "block_id": "go"})
    assert ok(mcp, "delete_tab", {"slug": slug, "tab_id": "extra"})


def test_publish_and_reissue_take_a_chosen_access_code(mcp: McpClient) -> None:
    slug = new_proposal(mcp)["slug"]

    assert "1234" not in refused(mcp, "publish", {"slug": slug, "access_code": "1234"})
    assert "access_code" in refused(mcp, "publish", {"slug": slug, "access_code": "1234"})
    assert ok(mcp, "list_revisions", {"slug": slug})["items"] == []  # nothing was published

    published = ok(mcp, "publish", {"slug": slug, "access_code": "가나다상사-2026"})
    assert published["access_code"] == "가나다상사-2026"
    assert Proposal.objects.get(slug=slug).access_code_hash

    reissued = ok(mcp, "reissue_access_code", {"slug": slug, "access_code": "새 코드 2027"})
    assert reissued["access_code"] == "새 코드 2027"
    auto = ok(mcp, "reissue_access_code", {"slug": slug, "access_code": ""})
    assert re.fullmatch(r"[A-Z0-9]{8}", auto["access_code"])

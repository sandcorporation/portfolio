"""Blog tools through /mcp (#74): registered, read-only marks, refusals as isError results."""

from typing import Any, cast

import pytest
from django.test import Client

from adapters.fake_jwks import FakeAuthServer
from tests.test_mcp import McpClient
from tests.test_mcp_proposals import ok, refused

pytestmark = pytest.mark.django_db

type Data = dict[str, Any]  # Any: tool results are arbitrary JSON

BLOG_TOOLS = {
    "list_posts", "get_post", "create_post", "update_post", "replace_post_block",
    "insert_post_block", "delete_post_block", "publish_post", "unpublish_post", "delete_post",
}  # fmt: skip
READ_ONLY = {"list_posts", "get_post"}


@pytest.fixture
def mcp(client: Client, auth_server: FakeAuthServer) -> McpClient:
    return McpClient(client, auth_server)


def test_blog_tools_are_listed_and_only_readers_are_read_only(mcp: McpClient) -> None:
    listed = cast(Data, mcp.request("tools/list")["result"])
    by_name = {t["name"]: t for t in listed["tools"]}
    assert set(by_name) >= BLOG_TOOLS
    for name in BLOG_TOOLS:
        assert by_name[name]["annotations"]["readOnlyHint"] is (name in READ_ONLY), name
    assert "create_post" in by_name["whoami"]["description"]
    assert "block_schema" in by_name["create_post"]["description"]


def test_write_publish_and_read_a_post(mcp: McpClient) -> None:
    post = ok(mcp, "create_post", {"title": "MCP로 쓴 글", "tags": ["mcp"]})
    slug = post["slug"]
    assert post["status"] == "draft"
    block = {"id": "a", "type": "markdown", "body": "x"}
    ok(mcp, "insert_post_block", {"slug": slug, "block": block})
    block = {"type": "markdown", "body": "y"}
    ok(mcp, "replace_post_block", {"slug": slug, "block_id": "a", "block": block})
    ok(mcp, "update_post", {"slug": slug, "summary": "요약"})
    live = ok(mcp, "publish_post", {"slug": slug})
    assert live["status"] == "published" and live["published_at"]

    listed = ok(mcp, "list_posts", {"published_only": True})["items"]
    assert [p["slug"] for p in listed] == [slug]
    got = ok(mcp, "get_post", {"slug": slug})
    assert got["summary"] == "요약"
    assert got["body"]["tabs"][0]["blocks"][0]["body"] == "y"

    ok(mcp, "unpublish_post", {"slug": slug})
    ok(mcp, "delete_post_block", {"slug": slug, "block_id": "a"})
    assert ok(mcp, "delete_post", {"slug": slug}) == {"deleted": slug}
    assert ok(mcp, "list_posts", {})["items"] == []


def test_refusals_become_tool_errors(mcp: McpClient) -> None:
    slug = ok(mcp, "create_post", {"title": "Refusals"})["slug"]
    bad = refused(mcp, "insert_post_block", {"slug": slug, "block": {"type": "nope"}})
    assert "저장하지 않았습니다" in bad and "body.tabs[0].blocks[0]" in bad
    assert "없습니다" in refused(mcp, "get_post", {"slug": "missing"})
    assert "이미 쓰고 있습니다" in refused(mcp, "create_post", {"title": "x", "slug": slug})

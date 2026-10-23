"""/mcp over Streamable HTTP (JSON responses): initialize -> tools/list -> tools/call."""

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from django.test import Client

from adapters.fake_jwks import FakeAuthServer
from documents.validation import BLOCK_TYPES, JSON, validate_document
from mcpserver.tools import TOOLS
from services import blocks
from services.blocks import EXAMPLES

type Message = dict[str, JSON]

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse


class McpClient:
    """Speaks JSON-RPC to /mcp with a valid owner token, the way Claude Code does."""

    def __init__(self, client: Client, auth_server: FakeAuthServer) -> None:
        self.client = client
        self.headers = {
            **auth_server.bearer(),
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        }
        self.next_id = 0

    def send(self, body: object) -> "_MonkeyPatchedWSGIResponse":
        return self.client.post(
            "/mcp", json.dumps(body), content_type="application/json", headers=self.headers
        )

    def request(self, method: str, params: Message | None = None) -> Message:
        self.next_id += 1
        message: Message = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            message["params"] = params
        response = self.send(message)
        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"
        answer: Message = response.json()
        assert answer["id"] == self.next_id
        return answer

    def call_tool(self, name: str, arguments: Message) -> Message:
        answer = self.request("tools/call", {"name": name, "arguments": arguments})
        result = answer["result"]
        assert isinstance(result, dict)
        return result


@pytest.fixture
def mcp(client: Client, auth_server: FakeAuthServer) -> McpClient:
    return McpClient(client, auth_server)


def test_initialize_list_and_call_tools(mcp: McpClient) -> None:
    init = mcp.request(
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "claude-code", "version": "2"},
        },
    )["result"]
    assert isinstance(init, dict)
    assert init["protocolVersion"] == "2025-06-18"
    assert init["capabilities"] == {"tools": {"listChanged": False}}
    assert mcp.send({"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202

    tools = mcp.request("tools/list")["result"]
    assert isinstance(tools, dict) and isinstance(tools["tools"], list)
    by_name = {tool["name"]: tool for tool in tools["tools"] if isinstance(tool, dict)}
    assert {"whoami", "block_schema"} <= set(by_name)
    for tool in by_name.values():
        schema = tool["inputSchema"]
        assert isinstance(schema, dict) and schema["type"] == "object"

    whoami = mcp.call_tool("whoami", {})
    assert whoami["isError"] is False
    assert whoami["structuredContent"] == {
        "sub": "owner",
        "client_id": "test-client",
        "scopes": ["admin"],
        "expires_at": whoami["structuredContent"]["expires_at"],  # type: ignore[index, call-overload]
    }
    content = whoami["content"]
    assert isinstance(content, list) and isinstance(content[0], dict)
    assert json.loads(str(content[0]["text"])) == whoami["structuredContent"]

    table = mcp.call_tool("block_schema", {"type": "table"})
    assert table["isError"] is False
    found = table["structuredContent"]
    assert isinstance(found, dict) and isinstance(found["schema"], dict)
    assert found["type"] == "table"
    assert "highlight_column" in found["schema"]["properties"]  # type: ignore[operator]
    assert found["example"] == EXAMPLES["table"]
    example_rows = EXAMPLES["table"]["rows"]
    assert isinstance(example_rows, list)
    assert any(
        isinstance(cell, dict) for row in example_rows if isinstance(row, list) for cell in row
    )  # a merged cell


def test_initialize_falls_back_to_newest_known_version(mcp: McpClient) -> None:
    result = mcp.request("initialize", {"protocolVersion": "1999-01-01"})["result"]
    assert isinstance(result, dict)
    assert result["protocolVersion"] == "2025-11-25"


def test_block_schema_without_type_lists_every_type(mcp: McpClient) -> None:
    result = mcp.call_tool("block_schema", {})["structuredContent"]
    assert isinstance(result, dict) and isinstance(result["block_types"], list)
    listed = {entry["type"] for entry in result["block_types"] if isinstance(entry, dict)}
    assert listed == BLOCK_TYPES
    document_schema = result["document_schema"]
    assert isinstance(document_schema, dict)
    assert document_schema["title"] == "Document"


def test_block_schema_unknown_type_is_a_tool_error(mcp: McpClient) -> None:
    result = mcp.call_tool("block_schema", {"type": "hologram"})
    assert result["isError"] is True
    assert "unknown block type 'hologram'" in json.dumps(result["content"])


def test_bad_tool_arguments_are_a_tool_error(mcp: McpClient) -> None:
    assert mcp.call_tool("whoami", {"extra": 1})["isError"] is True


def test_block_schema_returns_the_steps_schema_and_example(mcp: McpClient) -> None:
    result = mcp.call_tool("block_schema", {"type": "steps"})["structuredContent"]

    assert isinstance(result, dict) and result["type"] == "steps"
    assert "StepsBlock" in json.dumps(result["schema"])
    example = result["example"]
    assert isinstance(example, dict) and example["type"] == "steps"
    text = json.dumps(example, ensure_ascii=False)
    assert all(title in text for title in ("강의 대본", "본인 목소리 음성", "강의 영상"))


def test_every_block_type_has_a_valid_example() -> None:
    assert set(EXAMPLES) == BLOCK_TYPES
    blocks: list[JSON] = list(EXAMPLES.values())
    validate_document({"tabs": [{"id": "t", "title": "T", "blocks": blocks}]})


def test_protocol_errors(mcp: McpClient) -> None:
    assert mcp.request("nope")["error"] == {"code": -32601, "message": "method not found: nope"}
    unknown = mcp.request("tools/call", {"name": "rm_rf", "arguments": {}})["error"]
    assert isinstance(unknown, dict) and unknown["code"] == -32602

    response = mcp.client.post(
        "/mcp", "{not json", content_type="application/json", headers=mcp.headers
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == -32700

    assert mcp.send([{"jsonrpc": "2.0", "id": 1, "method": "ping"}]).status_code == 400


def test_get_and_delete_are_405_but_still_need_a_token(
    client: Client, mcp: McpClient, auth_server: FakeAuthServer
) -> None:
    assert client.get("/mcp").status_code == 401
    response = client.get("/mcp", headers=mcp.headers)
    assert response.status_code == 405
    assert response["Allow"] == "POST"
    assert client.delete("/mcp", headers=mcp.headers).status_code == 405


def test_unsupported_protocol_version_header_is_400(mcp: McpClient) -> None:
    mcp.headers["MCP-Protocol-Version"] = "2024-01-01"
    assert mcp.send({"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 400


# --- proposal_guide (#69) ---------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]


def _obj(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def _list(value: object) -> list[object]:
    assert isinstance(value, list)
    return value


def _guide(mcp: McpClient) -> tuple[str, list[object]]:
    result = mcp.call_tool("proposal_guide", {})
    assert result["isError"] is False
    found = _obj(result["structuredContent"])
    guide = found["guide"]
    assert isinstance(guide, str)
    return guide, _list(found["skeleton"])


def _schema_words(node: object) -> set[str]:
    """Every property name and enum/const string anywhere in a JSON Schema."""
    words: set[str] = set()
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            words |= set(props)
        for key in ("enum", "const"):
            value = node.get(key)
            words |= {
                one
                for one in (value if isinstance(value, list) else [value])
                if isinstance(one, str)
            }
        for child in node.values():
            words |= _schema_words(child)
    elif isinstance(node, list):
        for child in node:
            words |= _schema_words(child)
    return words


def test_proposal_guide_is_a_read_only_tool_that_writers_are_pointed_to(mcp: McpClient) -> None:
    init = _obj(mcp.request("initialize", {"protocolVersion": "2025-06-18"})["result"])
    assert "proposal_guide" in str(init["instructions"])

    listed = _list(_obj(mcp.request("tools/list")["result"])["tools"])
    by_name = {str(tool["name"]): tool for tool in map(_obj, listed)}
    assert _obj(by_name["proposal_guide"]["annotations"])["readOnlyHint"] is True
    for writer in (
        "whoami",
        "create_proposal",
        "replace_document",
        "replace_block",
        "insert_block",
    ):
        assert "proposal_guide" in str(by_name[writer]["description"]), writer
    whoami = str(by_name["whoami"]["description"])
    assert whoami.index("proposal_guide") < whoami.index("block_schema")


def test_proposal_guide_gives_general_rules_without_the_example_proposal(mcp: McpClient) -> None:
    guide, _ = _guide(mcp)
    assert guide.startswith("# 제안서 작성 지침")

    # The example proposal is a real customer's: none of its specific values may leak.
    example = json.loads((REPO_ROOT / "fixtures/documents/example-proposal.json").read_text())
    by_id = {b["id"]: b for tab in example["tabs"] for b in tab["blocks"]}
    cover = by_id["cover"]
    leaks = [cover["recipient"], cover["recipient"].split()[0], cover["title"], cover["subtitle"]]
    leaks += [item["value"] for item in by_id["summary-kpi"]["items"]]
    leaks += [c for row in by_id["price-table"]["rows"] for c in row if any(d.isdigit() for d in c)]
    leaks.append(by_id["company-intro"]["title"].removesuffix(" 소개"))  # the company's name
    for leak in leaks:
        assert leak not in guide, leak


def test_proposal_guide_names_only_real_tools_block_types_and_fields(mcp: McpClient) -> None:
    guide, skeleton = _guide(mcp)
    known = set(TOOLS) | set(BLOCK_TYPES) | _schema_words(blocks.document_schema())
    known |= {"contact_title"}  # a client field (list_clients)
    known |= {"estimate", "company"}  # the default tab ids (create_proposal)
    known |= {"skeleton"}  # this tool's own answer
    named = set(re.findall(r"`([A-Za-z][\w-]*)`", guide))
    assert named - known == set()
    assert {"list_clients", "list_media", "issue_preview_url", "publish", "case-ref"} <= named

    tabs = list(map(_obj, skeleton))
    assert [tab["tab_id"] for tab in tabs] == ["estimate", "company"]
    for tab in tabs:
        rows = list(map(_obj, _list(tab["blocks"])))
        assert rows
        for row in rows:
            assert row["type"] in BLOCK_TYPES, row
            assert row["purpose"], row
    estimate = [row["type"] for row in map(_obj, _list(tabs[0]["blocks"]))]
    assert estimate[0] == "cover" and estimate[-1] == "cta"


@pytest.mark.django_db
def test_portfolio_tools_give_the_id_a_case_ref_takes(mcp: McpClient) -> None:
    from documents.blocks import CaseRefItem
    from services import proposals
    from tests.test_portfolio import make
    from tests.test_proposals import make_draft

    item = make("alpha")
    listed = _list(_obj(mcp.call_tool("list_portfolio", {})["structuredContent"])["items"])
    got = _obj(mcp.call_tool("get_portfolio", {"slug": "alpha"})["structuredContent"])

    row = _obj(listed[0])
    assert row["id"] == got["id"] == item.pk
    assert type(row["id"]) is int  # the same type as case-ref's item_id
    assert CaseRefItem.model_fields["item_id"].annotation is int

    draft = make_draft()
    block: dict[str, object] = {
        "id": "cases",
        "type": "case-ref",
        "items": [{"item_id": row["id"]}],
    }
    proposals.replace_block(draft.slug, "cases", block)  # validates: the item exists

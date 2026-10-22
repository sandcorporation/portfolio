"""/mcp over Streamable HTTP (JSON responses): initialize -> tools/list -> tools/call."""

import json
from typing import TYPE_CHECKING

import pytest
from django.test import Client

from adapters.fake_jwks import FakeAuthServer
from documents.validation import BLOCK_TYPES, JSON, validate_document
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
    result = mcp.call_tool("block_schema", {"type": "video"})
    assert result["isError"] is True
    assert "unknown block type 'video'" in json.dumps(result["content"])


def test_bad_tool_arguments_are_a_tool_error(mcp: McpClient) -> None:
    assert mcp.call_tool("whoami", {"extra": 1})["isError"] is True


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

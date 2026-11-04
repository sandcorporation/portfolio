"""MCP over JSON-RPC: one message in, at most one message out. No Django, no HTTP here.

Supported: initialize, ping, tools/list, tools/call, and notifications (ignored).
The server is stateless: no sessions, no server-to-client requests, no resources/prompts.
"""

import json
import logging

from pydantic import ValidationError
from sandcorp_authkit.tokens import AccessToken

from documents.validation import JSON
from mcpserver import (  # noqa: F401  # register
    tools_blog,
    tools_media,
    tools_proposals,
    tools_publishing,
    tools_services,
    tools_shorts,
    tools_tips,
)
from mcpserver.tools import TOOLS, ToolError

# Newest first. initialize answers the client's version when we know it, else the newest.
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
SERVER_INFO: dict[str, JSON] = {"name": "sandcorp-portfolio", "version": "0.1.0"}
INSTRUCTIONS = (
    "Sandcorp portfolio site (https://sandcorp.co.kr). Portfolio items, proposals and blog posts "
    "(/blog) are block documents; call block_schema to see the block types before writing one. "
    "Before writing or rewriting a proposal, read proposal_guide first: it gives the writing "
    "rules and the recommended block order (외주 플랫폼 submissions: platform_mode + "
    "export_proposal_pdf). Before writing or rewriting a blog post, read "
    "blog_guide first. Development tips (/tips) are one markdown body each; before writing or "
    "rewriting a tip, read tip_guide first. YouTube Shorts on the home page come in from the "
    "channel by themselves (every 30 minutes, newest in front); only hiding (is_visible), order "
    "(position, smaller first) and link need changing, with list_shorts/update_short. add_short "
    "is only for putting one up before the automatic sync or bringing back a deleted one. The "
    "outsourced-work services (home 「외주로 맡는 일」 cards and /services/<slug> pages) are rows "
    "of fixed sections; before writing or rewriting one, read service_guide first."
)

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

type RequestId = str | int
type Message = dict[str, JSON]

logger = logging.getLogger(__name__)


class _Fail(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def error(request_id: RequestId | None, code: int, message: str) -> Message:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def dispatch(message: object, token: AccessToken) -> Message | None:
    """Answer a request; return None for a notification or a client response."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return error(None, INVALID_REQUEST, "expected a JSON-RPC 2.0 object")
    method = message.get("method")
    if "id" not in message:
        if method is None and ("result" in message or "error" in message):
            return None  # a response to a server request; this server sends none
        if isinstance(method, str):
            return None  # notification (e.g. notifications/initialized): nothing to answer
        return error(None, INVALID_REQUEST, "missing method")
    request_id = message["id"]
    if isinstance(request_id, bool) or not isinstance(request_id, str | int):
        return error(None, INVALID_REQUEST, "id must be a string or an integer")
    if not isinstance(method, str):
        return error(request_id, INVALID_REQUEST, "missing method")
    params = message.get("params", {})
    if not isinstance(params, dict):
        return error(request_id, INVALID_PARAMS, "params must be an object")
    try:
        result = _call(method, params, token)
    except _Fail as fail:
        return error(request_id, fail.code, fail.message)
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _call(method: str, params: dict[str, JSON], token: AccessToken) -> dict[str, JSON]:
    match method:
        case "initialize":
            return _initialize(params)
        case "ping":
            return {}
        case "tools/list":
            return {"tools": [registered.definition() for registered in TOOLS.values()]}
        case "tools/call":
            return _call_tool(params, token)
        case _:
            raise _Fail(METHOD_NOT_FOUND, f"method not found: {method}")


def _initialize(params: dict[str, JSON]) -> dict[str, JSON]:
    requested = params.get("protocolVersion")
    version = requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
    return {
        "protocolVersion": version,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": SERVER_INFO,
        "instructions": INSTRUCTIONS,
    }


def _call_tool(params: dict[str, JSON], token: AccessToken) -> dict[str, JSON]:
    name = params.get("name")
    arguments = params.get("arguments", {})
    if not isinstance(name, str) or name not in TOOLS:
        raise _Fail(INVALID_PARAMS, f"unknown tool: {name}")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise _Fail(INVALID_PARAMS, "arguments must be an object")
    try:
        result = TOOLS[name].call(token, arguments)
    except ValidationError as exc:
        return _tool_error(f"invalid arguments: {exc.errors(include_url=False)}")
    except ToolError as exc:
        return _tool_error(str(exc))
    except Exception:
        logger.exception("MCP tool %s failed", name)
        raise _Fail(INTERNAL_ERROR, "internal error") from None
    return {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
        "structuredContent": result,
        "isError": False,
    }


def _tool_error(text: str) -> dict[str, JSON]:
    return {"content": [{"type": "text", "text": text}], "isError": True}

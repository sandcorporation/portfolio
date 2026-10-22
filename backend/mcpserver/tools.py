"""MCP tools: thin shells over `services/`. A tool validates its input and shapes its output.

Add a tool with `@tool(name, title, description, InputModel)` on a function
`(token: AccessToken, args: InputModel) -> dict[str, JSON]`. The input model (Pydantic,
`extra="forbid"`) becomes the tool's `inputSchema`; raise `ToolError` for a failure the caller
should read (it becomes an `isError` result, not a protocol error).
Every tool runs behind the `/mcp` bearer check (scope `admin`), so it always has a token.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from documents.validation import BLOCK_TYPES, JSON
from oauth.tokens import AccessToken
from services import blocks

type ToolResult = dict[str, JSON]


class ToolError(Exception):
    """A tool-level failure; the message is shown to the MCP client."""


class RegisteredTool(Protocol):
    @property
    def name(self) -> str: ...

    def definition(self) -> dict[str, JSON]: ...

    def call(self, token: AccessToken, arguments: dict[str, JSON]) -> ToolResult: ...


@dataclass(frozen=True)
class Tool[M: BaseModel]:
    name: str
    title: str
    description: str
    input_model: type[M]
    handler: Callable[[AccessToken, M], ToolResult]

    def definition(self) -> dict[str, JSON]:
        schema: dict[str, JSON] = self.input_model.model_json_schema()
        schema.pop("title", None)
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": schema,
            "annotations": {"readOnlyHint": True},
        }

    def call(self, token: AccessToken, arguments: dict[str, JSON]) -> ToolResult:
        return self.handler(token, self.input_model.model_validate(arguments))


TOOLS: dict[str, RegisteredTool] = {}


def tool[M: BaseModel](
    name: str, title: str, description: str, input_model: type[M]
) -> Callable[[Callable[[AccessToken, M], ToolResult]], Callable[[AccessToken, M], ToolResult]]:
    def register(
        handler: Callable[[AccessToken, M], ToolResult],
    ) -> Callable[[AccessToken, M], ToolResult]:
        if name in TOOLS:
            raise ValueError(f"MCP tool {name!r} is registered twice")
        TOOLS[name] = Tool(name, title, description, input_model, handler)
        return handler

    return register


class NoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BlockSchemaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str | None = Field(
        default=None,
        description="Block type to describe; omit to list every type. One of: "
        + ", ".join(sorted(BLOCK_TYPES)),
    )


@tool(
    "whoami",
    "Who am I",
    "The identity this connection acts as: the token's subject, client and scopes.",
    NoInput,
)
def whoami(token: AccessToken, args: NoInput) -> ToolResult:
    return {
        "sub": token.sub,
        "client_id": token.client_id,
        "scopes": [scope for scope in sorted(token.scopes)],
        "expires_at": token.exp,
    }


@tool(
    "block_schema",
    "Block schema",
    "JSON Schema and a valid example for a block type of the block document (portfolio items "
    "and proposals are tabs of these blocks). Without `type`: every block type with a one-line "
    "description, plus the whole document schema.",
    BlockSchemaInput,
)
def block_schema(token: AccessToken, args: BlockSchemaInput) -> ToolResult:
    if args.type is None:
        return {
            "block_types": [
                {"type": summary["type"], "description": summary["description"]}
                for summary in blocks.block_types()
            ],
            "document_schema": blocks.document_schema(),
        }
    try:
        found = blocks.block_schema(args.type)
    except blocks.UnknownBlockType as exc:
        known = ", ".join(sorted(BLOCK_TYPES))
        raise ToolError(f"unknown block type {exc.block_type!r}; known types: {known}") from exc
    return {
        "type": found["type"],
        "description": found["description"],
        "schema": found["schema"],
        "example": found["example"],
    }

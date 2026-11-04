"""MCP tools for the home page's YouTube Shorts (services.shorts, issue 207): one service call
each."""

from pydantic import BaseModel, ConfigDict, Field
from sandcorp_authkit.tokens import AccessToken

from mcpserver.tools import NoInput, ToolResult, _failure, many, one, tool
from services import shorts
from services.errors import ServiceError

ORDER_NOTE = (
    " The home page shows the visible shorts by position (smaller first), at most "
    f"{shorts.HOME_LIMIT}."
)


class VideoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video: str = Field(min_length=1, max_length=200, description=shorts.VIDEO_HELP)


class AddShortInput(shorts.NewShort):
    pass


class UpdateShortInput(shorts.ShortPatch):
    video: str = Field(
        min_length=1, max_length=200, description="Which short: " + shorts.VIDEO_HELP
    )


@tool(
    "list_shorts",
    "List YouTube Shorts on the home page",
    "Every registered short in home order (hidden ones too), with id, title, position, "
    "is_visible and link." + ORDER_NOTE,
    NoInput,
)
def list_shorts(token: AccessToken, args: NoInput) -> ToolResult:
    return many(shorts.list_shorts)


@tool(
    "add_short",
    "Add a YouTube Short to the home page",
    "Shorts come in from the channel by themselves (every 30 minutes); use this only to put one "
    "up before the automatic sync or to bring back a deleted one (it is then synced again). "
    "video takes the ID or any of its URLs. Omit title to take it from YouTube; omit position "
    "to put it in front of all others (newest first)." + ORDER_NOTE,
    AddShortInput,
    read_only=False,
)
def add_short(token: AccessToken, args: AddShortInput) -> ToolResult:
    return one(lambda: shorts.add_short(args))


@tool(
    "update_short",
    "Update a YouTube Short on the home page",
    'Change the given fields only: title ("" takes it from YouTube again), position, '
    "is_visible (false hides it) or link." + ORDER_NOTE,
    UpdateShortInput,
    read_only=False,
)
def update_short(token: AccessToken, args: UpdateShortInput) -> ToolResult:
    patch = shorts.ShortPatch.model_validate(args.model_dump(exclude={"video"}, exclude_unset=True))
    return one(lambda: shorts.update_short(args.video, patch))


@tool(
    "delete_short",
    "Remove a YouTube Short from the home page",
    "Delete the registration (the video on YouTube stays). A deleted short is not registered "
    "again by the automatic channel sync; add_short brings it back. To take it down for now, "
    "use update_short with is_visible false.",
    VideoInput,
    read_only=False,
)
def delete_short(token: AccessToken, args: VideoInput) -> ToolResult:
    try:
        deleted = shorts.delete_short(args.video)
    except ServiceError as exc:
        raise _failure(exc) from exc
    return {"deleted": deleted}

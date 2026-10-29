"""MCP tools for media: presigned upload start, completion and listing (services.media)."""

from pydantic import BaseModel, ConfigDict, Field
from sandcorp_authkit.tokens import AccessToken

from adapters.storage import StorageNotConfigured
from content.models import Media
from documents.validation import JSON
from mcpserver.tools import ToolError, ToolResult, tool
from services import media as media_service


class StartUploadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(description="The file's name, e.g. hero.png (only kept for display).")
    content_type: str = Field(description="MIME type, e.g. image/png or video/mp4.")
    size: int = Field(description="Exact size in bytes of the file you will PUT.")
    is_public: bool = Field(
        default=True, description="true for site images; false for files only owners can fetch."
    )


class MediaIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_id: int = Field(description="The id start_upload returned.")


class ListMediaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_only: bool = False
    complete_only: bool = Field(default=True, description="false also lists unfinished uploads.")


def _media_out(media: Media) -> dict[str, JSON]:
    return {
        "media_id": media.pk,
        "filename": media.original_filename,
        "content_type": media.content_type,
        "size": media.size,
        "is_public": media.is_public,
        "complete": media.is_complete,
        "url": media_service.public_url(media) if media.is_public and media.is_complete else None,
    }


def _limits() -> str:
    types = ", ".join(sorted(media_service.ALLOWED_TYPES))
    return (
        f"Allowed: {types}. Images up to {media_service.MAX_SIZE // 2**20}MB, audio and video up "
        f"to {media_service.MAX_AV_SIZE // 2**20}MB."
    )


@tool(
    "start_upload",
    "Start a media upload",
    "Step 1 of 2. Returns a presigned PUT URL (valid 15 minutes): PUT the file bytes to it "
    "directly, with the returned headers, then call complete_upload. Compress video for the web "
    "first (short, H.264 mp4). " + _limits(),
    StartUploadInput,
    read_only=False,
)
def start_upload(token: AccessToken, args: StartUploadInput) -> ToolResult:
    try:
        ticket = media_service.start_upload(
            args.filename, args.content_type, args.size, is_public=args.is_public
        )
    except (media_service.InvalidUpload, StorageNotConfigured) as exc:
        raise ToolError(f"업로드를 시작하지 않았습니다: {exc}") from exc
    return {
        "media_id": ticket.media.pk,
        "upload_url": ticket.upload.url,
        "upload_method": "PUT",
        "upload_headers": dict(ticket.upload.headers),
        "next": "PUT the file to upload_url with upload_headers, then call complete_upload.",
    }


@tool(
    "complete_upload",
    "Finish a media upload",
    "Step 2 of 2: after the PUT, confirm the file arrived with the promised type and size. "
    "Returns the media (use media_id in block documents). A mismatch discards the upload.",
    MediaIdInput,
    read_only=False,
)
def complete_upload(token: AccessToken, args: MediaIdInput) -> ToolResult:
    try:
        media = media_service.complete_upload(args.media_id)
    except Media.DoesNotExist as exc:
        raise ToolError(f"미디어 {args.media_id}번이 없습니다") from exc
    except (media_service.InvalidUpload, StorageNotConfigured) as exc:
        raise ToolError(f"업로드를 완료하지 못했습니다: {exc}") from exc
    return _media_out(media)


@tool(
    "list_media",
    "List media",
    "Uploaded files, newest first: media_id (what block documents reference), type, size and "
    "the public URL of public ones.",
    ListMediaInput,
)
def list_media(token: AccessToken, args: ListMediaInput) -> ToolResult:
    items = media_service.list_media(public_only=args.public_only, complete_only=args.complete_only)
    return {"items": [_media_out(m) for m in items]}

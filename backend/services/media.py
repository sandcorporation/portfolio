"""Media: files in object storage that documents and portfolio covers refer to by id.

Two ways in, both ending in `complete_upload`:
- `start_upload` -> the client PUTs to the presigned URL -> `complete_upload` (MCP tools, #24).
- `upload` for a server that already holds the bytes (Django admin).
A media item is referenceable only once `complete_upload` confirmed the object is in the bucket.
"""

import copy
import posixpath
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from adapters.storage import (
    Bucket,
    ObjectStorage,
    PresignedUpload,
    StorageNotConfigured,
    get_storage,
)
from content.models import Media
from documents.validation import JSON

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
}
MAX_SIZE = 20 * 1024 * 1024
UPLOAD_URL_TTL = timedelta(minutes=15)
PRIVATE_URL_TTL = timedelta(minutes=10)


class InvalidUpload(Exception):
    """The file is not something we store (type or size). The message is for the person."""


@dataclass(frozen=True)
class UploadTicket:
    media: Media
    upload: PresignedUpload


def validate_upload(content_type: str, size: int) -> None:
    if content_type not in ALLOWED_IMAGE_TYPES:
        allowed = ", ".join(sorted(ALLOWED_IMAGE_TYPES))
        raise InvalidUpload(f"{content_type or '알 수 없는 형식'}은 올릴 수 없습니다 ({allowed})")
    if size <= 0:
        raise InvalidUpload("빈 파일입니다")
    if size > MAX_SIZE:
        raise InvalidUpload(f"{MAX_SIZE // (1024 * 1024)}MB를 넘는 파일은 올릴 수 없습니다")


def _bucket(media: Media) -> Bucket:
    return Bucket.PUBLIC if media.is_public else Bucket.PRIVATE


def _new_media(filename: str, content_type: str, size: int, is_public: bool) -> Media:
    validate_upload(content_type, size)
    # The key never contains the person's file name: unguessable and safe in any URL.
    key = f"{uuid.uuid4().hex}{ALLOWED_IMAGE_TYPES[content_type]}"
    return Media.objects.create(
        is_public=is_public,
        object_key=key,
        content_type=content_type,
        size=size,
        original_filename=posixpath.basename(filename.replace("\\", "/"))[:255] or "file",
    )


def start_upload(
    filename: str,
    content_type: str,
    size: int,
    *,
    is_public: bool,
    storage: ObjectStorage | None = None,
) -> UploadTicket:
    """Create a pending media item and a presigned PUT URL for it."""
    storage = storage or get_storage()
    media = _new_media(filename, content_type, size, is_public)
    presigned = storage.presign_put(_bucket(media), media.object_key, content_type, UPLOAD_URL_TTL)
    return UploadTicket(media=media, upload=presigned)


def complete_upload(media_id: int, *, storage: ObjectStorage | None = None) -> Media:
    """Confirm the object is in the bucket with the promised type and size, then mark it done."""
    storage = storage or get_storage()
    media = Media.objects.get(pk=media_id)
    if media.is_complete:
        return media
    stored = storage.head(_bucket(media), media.object_key)
    if stored is None:
        raise InvalidUpload("업로드된 파일을 찾을 수 없습니다")
    if stored.content_type != media.content_type or stored.size != media.size:
        storage.delete(_bucket(media), media.object_key)
        media.delete()
        raise InvalidUpload("업로드된 파일이 약속한 형식·크기와 다릅니다")
    media.uploaded_at = timezone.now()
    media.save(update_fields=["uploaded_at"])
    return media


def upload(
    filename: str,
    content_type: str,
    data: bytes,
    *,
    is_public: bool,
    storage: ObjectStorage | None = None,
) -> Media:
    """Store bytes the server already has (Django admin) and mark the media complete."""
    storage = storage or get_storage()
    media = _new_media(filename, content_type, len(data), is_public)
    try:
        storage.put(_bucket(media), media.object_key, data, content_type)
    except Exception:
        media.delete()
        raise
    return complete_upload(media.pk, storage=storage)


def list_media(*, public_only: bool = False, complete_only: bool = True) -> list[Media]:
    items = Media.objects.all()
    if public_only:
        items = items.filter(is_public=True)
    if complete_only:
        items = items.filter(uploaded_at__isnull=False)
    return list(items)


def public_url(media: Media, *, storage: ObjectStorage | None = None) -> str | None:
    """The public URL of a finished public media item; None for private, unfinished or when
    storage is not configured."""
    if not (media.is_public and media.is_complete):
        return None
    try:
        return (storage or get_storage()).public_url(media.object_key)
    except StorageNotConfigured:
        return None


def delete_media(media: Media, *, storage: ObjectStorage | None = None) -> None:
    (storage or get_storage()).delete(_bucket(media), media.object_key)
    media.delete()


def resolve_document(document: dict[str, JSON]) -> dict[str, JSON]:
    """A copy of a stored document with each gallery image's `url` filled in.

    Images whose media is gone or no longer public get no url, and the renderer skips them.
    """
    resolved = copy.deepcopy(document)
    images = [
        image
        for tab in _list(resolved.get("tabs"))
        for block in _list(_dict(tab).get("blocks"))
        if _dict(block).get("type") == "gallery"
        for image in _list(_dict(block).get("images"))
    ]
    ids = {_dict(image).get("media_id") for image in images}
    media = {m.pk: m for m in Media.objects.filter(pk__in=[i for i in ids if isinstance(i, int)])}
    try:
        storage = get_storage() if media else None
    except StorageNotConfigured:
        storage = None  # the site still renders; images without a url are skipped
    for image in images:
        entry = _dict(image)
        media_id = entry.get("media_id")
        found = media.get(media_id) if isinstance(media_id, int) else None
        if found and storage:
            entry["url"] = public_url(found, storage=storage)
    return resolved


def _list(value: JSON) -> list[JSON]:
    return value if isinstance(value, list) else []


def _dict(value: JSON) -> dict[str, JSON]:
    return value if isinstance(value, dict) else {}

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
ALLOWED_AV_TYPES = {
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/flac": ".flac",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}
ALLOWED_TYPES = ALLOWED_IMAGE_TYPES | ALLOWED_AV_TYPES
MAX_SIZE = 20 * 1024 * 1024  # images
MAX_AV_SIZE = 100 * 1024 * 1024  # audio and video: demo clips, not whole recordings
UPLOAD_URL_TTL = timedelta(minutes=15)
# Private media URLs: long enough to start a clip and seek around without a refresh, short enough
# that a copied link stops working soon after the session ends. The page asks again on expiry.
PRIVATE_URL_TTL = timedelta(minutes=10)


class InvalidUpload(Exception):
    """The file is not something we store (type or size). The message is for the person."""


@dataclass(frozen=True)
class UploadTicket:
    media: Media
    upload: PresignedUpload


def validate_upload(content_type: str, size: int) -> None:
    if content_type not in ALLOWED_TYPES:
        allowed = ", ".join(sorted(ALLOWED_TYPES))
        raise InvalidUpload(f"{content_type or '알 수 없는 형식'}은 올릴 수 없습니다 ({allowed})")
    if size <= 0:
        raise InvalidUpload("빈 파일입니다")
    limit = MAX_SIZE if content_type in ALLOWED_IMAGE_TYPES else MAX_AV_SIZE
    if size > limit:
        raise InvalidUpload(f"{limit // (1024 * 1024)}MB를 넘는 파일은 올릴 수 없습니다")


def _bucket(media: Media) -> Bucket:
    return Bucket.PUBLIC if media.is_public else Bucket.PRIVATE


def _new_media(filename: str, content_type: str, size: int, is_public: bool) -> Media:
    validate_upload(content_type, size)
    # The key never contains the person's file name: unguessable and safe in any URL.
    key = f"{uuid.uuid4().hex}{ALLOWED_TYPES[content_type]}"
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


def private_url(
    media: Media, *, storage: ObjectStorage | None = None, download: bool = False
) -> str | None:
    """A presigned GET URL (PRIVATE_URL_TTL) for a finished media item of either bucket. Only for
    a reader the caller has already let in (proposal session, signed preview)."""
    if not media.is_complete:
        return None
    try:
        storage = storage or get_storage()
    except StorageNotConfigured:
        return None
    name = media.original_filename if download else None
    return storage.presign_get(
        _bucket(media), media.object_key, PRIVATE_URL_TTL, download_name=name
    )


@dataclass(frozen=True)
class _Ref:
    """One media reference inside a document: entry[id_key] is the media id, entry[url_key] is
    where the server writes the URL when serving."""

    entry: dict[str, JSON]
    id_key: str
    url_key: str

    @property
    def media_id(self) -> int | None:
        value = self.entry.get(self.id_key)
        return value if isinstance(value, int) and not isinstance(value, bool) else None


def _refs(document: dict[str, JSON]) -> list[_Ref]:
    refs: list[_Ref] = []
    for tab in _list(document.get("tabs")):
        for raw in _list(_dict(tab).get("blocks")):
            block = _dict(raw)
            kind = block.get("type")
            if kind == "gallery":
                refs += [_Ref(_dict(i), "media_id", "url") for i in _list(block.get("images"))]
            elif kind == "audio-compare":
                tracks = [block.get("original"), *_list(block.get("tracks"))]
                refs += [_Ref(_dict(t), "media_id", "url") for t in tracks]
            elif kind == "video":
                refs.append(_Ref(block, "media_id", "url"))
                refs.append(_Ref(block, "poster_media_id", "poster_url"))
    return refs


def referenced_media_ids(document: dict[str, JSON]) -> set[int]:
    return {ref.media_id for ref in _refs(document) if ref.media_id is not None}


def resolve_document(document: dict[str, JSON], *, private: bool = False) -> dict[str, JSON]:
    """A copy of a stored document with each media reference's URL filled in.

    Public media gets its public URL. Private media gets a short-lived presigned URL only when
    `private` (the caller checked the proposal session or preview link); otherwise none.
    References whose media is gone get no URL, and the renderers say so or skip them.
    """
    resolved = copy.deepcopy(document)
    refs = _refs(resolved)
    ids = {ref.media_id for ref in refs if ref.media_id is not None}
    media = {m.pk: m for m in Media.objects.filter(pk__in=ids)}
    try:
        storage = get_storage() if media else None
    except StorageNotConfigured:
        storage = None  # the site still renders; media without a url is skipped
    for ref in refs:
        found = media.get(ref.media_id) if ref.media_id is not None else None
        if not (found and storage):
            continue
        if found.is_public:
            ref.entry[ref.url_key] = public_url(found, storage=storage)
        elif private:
            ref.entry[ref.url_key] = private_url(found, storage=storage)
    return resolved


def document_media_url(
    document: dict[str, JSON], media_id: int, *, download: bool = False
) -> str | None:
    """A fresh URL for media the document refers to, or None (not referenced by this document,
    gone, unfinished). The caller has checked that the reader may see `document`."""
    if media_id not in referenced_media_ids(document):
        return None
    found = Media.objects.filter(pk=media_id).first()
    if found is None:
        return None
    if found.is_public and not download:
        return public_url(found)
    return private_url(found, download=download)


def _list(value: JSON) -> list[JSON]:
    return value if isinstance(value, list) else []


def _dict(value: JSON) -> dict[str, JSON]:
    return value if isinstance(value, dict) else {}

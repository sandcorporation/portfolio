"""YouTube Shorts picked for the home page (issue 207).

Owner side (MCP tools and admin): `list_shorts`, `add_short`, `update_short`, `delete_short`.
A video is named by its 11-character ID or any of its URLs (`youtube.com/shorts/<id>`,
`watch?v=<id>`, `youtu.be/<id>`, `embed/<id>`); `parse_video` turns either into the ID.
An empty title is filled once from oEmbed (`adapters/youtube.py`); if that fails the short is
still saved with an empty title and the home page says 「Sandcorp 쇼츠」.

A new short goes first by default (position one less than the current smallest): a short is
registered right after it is uploaded, so the newest is in front.

New uploads also come in by themselves (issue 211): `sync_from_channel()` reads the channel's
feed and registers every video it has never seen — not a Short yet and not dismissed — with the
feed's title, visible, in front (newest first). It never changes an existing Short (hidden ones,
order and links stay). Deleting a Short dismisses its ID (`DismissedShort`) so the sync does not
bring it back; `add_short` (or adding it in admin) takes the dismissal off. A video the sync finds
to be a regular video is dismissed as well, so it is checked only once. The compose `worker` loop
calls `sync_if_due()` (at most once per `SYNC_EVERY` across processes, like retention);
`manage.py sync_shorts` runs it by hand. The home page never calls YouTube.

Public side: `public_cards()` — the visible ones by position, at most four.
"""

import re
from datetime import datetime, timedelta
from typing import TypedDict
from urllib.parse import parse_qs, urlsplit

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Min
from pydantic import BaseModel, ConfigDict, Field

from adapters import youtube
from content.models import SITE_PATH_PATTERN, DismissedShort, Short
from services.errors import Conflict, NotFound, Rejected

HOME_LIMIT = 4
# The channel sync runs at most this often across every process (django_cache key).
SYNC_EVERY = timedelta(minutes=30)
SYNC_DUE_KEY = "shorts:channel-synced"
FALLBACK_TITLE = "Sandcorp 쇼츠"
CHANNEL_URL = "https://www.youtube.com/@sandcorporation"
# The home section's fixed copy lives in home.html and ShortsSection.tsx; tests compare them.
SECTION_LEAD = "만들고 운영하며 겪은 일을 1분 안팎으로 보여 줍니다."

_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}
_PATH_PREFIXES = ("shorts", "embed", "live", "v")
_SITE_PATH = re.compile(SITE_PATH_PATTERN)

VIDEO_HELP = (
    "The video: its 11-character ID or a URL (youtube.com/shorts/<id>, watch?v=<id>, "
    "youtu.be/<id>)."
)
LINK_HELP = 'Optional path on this site shown under the card, e.g. "/tips/<slug>"; "" removes it.'


def parse_video(value: str) -> str | None:
    """The 11-character video ID in an ID or a YouTube URL; None when there is none."""
    text = value.strip()
    if _ID.match(text):
        return text
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    host = (parts.hostname or "").lower()
    segments = [s for s in parts.path.split("/") if s]
    candidate = ""
    if host == "youtu.be" and segments:
        candidate = segments[0]
    elif host in _YOUTUBE_HOSTS:
        if segments[:1] == ["watch"]:
            candidate = (parse_qs(parts.query).get("v") or [""])[0]
        elif len(segments) >= 2 and segments[0] in _PATH_PREFIXES:
            candidate = segments[1]
    return candidate if _ID.match(candidate) else None


def video_id_or_reject(value: str, path: str = "video") -> str:
    found = parse_video(value)
    if found is None:
        raise Rejected.at(path, "YouTube 영상 ID(11자)나 영상 주소가 아닙니다")
    return found


def _check_link(link: str) -> str:
    link = link.strip()
    if link and not _SITE_PATH.match(link):
        raise Rejected.at("link", '사이트 안 경로여야 합니다(예: "/tips/x")')
    return link


# --- owner side: Pydantic in, Pydantic out ---


class ShortOut(BaseModel):
    id: int
    youtube_id: str
    title: str
    position: int
    is_visible: bool
    link: str
    url: str  # https://www.youtube.com/shorts/<id>
    thumbnail_url: str
    created_at: datetime
    updated_at: datetime


class NewShort(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video: str = Field(min_length=1, max_length=200, description=VIDEO_HELP)
    title: str = Field(
        default="", max_length=200, description="Omit to take the title from YouTube (oEmbed)."
    )
    position: int | None = Field(
        default=None,
        description="Smaller comes first on the home page. Omit to put it in front of all others.",
    )
    is_visible: bool = Field(default=True, description="false keeps it off the home page.")
    link: str = Field(default="", max_length=200, description=LINK_HELP)


class ShortPatch(BaseModel):
    """Fields left out stay as they are."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        default="", max_length=200, description='"" takes the title from YouTube again.'
    )
    position: int = Field(default=0, description="Smaller comes first on the home page.")
    is_visible: bool = Field(default=True)
    link: str = Field(default="", max_length=200, description=LINK_HELP)


def thumbnail_url(youtube_id: str) -> str:
    return f"https://i.ytimg.com/vi/{youtube_id}/hqdefault.jpg"


def short_out(short: Short) -> ShortOut:
    return ShortOut(
        id=short.pk,
        youtube_id=short.youtube_id,
        title=short.title,
        position=short.position,
        is_visible=short.is_visible,
        link=short.link,
        url=youtube.short_url(short.youtube_id),
        thumbnail_url=thumbnail_url(short.youtube_id),
        created_at=short.created_at,
        updated_at=short.updated_at,
    )


def fill_title(short: Short) -> None:
    """An empty title gets the oEmbed one (stays empty when YouTube cannot be read)."""
    if not short.title.strip():
        short.title = youtube.fetch_title(short.youtube_id)


def front_position() -> int:
    """One less than the smallest position now (0 when there are none)."""
    smallest: int | None = Short.objects.aggregate(m=Min("position"))["m"]
    return 0 if smallest is None else smallest - 1


def _short_or_404(video: str) -> Short:
    youtube_id = video_id_or_reject(video)
    short = Short.objects.filter(youtube_id=youtube_id).first()
    if short is None:
        raise NotFound(f"쇼츠 {youtube_id!r}이(가) 없습니다")
    return short


def list_shorts() -> list[ShortOut]:
    """All shorts in home order (hidden ones too)."""
    return [short_out(s) for s in Short.objects.all()]


def add_short(new: NewShort) -> ShortOut:
    youtube_id = video_id_or_reject(new.video)
    link = _check_link(new.link)
    if Short.objects.filter(youtube_id=youtube_id).exists():
        raise Conflict(f"쇼츠 {youtube_id!r}는 이미 등록되어 있습니다")
    short = Short(
        youtube_id=youtube_id,
        title=new.title.strip(),
        position=front_position() if new.position is None else new.position,
        is_visible=new.is_visible,
        link=link,
    )
    fill_title(short)
    try:
        with transaction.atomic():
            short.save()
            undismiss(youtube_id)
    except IntegrityError:
        raise Conflict(f"쇼츠 {youtube_id!r}는 이미 등록되어 있습니다") from None
    return short_out(short)


def update_short(video: str, patch: ShortPatch) -> ShortOut:
    short = _short_or_404(video)
    given = patch.model_fields_set
    if "link" in given:
        short.link = _check_link(patch.link)
    if "title" in given:
        short.title = patch.title.strip()
        fill_title(short)
    if "position" in given:
        short.position = patch.position
    if "is_visible" in given:
        short.is_visible = patch.is_visible
    short.save()
    return short_out(short)


def delete_short(video: str) -> str:
    """Removes it and keeps the channel sync from registering it again; returns the video ID."""
    short = _short_or_404(video)
    with transaction.atomic():
        short.delete()
        dismiss(short.youtube_id)
    return short.youtube_id


# --- dismissed videos and the channel sync (issue 211) ---


def dismiss(youtube_id: str, reason: str = DismissedShort.Reason.DELETED) -> None:
    """The channel sync skips this video from now on (idempotent)."""
    try:
        with transaction.atomic():
            DismissedShort.objects.get_or_create(youtube_id=youtube_id, defaults={"reason": reason})
    except IntegrityError:  # another process dismissed it at the same moment
        pass


def undismiss(youtube_id: str) -> None:
    DismissedShort.objects.filter(youtube_id=youtube_id).delete()


def _register(entry: youtube.FeedEntry) -> bool:
    """A Short for a video seen for the first time; False when another process was first."""
    try:
        with transaction.atomic():
            _, created = Short.objects.get_or_create(
                youtube_id=entry.youtube_id,
                defaults={"title": entry.title, "position": front_position(), "is_visible": True},
            )
    except IntegrityError:
        return False
    return created


def sync_from_channel() -> int:
    """Register the channel's videos never seen before; returns how many Shorts were made."""
    entries = youtube.fetch_channel_feed()
    ids = {e.youtube_id for e in entries if _ID.match(e.youtube_id)}
    if not ids:
        return 0
    seen = set(Short.objects.filter(youtube_id__in=ids).values_list("youtube_id", flat=True))
    seen |= set(
        DismissedShort.objects.filter(youtube_id__in=ids).values_list("youtube_id", flat=True)
    )
    created = 0
    # Oldest first: each goes in front of the last, so the newest ends up first.
    for entry in sorted(entries, key=lambda e: e.published):
        if entry.youtube_id not in ids or entry.youtube_id in seen:
            continue
        seen.add(entry.youtube_id)
        if not youtube.check_is_short(entry.youtube_id):
            dismiss(entry.youtube_id, DismissedShort.Reason.NOT_SHORT)
            continue
        created += _register(entry)
    return created


def sync_if_due() -> int | None:
    """`sync_from_channel()` unless some process ran it within `SYNC_EVERY`; None when skipped."""
    if not cache.add(SYNC_DUE_KEY, True, timeout=int(SYNC_EVERY.total_seconds())):
        return None
    try:
        return sync_from_channel()
    except Exception:
        cache.delete(SYNC_DUE_KEY)  # let the next check retry instead of waiting half an hour
        raise


# --- public side: visible shorts only, plain JSON for the shell ---


class ShortCard(TypedDict):
    youtube_id: str
    title: str  # never empty: 「Sandcorp 쇼츠」 stands in
    url: str  # the Short on YouTube (the card's link without JS)
    thumbnail_url: str
    link: str  # "" when there is none
    link_label: str  # "관련 팁 →" / "관련 글 →" / "관련 링크 →"


def _link_label(link: str) -> str:
    if link.startswith("/tips/"):
        return "관련 팁 →"
    if link.startswith("/blog/"):
        return "관련 글 →"
    return "관련 링크 →"


def card_of(short: Short) -> ShortCard:
    return ShortCard(
        youtube_id=short.youtube_id,
        title=short.title.strip() or FALLBACK_TITLE,
        url=youtube.short_url(short.youtube_id),
        thumbnail_url=thumbnail_url(short.youtube_id),
        link=short.link,
        link_label=_link_label(short.link) if short.link else "",
    )


def public_cards(limit: int = HOME_LIMIT) -> list[ShortCard]:
    """The visible shorts in home order, at most `limit`."""
    return [card_of(s) for s in Short.objects.filter(is_visible=True)[: max(limit, 0)]]

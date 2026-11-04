"""YoutubeGateway for tests: answers from `titles`, `feed` and `regular`, counts calls and can
fail on demand."""

from dataclasses import dataclass, field
from datetime import datetime

from adapters.youtube import YoutubeUnavailable


def atom_feed(*entries: tuple[str, str, datetime]) -> bytes:
    """A channel feed shaped like YouTube's, for (video id, title, published) entries."""
    items = "".join(
        f"<entry><id>yt:video:{vid}</id><yt:videoId>{vid}</yt:videoId>"
        f"<title>{title}</title><published>{published.isoformat()}</published></entry>"
        for vid, title, published in entries
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" '
        'xmlns="http://www.w3.org/2005/Atom"><title>Sandcorp</title>'
        f"{items}</feed>"
    ).encode()


@dataclass
class FakeYoutube:
    titles: dict[str, str] = field(default_factory=dict)  # id -> title; a missing id is a 404
    failing: bool = False
    feed: bytes = field(default_factory=atom_feed)  # the channel feed; empty by default
    regular: set[str] = field(default_factory=set)  # ids /shorts/<id> redirects (regular videos)
    shorts_check_failing: bool = False
    calls: list[str] = field(default_factory=list)

    def title(self, youtube_id: str) -> str:
        self.calls.append(youtube_id)
        if self.failing:
            raise YoutubeUnavailable("가짜 YouTube 장애")
        if youtube_id not in self.titles:
            raise YoutubeUnavailable("HTTP 404")
        return self.titles[youtube_id]

    def channel_feed(self) -> bytes:
        self.calls.append("feed")
        if self.failing:
            raise YoutubeUnavailable("가짜 YouTube 장애")
        return self.feed

    def is_short(self, youtube_id: str) -> bool:
        self.calls.append(f"is_short:{youtube_id}")
        if self.failing or self.shorts_check_failing:
            raise YoutubeUnavailable("가짜 YouTube 장애")
        return youtube_id not in self.regular

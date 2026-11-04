"""YoutubeGateway for tests: answers from `titles`, counts calls and can fail on demand."""

from dataclasses import dataclass, field

from adapters.youtube import YoutubeUnavailable


@dataclass
class FakeYoutube:
    titles: dict[str, str] = field(default_factory=dict)  # id -> title; a missing id is a 404
    failing: bool = False
    calls: list[str] = field(default_factory=list)

    def title(self, youtube_id: str) -> str:
        self.calls.append(youtube_id)
        if self.failing:
            raise YoutubeUnavailable("가짜 YouTube 장애")
        if youtube_id not in self.titles:
            raise YoutubeUnavailable("HTTP 404")
        return self.titles[youtube_id]

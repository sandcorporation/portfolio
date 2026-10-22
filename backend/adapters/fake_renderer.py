"""PdfRenderer for tests: it records the URLs it was asked to print and can fail on demand."""

from dataclasses import dataclass, field

from adapters.renderer import RenderFailed

FAKE_PDF = b"%PDF-1.7\n% fake renderer\n%%EOF\n"


@dataclass
class FakeRenderer:
    urls: list[str] = field(default_factory=list)
    failing: bool = False

    def render(self, url: str) -> bytes:
        self.urls.append(url)
        if self.failing:
            raise RenderFailed("가짜 렌더러 장애")
        return FAKE_PDF

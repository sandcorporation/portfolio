"""PDF renderer behind a narrow interface: a headless Chromium (browserless) prints a page to PDF.

The project runs its own browserless container (`renderer` in docker-compose.prod.yml), reachable
only on the compose network. We use its REST `/pdf` endpoint: one HTTP request that opens the URL,
waits until the print page says it is ready (`document.body.dataset.printReady`, set by #16 to
"true", or "timeout" when media did not load in time) and returns the PDF bytes. No CDP client
library is needed. The fake in `adapters/fake_renderer.py` stands in for tests.
"""

import json
import urllib.error
import urllib.request
from typing import Protocol
from urllib.parse import quote

from django.conf import settings

# The print page flips this once its blocks and media have settled (see frontend print mode).
PRINT_READY = "() => ['true', 'timeout'].includes(document.body.dataset.printReady)"


class RenderFailed(Exception):
    """The renderer could not produce a PDF (unreachable, refused, timed out or not configured)."""


class PdfRenderer(Protocol):
    def render(self, url: str) -> bytes:
        """The PDF of the page at `url` (an address the renderer can reach). Raises RenderFailed."""
        ...


def pdf_request_body(url: str, timeout_ms: int) -> dict[str, object]:
    return {
        "url": url,
        "gotoOptions": {"waitUntil": "load", "timeout": timeout_ms},
        "waitForFunction": {"fn": PRINT_READY, "polling": 200, "timeout": timeout_ms},
        "options": {"format": "A4", "printBackground": True, "preferCSSPageSize": True},
    }


class BrowserlessRenderer:
    def __init__(self, base_url: str, token: str, timeout_seconds: int) -> None:
        self._endpoint = f"{base_url.rstrip('/')}/pdf?token={quote(token, safe='')}"
        self._timeout = timeout_seconds

    def render(self, url: str) -> bytes:
        body = pdf_request_body(url, self._timeout * 1000)
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            # Generous socket timeout: browserless itself gives up after `timeout` per step.
            with urllib.request.urlopen(request, timeout=self._timeout * 2 + 10) as response:  # noqa: S310
                data: bytes = response.read()
        except urllib.error.HTTPError as e:
            detail = e.read(500).decode(errors="replace")
            raise RenderFailed(f"렌더러 HTTP {e.code}: {detail}") from None
        except (urllib.error.URLError, OSError) as e:
            raise RenderFailed(f"렌더러에 닿지 못함: {e}") from None
        if not data.startswith(b"%PDF"):
            raise RenderFailed("렌더러가 PDF가 아닌 응답을 돌려줌")
        return data


class UnconfiguredRenderer:
    """No token set: every render fails, so PDFs end up failed while the site keeps working."""

    def render(self, url: str) -> bytes:
        raise RenderFailed("PDF_RENDERER_TOKEN이 설정되지 않음")


def get_renderer() -> PdfRenderer:
    token: str = settings.PDF_RENDERER_TOKEN
    if not token:
        return UnconfiguredRenderer()
    return BrowserlessRenderer(
        settings.PDF_RENDERER_URL, token, settings.PDF_RENDER_TIMEOUT_SECONDS
    )

"""Failures a service function reports. The ninja API and MCP tools each turn them into their own
error shape (HTTP status / `isError` result); neither invents rules of its own."""

from documents.validation import DocumentError


class ServiceError(Exception):
    """Base class; `str(exc)` is a message a person can read."""


class NotFound(ServiceError):
    pass


class Conflict(ServiceError):
    pass


class Rejected(ServiceError):
    """The input was refused and nothing was saved. `errors` name where, e.g.
    `body.tabs[0].blocks[1].images[0].media_id` (a block path), `cover_media_id` or `slug`."""

    def __init__(self, errors: list[DocumentError]) -> None:
        super().__init__("; ".join(f"{e.path}: {e.reason}" for e in errors))
        self.errors = errors

    @classmethod
    def at(cls, path: str, reason: str) -> "Rejected":
        return cls([DocumentError(path, reason)])

    def lines(self) -> list[str]:
        return [f"{e.path}: {e.reason}" for e in self.errors]


class RateLimited(ServiceError):
    """Too many requests from one caller; nothing was saved."""

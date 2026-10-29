"""Signed, short-lived preview links (#147): a proposal draft (`/preview/<token>`) and a blog
post draft (`/preview/blog/<token>`) share the signing, each with its own salt so a token of one
never opens the other."""

from datetime import datetime, timedelta

from django.core import signing
from django.utils import timezone
from pydantic import BaseModel


class PreviewLink(BaseModel):
    url: str
    expires_at: datetime


class BadPreviewToken(Exception):
    pass


class ExpiredPreviewToken(BadPreviewToken):
    pass


def issue(*, salt: str, value: str, path: str, max_age: int) -> PreviewLink:
    """A link to `path` + the signed `value`, good for `max_age` seconds."""
    token = signing.TimestampSigner(salt=salt).sign(value)
    expires_at = timezone.now() + timedelta(seconds=max_age)
    return PreviewLink(url=f"{path}{token}", expires_at=expires_at)


def unsign(token: str, *, salt: str, max_age: int) -> str:
    """The value a link carries, or `ExpiredPreviewToken`/`BadPreviewToken`."""
    try:
        return signing.TimestampSigner(salt=salt).unsign(token, max_age=max_age)
    except signing.SignatureExpired:
        raise ExpiredPreviewToken from None
    except signing.BadSignature:
        raise BadPreviewToken from None

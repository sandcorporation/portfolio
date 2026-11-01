"""Inquiries: leave one, list them, mark them handled.

`submit` is the one entry for both the browser form and the server-to-server post from another
Sandcorp site. Whether the caller is trusted (it proved the shared secret) is decided by the
endpoint; here it only decides what is believed: a trusted caller names its own `site`, skips the
honeypot and the IP limit. An untrusted one is always `portfolio`.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from adapters.notify import Field as NotifyField
from adapters.notify import Notification, get_notifier
from content.models import Inquiry
from services.errors import NotFound, RateLimited

logger = logging.getLogger(__name__)

DEFAULT_SITE = "portfolio"
Kind = Literal[
    "문의", "제안", "신규 개발", "유지보수", "기타", "MCP 연동", "Claude Code 자동화"
]  # Inquiry.Kind values
Text = Annotated[str, StringConstraints(strip_whitespace=True)]


class NewInquiry(BaseModel):
    """What a visitor (or the news site) sends. Unknown keys are ignored."""

    model_config = ConfigDict(extra="ignore")

    name: Text = Field(min_length=1, max_length=80)
    company: Text = Field(default="", max_length=120)
    contact: Text = Field(min_length=1, max_length=200)
    message: Text = Field(min_length=1, max_length=4000)
    kind: Kind = "문의"
    site: Text = Field(default=DEFAULT_SITE, max_length=40, pattern=r"^[a-z0-9][a-z0-9-]*$")
    website: str = Field(default="", max_length=500)  # the honeypot; real people leave it empty

    @field_validator("site", mode="before")
    @classmethod
    def blank_site_is_default(cls, value: object) -> object:
        return DEFAULT_SITE if value in (None, "") else value


class InquiryOut(BaseModel):
    id: int
    site: str
    kind: str
    name: str
    company: str
    contact: str
    message: str
    created_at: datetime
    handled_at: datetime | None


def _out(inquiry: Inquiry) -> InquiryOut:
    return InquiryOut(
        id=inquiry.pk,
        site=inquiry.site,
        kind=inquiry.kind,
        name=inquiry.name,
        company=inquiry.company,
        contact=inquiry.contact,
        message=inquiry.message,
        created_at=inquiry.created_at,
        handled_at=inquiry.handled_at,
    )


@dataclass(frozen=True)
class Received:
    """`inquiry` is None when the honeypot swallowed it; the caller still answers success."""

    inquiry: InquiryOut | None


def _take_slot(ip: str) -> None:
    """Count this submission against the IP; refuse past the limit. Nothing is saved on refusal."""
    key = f"inquiry-ip:{ip}"
    window: int = settings.INQUIRY_RATE_WINDOW_SECONDS
    cache.add(key, 0, window)  # starts the window only once
    try:
        used = cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, window)
        used = 1
    if used > settings.INQUIRY_RATE_LIMIT:
        raise RateLimited("문의가 너무 많습니다. 잠시 후 다시 시도해 주세요.")


def notification_for(inquiry: Inquiry) -> Notification:
    fields = [
        NotifyField("사이트", inquiry.site, inline=True),
        NotifyField("구분", inquiry.kind, inline=True),
        NotifyField("이름", inquiry.name, inline=True),
    ]
    if inquiry.company:
        fields.append(NotifyField("회사", inquiry.company, inline=True))
    fields.append(NotifyField("연락처", inquiry.contact))
    return Notification(
        title=f"새 {inquiry.kind} · {inquiry.site}",
        text=inquiry.message,
        fields=tuple(fields),
    )


def submit(data: NewInquiry, *, trusted: bool, ip: str) -> Received:
    if not trusted:
        if data.website:  # a bot filled the hidden field: look successful, keep nothing
            return Received(None)
        _take_slot(ip)
    inquiry = Inquiry.objects.create(
        site=data.site if trusted else DEFAULT_SITE,
        kind=data.kind,
        name=data.name,
        company=data.company,
        contact=data.contact,
        message=data.message,
    )
    try:  # saved already: an alert problem of any kind must not undo or fail the receipt
        get_notifier().send(notification_for(inquiry))
    except Exception:
        logger.exception("inquiry alert crashed")
    return Received(_out(inquiry))


def list_inquiries(*, unhandled_only: bool = False, limit: int = 50) -> list[InquiryOut]:
    rows = Inquiry.objects.all()
    if unhandled_only:
        rows = rows.filter(handled_at__isnull=True)
    return [_out(i) for i in rows[:limit]]


def mark_handled(inquiry_id: int) -> InquiryOut:
    """Idempotent: handling an already handled inquiry keeps its first handled time."""
    inquiry = Inquiry.objects.filter(pk=inquiry_id).first()
    if inquiry is None:
        raise NotFound(f"문의 {inquiry_id}번이 없습니다")
    if inquiry.handled_at is None:
        inquiry.handled_at = timezone.now()
        inquiry.save(update_fields=["handled_at"])
    return _out(inquiry)

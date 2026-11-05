"""Operating settings the owner can change in the admin without a restart (#233).

`get(name)` answers the admin override when there is one, else `settings.<name>` (the `.env`
value). Only names in `REGISTRY` exist here; everything else stays `.env`-only.

Every process (web workers and the `worker` container) shares one snapshot of all overrides in
`django_cache` (`SNAPSHOT_KEY`). Writes rebuild it from the DB in `transaction.on_commit`, so the
next read anywhere sees the new value; a missing snapshot is rebuilt with `cache.add` (a reader
racing a write can never put an older snapshot back over the writer's). Inside a request the
snapshot is read once (`request_scope`, set by `core.middleware.RuntimeSettingsMiddleware`);
outside a request (the worker loop, commands) every `get` reads the shared cache — no process
keeps a value in memory.

Secrets are sealed (`services/sealed_box.py`) in the DB and in the snapshot; the plain value only
exists in the return value of `get`. A secret that no longer opens (`SECRET_KEY` changed) falls
back to `.env` and the admin shows 「다시 넣어야 함」.
"""

import logging
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, transaction

from content.models import RuntimeSetting
from services.errors import Rejected
from services.sealed_box import Box

logger = logging.getLogger(__name__)

SNAPSHOT_KEY = "runtime-settings:snapshot"
SNAPSHOT_SECONDS = 24 * 60 * 60  # rebuilt from the DB on a miss; writes replace it at once
_box = Box(b"portfolio.runtime-setting")

Check = Callable[[str], str | None]  # the reason the value is refused, or None


def _url(value: str) -> str | None:
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc or re.search(r"\s", value):
        return "http(s):// 주소여야 합니다"
    return None


def _https_url(value: str) -> str | None:
    if _url(value) is not None or not value.startswith("https://"):
        return "https:// 주소여야 합니다"
    return None


def _pattern(regex: str, reason: str) -> Check:
    compiled = re.compile(regex)

    def check(value: str) -> str | None:
        return None if compiled.fullmatch(value) else reason

    return check


def _one_line(limit: int) -> Check:
    def check(value: str) -> str | None:
        if len(value) > limit or "\n" in value or "\r" in value:
            return f"한 줄, {limit}자 이하여야 합니다"
        return None

    return check


@dataclass(frozen=True)
class Spec:
    name: str
    description: str
    check: Check
    secret: bool = False
    may_be_empty: bool = True  # an empty override switches the feature off


REGISTRY: dict[str, Spec] = {
    s.name: s
    for s in (
        Spec(
            "DISCORD_WEBHOOK_URL",
            "Discord 활동 알림 웹훅(문의 접수 등). 비면 알림 없음.",
            _https_url,
            secret=True,
        ),
        Spec(
            "DISCORD_ALERTS_WEBHOOK_URL",
            "Discord 경고 알림 웹훅. 비면 활동 웹훅으로 보냄.",
            _https_url,
            secret=True,
        ),
        Spec("FORESIGHT_API_URL", "Foresight 최근 기사 JSON(홈 「최근 뉴스」). 비면 끔.", _url),
        Spec("FORESIGHT_STATS_URL", "Foresight 집계(홈 증거 행 「N건/일」). 비면 끔.", _url),
        Spec("METRICS_API_URL", "sandcorp-metrics 방문 집계(홈 숫자). 비면 끔.", _url),
        Spec("METRICS_SNIPPET_URL", "방문 집계 스니펫 스크립트. 비면 안 넣음.", _url),
        Spec(
            "METRICS_SITE_KEY",
            "스니펫의 data-site 값.",
            _pattern(r"[a-z0-9][a-z0-9_-]{0,39}", "영소문자·숫자·-·_ 40자 이하여야 합니다"),
            may_be_empty=False,
        ),
        Spec(
            "YOUTUBE_CHANNEL_ID",
            "쇼츠를 자동으로 가져올 채널 ID(UC…). 비면 동기화 끔.",
            _pattern(r"UC[A-Za-z0-9_-]{22}", "UC로 시작하는 24자 채널 ID여야 합니다"),
        ),
        Spec("YOUTUBE_OEMBED_URL", "쇼츠 제목을 읽는 oEmbed 주소. 비면 제목을 안 읽음.", _url),
        Spec(
            "GOOGLE_SITE_VERIFICATION",
            "구글 서치 콘솔 소유확인 코드. 비면 태그 없음.",
            _pattern(r"[A-Za-z0-9_-]{1,100}", "영문·숫자·-·_ 100자 이하여야 합니다"),
        ),
        Spec(
            "NAVER_SITE_VERIFICATION",
            "네이버 서치어드바이저 소유확인 코드. 비면 태그 없음.",
            _pattern(r"[A-Za-z0-9_-]{1,100}", "영문·숫자·-·_ 100자 이하여야 합니다"),
        ),
        Spec("SUPPLIER_NAME", "제안서 표지의 공급자 이름.", _one_line(60), may_be_empty=False),
    )
}


class UnknownSetting(Rejected):
    pass


class InvalidSetting(Rejected):
    pass


class Snapshot(TypedDict):
    version: int
    values: dict[str, str]  # name -> stored value (sealed for secrets)


_request_memo: ContextVar[dict[str, Snapshot] | None] = ContextVar(
    "runtime_settings_memo", default=None
)


@contextmanager
def request_scope() -> Iterator[None]:
    """Read the shared snapshot at most once inside this block (one request)."""
    token = _request_memo.set({})
    try:
        yield
    finally:
        _request_memo.reset(token)


def _from_db(version: int) -> Snapshot:
    return {
        "version": version,
        "values": {r.name: r.value for r in RuntimeSetting.objects.filter(name__in=REGISTRY)},
    }


def _valid_snapshot(raw: object) -> Snapshot | None:
    if not isinstance(raw, dict):
        return None
    version, values = raw.get("version"), raw.get("values")
    if not isinstance(version, int) or not isinstance(values, dict):
        return None
    return {"version": version, "values": {str(k): str(v) for k, v in values.items()}}


def _shared_snapshot() -> Snapshot:
    """The shared snapshot; with the DB or cache table unreachable, no overrides (`.env`)."""
    try:
        snap = _valid_snapshot(cache.get(SNAPSHOT_KEY))
        if snap is None:
            snap = _from_db(0)
            cache.add(SNAPSHOT_KEY, snap, SNAPSHOT_SECONDS)
    except DatabaseError:
        logger.warning("운영 설정을 읽지 못함 — .env 값을 씀", exc_info=True)
        return {"version": 0, "values": {}}
    return snap


def _snapshot() -> Snapshot:
    memo = _request_memo.get()
    if memo is None:
        return _shared_snapshot()
    if "snap" not in memo:
        memo["snap"] = _shared_snapshot()
    return memo["snap"]


def _publish() -> None:
    """Rebuild the shared snapshot from the DB with a higher version (after a commit)."""
    previous = _valid_snapshot(cache.get(SNAPSHOT_KEY))
    cache.set(SNAPSHOT_KEY, _from_db((previous or {"version": 0})["version"] + 1), SNAPSHOT_SECONDS)
    memo = _request_memo.get()
    if memo is not None:
        memo.clear()


def _spec(name: str) -> Spec:
    try:
        return REGISTRY[name]
    except KeyError:
        raise UnknownSetting.at("name", f"운영 설정에 없는 이름: {name}") from None


def env_value(name: str) -> str:
    value: str = getattr(settings, _spec(name).name)
    return value


def get(name: str) -> str:
    """The admin override when there is one (and, for a secret, it still opens), else `.env`."""
    spec = _spec(name)
    stored = _snapshot()["values"].get(name)
    if stored is None:
        return env_value(name)
    if not spec.secret:
        return stored
    if stored == "":
        return ""
    plain = _box.open_(stored)
    if plain is None:
        logger.warning("운영 설정 %s를 열 수 없음(SECRET_KEY 변경?) — .env 값을 씀", name)
        return env_value(name)
    return plain


def _write(name: str, stored: str, by: str) -> None:
    with transaction.atomic():
        RuntimeSetting.objects.update_or_create(
            name=name,
            defaults={"value": stored, "is_secret": REGISTRY[name].secret, "updated_by": by},
        )
        transaction.on_commit(_publish)


def set_value(name: str, value: str, *, by: str) -> bool:
    """Override with `value`. For a secret an empty value keeps the current one (False)."""
    spec = _spec(name)
    value = value.strip()
    if value == "":
        if spec.secret:
            return False
        raise InvalidSetting.at(name, "값이 비었습니다. 끄려면 「빈 값으로 덮어쓰기」를 쓰세요")
    reason = spec.check(value)
    if reason is not None:
        raise InvalidSetting.at(name, reason)  # never the value: it may be a secret
    _write(name, _box.seal(value) if spec.secret else value, by)
    return True


def set_empty(name: str, *, by: str) -> None:
    """Override with an empty value: the feature is switched off whatever `.env` says."""
    spec = _spec(name)
    if not spec.may_be_empty:
        raise InvalidSetting.at(name, "빈 값으로 둘 수 없습니다")
    _write(name, "", by)


def clear(name: str) -> bool:
    """Drop the override: `.env` applies again. False when there was none."""
    _spec(name)
    with transaction.atomic():
        deleted, _ = RuntimeSetting.objects.filter(name=name).delete()
        transaction.on_commit(_publish)
    return deleted > 0


@dataclass(frozen=True)
class Row:
    """What the admin shows for one setting. A secret's value is never in it, only its tail."""

    name: str
    description: str
    secret: bool
    source: str  # "DB" | ".env"
    shown: str  # the value for plain settings; "설정됨 · …abcd" / "비어 있음" for secrets
    unreadable: bool  # a secret override that no longer opens: enter it again
    may_be_empty: bool
    updated_at: datetime | None
    updated_by: str


def _secret_shown(plain: str) -> str:
    return f"설정됨 · …{plain[-4:]}" if plain else "비어 있음"


def row(name: str) -> Row:
    spec = _spec(name)
    db = RuntimeSetting.objects.filter(name=name).first()
    unreadable = False
    if db is None:
        source, plain = ".env", env_value(name)
    else:
        source, plain = "DB", db.value
        if spec.secret and db.value:
            opened = _box.open_(db.value)
            unreadable = opened is None
            plain = opened or ""
    if spec.secret:
        shown = "다시 넣어야 함 (지금은 .env 값을 씀)" if unreadable else _secret_shown(plain)
    else:
        shown = plain
    return Row(
        name=name,
        description=spec.description,
        secret=spec.secret,
        source=source,
        shown=shown,
        unreadable=unreadable,
        may_be_empty=spec.may_be_empty,
        updated_at=db.updated_at if db else None,
        updated_by=db.updated_by if db else "",
    )


def rows() -> list[Row]:
    return [row(name) for name in REGISTRY]

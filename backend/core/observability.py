"""Errors go to our self-hosted GlitchTip (issue 235) through the Sentry SDK.

Nothing happens without a DSN: dev, CI and the tests never set `SENTRY_DSN`, so the SDK stays off
and nothing leaves the machine. Production gets it from compose (`SENTRY_DSN_BACKEND` in `.env`).

`release` is the deployed commit sha (40 hex chars), so a diagnosis can `git show <release>:<path>`:
`SENTRY_RELEASE` if set, else the tag of `PORTFOLIO_IMAGE` (Jenkins deploys
`ghcr.io/sandcorporation/portfolio:<sha>` and compose passes that variable through — a rollback
runs an older image and so reports the older sha).

What is never sent (`before_send`), on top of `send_default_pii=False` and no request bodies:

- cookies, `Authorization`-like headers, frame local variables, and token-shaped strings
  (bearer tokens, JWTs, long opaque strings, the signed token in `/preview/…`·`/print/…` URLs)
  in the message, exception values, extra, request and breadcrumbs;
- refusals we raise on purpose: `Http404`, `PermissionDenied`, `SuspiciousOperation` (with
  `DisallowedHost`), the services' `ServiceError` family (`NotFound`, `Conflict`, `Rejected`, …)
  and any exception carrying a 4xx `status_code` (ninja's `HttpError`);
- anything raised inside `manage.py shell` (also `-c`): a typo a person made is not an app bug
  (codemit GlitchTip issue 107).
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping

from sentry_sdk.types import Event, Hint

ENVIRONMENT = "production"
_SHA = re.compile(r"[0-9a-f]{40}")


def release() -> str | None:
    """The deployed commit: `SENTRY_RELEASE`, else the sha tag of `PORTFOLIO_IMAGE`, else None."""
    explicit = os.environ.get("SENTRY_RELEASE", "").strip()
    if explicit:
        return explicit
    image = os.environ.get("PORTFOLIO_IMAGE", "").strip()
    _, colon, tag = image.rpartition(":")
    return tag if colon and _SHA.fullmatch(tag) else None


_SHELL_MODULE = "django.core.management.commands.shell"
_SHELL_PATH = "django/core/management/commands/shell.py"


def _frames(event: Mapping[str, object]) -> list[Mapping[str, object]]:
    found: list[Mapping[str, object]] = []
    exception = event.get("exception")
    values = exception.get("values") if isinstance(exception, Mapping) else None
    for value in values if isinstance(values, list) else []:
        stacktrace = value.get("stacktrace") if isinstance(value, Mapping) else None
        frames = stacktrace.get("frames") if isinstance(stacktrace, Mapping) else None
        found.extend(
            f for f in (frames if isinstance(frames, list) else []) if isinstance(f, Mapping)
        )
    return found


def _from_manage_shell(event: Mapping[str, object]) -> bool:
    for frame in _frames(event):
        if frame.get("module") == _SHELL_MODULE:
            return True
        for key in ("abs_path", "filename"):
            if str(frame.get(key) or "").replace("\\", "/").endswith(_SHELL_PATH):
                return True
    return False


def _is_expected_refusal(exc: BaseException) -> bool:
    from django.core.exceptions import PermissionDenied, SuspiciousOperation
    from django.http import Http404

    from services.errors import ServiceError

    if isinstance(exc, (Http404, PermissionDenied, SuspiciousOperation, ServiceError)):
        return True
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and 400 <= status < 500


_CREDENTIAL_HEADERS = frozenset(
    {"cookie", "set-cookie", "authorization", "proxy-authorization", "x-api-key", "x-csrftoken"}
)
_TOKEN_PATTERNS = (
    re.compile(r"(?i)\b(bearer|basic|token)\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"),  # JWT
    re.compile(
        r"(?i)((?:token|secret|password|passwd|api[_-]?key|code|session)[\"']?\s*[=:]\s*)[^\s&,;\"']+"
    ),
    re.compile(r"(/(?:preview/[a-z]+|print(?:/draft)?)/)[^/\s?#\"']+"),  # signed page tokens
    re.compile(r"\b[A-Za-z0-9_+=]{40,}"),  # long opaque values (no paths, slugs)
)
_FILTERED = "[Filtered]"


def scrub_text(text: str) -> str:
    """Token-shaped parts of a string replaced with `[Filtered]`."""
    for pattern in _TOKEN_PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda m: m.group(1) + _FILTERED, text)
        else:
            text = pattern.sub(_FILTERED, text)
    return text


def _scrub(value: object) -> object:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def scrub(event: Event) -> Event:
    """Remove what may carry credentials before the event leaves (in place, also returned)."""
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("cookies", None)
        request.pop("data", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            for name in list(headers):
                if str(name).lower() in _CREDENTIAL_HEADERS:
                    del headers[name]
        event["request"] = _scrub(request)  # type: ignore[typeddict-item]  # same shape, strings scrubbed
    for frame in _frames(event):
        if isinstance(frame, dict):
            frame.pop("vars", None)
    exception = event.get("exception")
    for value in exception.get("values", []) if isinstance(exception, dict) else []:
        if isinstance(value, dict) and isinstance(value.get("value"), str):
            value["value"] = scrub_text(value["value"])
    for key in ("message", "logentry", "extra", "breadcrumbs"):
        if key in event:
            event[key] = _scrub(event[key])  # type: ignore[typeddict-item]  # same shape, scrubbed
    return event


def before_send(event: Event, hint: Hint) -> Event | None:
    """Drop expected refusals and `manage.py shell` errors; scrub everything else."""
    if _from_manage_shell(event):
        return None
    exc_info = hint.get("exc_info")
    exc = exc_info[1] if isinstance(exc_info, tuple) else None
    if isinstance(exc, BaseException) and _is_expected_refusal(exc):
        return None
    return scrub(event)


def init_options(dsn: str) -> dict[str, object]:
    """`sentry_sdk.init` keywords — the tests start the SDK with these and a keeping transport."""
    from sentry_sdk.integrations.django import DjangoIntegration

    return {
        "dsn": dsn,
        "release": release(),
        "environment": ENVIRONMENT,
        "integrations": [DjangoIntegration()],
        "send_default_pii": False,
        "include_local_variables": False,
        "max_request_body_size": "never",
        "traces_sample_rate": 0.0,
        "before_send": before_send,
    }


def configure() -> bool:
    """Start the SDK when `SENTRY_DSN` is set (settings.py calls this once). True if started."""
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(**init_options(dsn))  # type: ignore[arg-type]  # init's keywords are typed one by one
    return True


def public_config(path: str) -> dict[str, str] | None:
    """What the browser SDK needs (`window.__PUBLIC__`), or None: no frontend DSN, or a `/print/`
    page (opened by the PDF renderer, not by people)."""
    from django.conf import settings

    dsn = str(settings.SENTRY_DSN_FRONTEND).strip()
    if not dsn or path.startswith("/print/"):
        return None
    config = {"sentryDsn": dsn, "sentryEnvironment": ENVIRONMENT}
    found = release()
    if found:
        config["sentryRelease"] = found
    return config

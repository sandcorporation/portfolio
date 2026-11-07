"""GlitchTip error reports (issue 235): off without a DSN, release from the deployed image,
`before_send` drops refusals and shell errors and scrubs credentials, and the page shell hands the
browser its DSN except on /print/. Nothing leaves the machine: the DSN is fake and a transport
keeps the envelopes."""

import io
import sys
from collections.abc import Iterator

import pytest
import sentry_sdk
from django.core.exceptions import DisallowedHost, PermissionDenied
from django.core.management import call_command
from django.http import Http404
from django.test import Client, override_settings
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport
from sentry_sdk.types import Event, Hint

from core import observability
from core.management.commands.glitchtip_test import GlitchTipOnboardingTest
from services.errors import Conflict, NotFound, Rejected

FAKE_DSN = "https://public@example.invalid/1"
SHA = "0123456789abcdef0123456789abcdef01234567"


class KeepingTransport(Transport):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[Event] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        event = envelope.get_event()
        if event is not None:
            self.events.append(event)


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> Iterator[KeepingTransport]:
    monkeypatch.setenv("PORTFOLIO_IMAGE", f"ghcr.io/sandcorporation/portfolio:{SHA}")
    monkeypatch.delenv("SENTRY_RELEASE", raising=False)
    transport = KeepingTransport()
    options = observability.init_options(FAKE_DSN)
    sentry_sdk.init(**options, transport=transport)  # type: ignore[arg-type]
    yield transport
    sentry_sdk.init()  # off again for the other tests


def _hint(exc: BaseException) -> Hint:
    return {"exc_info": (type(exc), exc, None)}


def test_the_sdk_stays_off_without_a_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert observability.configure() is False
    assert not sentry_sdk.get_client().dsn


def test_release_prefers_sentry_release_then_the_image_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTRY_RELEASE", "f" * 40)
    monkeypatch.setenv("PORTFOLIO_IMAGE", f"ghcr.io/sandcorporation/portfolio:{SHA}")
    assert observability.release() == "f" * 40
    monkeypatch.delenv("SENTRY_RELEASE")
    assert observability.release() == SHA
    for image in ("", "portfolio-web:latest", "ghcr.io/sandcorporation/portfolio", "x:0123abc"):
        monkeypatch.setenv("PORTFOLIO_IMAGE", image)
        assert observability.release() is None
    monkeypatch.delenv("PORTFOLIO_IMAGE")
    assert observability.release() is None


@pytest.mark.parametrize(
    "exc",
    [
        Http404("no"),
        PermissionDenied("no"),
        DisallowedHost("evil.example"),
        NotFound("no"),
        Conflict("no"),
        Rejected.at("slug", "taken"),
    ],
)
def test_refusals_we_raise_on_purpose_are_dropped(exc: Exception) -> None:
    assert observability.before_send({"exception": {"values": []}}, _hint(exc)) is None


def test_errors_raised_in_manage_shell_are_dropped() -> None:
    frames = [
        {"module": "manage", "filename": "manage.py"},
        {"abs_path": "/venv/site-packages/django/core/management/commands/shell.py"},
        {"module": "<string>"},
    ]
    event: Event = {
        "exception": {"values": [{"type": "NameError", "stacktrace": {"frames": frames}}]}
    }
    assert observability.before_send(event, _hint(NameError("x"))) is None


def test_other_errors_pass_with_credentials_scrubbed() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
    event: Event = {
        "message": f"call failed with Bearer abcdefgh12345678 and {jwt}",
        "exception": {
            "values": [
                {
                    "type": "RuntimeError",
                    "value": "token=s3cr3tvalue failed",
                    "stacktrace": {"frames": [{"module": "services.pdf", "vars": {"key": "v"}}]},
                }
            ]
        },
        "extra": {"note": "password: hunter22", "id": 7},
        "request": {
            "url": "https://sandcorp.co.kr/preview/blog/AbC.dEf:1x2y3z:signature",
            "cookies": {"sessionid": "abc"},
            "data": {"code": "1234"},
            "headers": {"Cookie": "sessionid=abc", "Authorization": "Bearer x", "User-Agent": "UA"},
        },
    }
    kept = observability.before_send(event, _hint(RuntimeError("token=s3cr3tvalue failed")))
    assert kept is not None
    text = repr(kept)
    for secret in (
        "abcdefgh12345678",
        jwt,
        "s3cr3tvalue",
        "hunter22",
        "sessionid",
        "signature",
        "1234",
    ):
        assert secret not in text
    request = kept["request"]
    assert request["headers"] == {"User-Agent": "UA"}
    assert request["url"] == "https://sandcorp.co.kr/preview/blog/[Filtered]"
    assert "vars" not in kept["exception"]["values"][0]["stacktrace"]["frames"][0]
    assert kept["extra"]["id"] == 7


def test_glitchtip_test_sends_one_event_with_release_and_environment(
    sent: KeepingTransport,
) -> None:
    out = io.StringIO()
    call_command("glitchtip_test", "hello", stdout=out)
    assert "event_id=" in out.getvalue()
    [event] = sent.events
    assert event["release"] == SHA
    assert event["environment"] == "production"
    assert event["exception"]["values"][-1]["type"] == GlitchTipOnboardingTest.__name__


def test_glitchtip_test_without_a_dsn_says_so() -> None:
    out = io.StringIO()
    call_command("glitchtip_test", stdout=out)
    assert "DSN 없음" in out.getvalue()


def test_a_refusal_never_reaches_the_transport(sent: KeepingTransport) -> None:
    try:
        raise Rejected.at("slug", "taken")
    except Rejected:
        sentry_sdk.capture_exception(sys.exc_info()[1])
    sentry_sdk.flush()
    assert sent.events == []


@pytest.mark.django_db
def test_the_shell_hands_the_browser_its_dsn_only_when_set(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PORTFOLIO_IMAGE", f"ghcr.io/sandcorporation/portfolio:{SHA}")
    assert "__PUBLIC__" not in client.get("/").content.decode()
    with override_settings(SENTRY_DSN_FRONTEND=FAKE_DSN):
        html = client.get("/").content.decode()
        assert "window.__PUBLIC__" in html
        assert FAKE_DSN in html and SHA in html
        assert observability.public_config("/print/abc") is None
        assert observability.public_config("/print/draft/abc") is None
        assert observability.public_config("/p/some-proposal") is not None

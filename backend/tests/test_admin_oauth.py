"""Admin login through sandcorp-auth (issue #7), at the HTTP boundary.

The browser is the Django test client; `auth_server` (FakeAuthServer) plays sandcorp-auth's
`/authorize` (approve and send back a code) and `/token` (client secret, one-time code,
redirect_uri, PKCE). The temporary password login (#25) stays beside it for now and keeps
its own tests in test_admin_ratelimit.py.
"""

import urllib.parse
from collections.abc import Iterator
from importlib import reload
from typing import TYPE_CHECKING

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import clear_url_caches
from pytest_django.fixtures import Settings

from adapters.fake_jwks import FakeAuthServer
from oauth.bearer import RESOURCE
from oauth.login import AUTHORIZE_URL, code_challenge

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse as Response

pytestmark = pytest.mark.django_db
CALLBACK = "https://sandcorp.co.kr/admin/oauth/callback/"
START = "/admin/oauth/login/"


def location(response: "Response") -> str:
    assert response.status_code == 302, response.status_code
    return str(response["Location"])


def begin(client: Client, next_url: str = "/admin/") -> str:
    """Press 「sandcorp-auth로 로그인」; return the /authorize URL the browser is sent to."""
    return location(client.get(START, {"next": next_url}))


def sign_in(
    client: Client,
    auth_server: FakeAuthServer,
    next_url: str = "/admin/",
    claims: dict[str, str | int] | None = None,
    signing_key: Ed25519PrivateKey | None = None,
) -> "Response":
    callback = auth_server.authorize(begin(client, next_url), claims, signing_key=signing_key)
    return client.get(callback)


def signed_in(client: Client) -> bool:
    return "_auth_user_id" in client.session


def test_anonymous_admin_goes_to_the_login_page_with_the_sandcorp_auth_button(
    auth_server: FakeAuthServer,
) -> None:
    client = Client()
    login_page = location(client.get("/admin/content/portfolioitem/"))
    assert login_page.startswith("/admin/login/")
    body = client.get(login_page).content.decode()
    assert 'id="oauth-login"' in body
    assert f"{START}?next=/admin/content/portfolioitem/" in body


def test_start_redirects_to_authorize_with_pkce_state_and_client(
    auth_server: FakeAuthServer,
) -> None:
    client = Client()
    base, _, query = begin(client).partition("?")
    params = dict(urllib.parse.parse_qsl(query))
    pending = client.session["admin_oauth"]
    assert base == AUTHORIZE_URL
    assert params == {
        "response_type": "code",
        "client_id": "portfolio-admin",
        "redirect_uri": CALLBACK,
        "state": pending["state"],
        "code_challenge": code_challenge(pending["verifier"]),
        "code_challenge_method": "S256",
        "resource": RESOURCE,
        "scope": "login",
    }
    assert len(pending["state"]) >= 32 and 43 <= len(pending["verifier"]) <= 128
    # every start draws a fresh state and verifier
    begin(client)
    assert client.session["admin_oauth"]["state"] != pending["state"]


def test_owner_signs_in_and_the_admin_opens(auth_server: FakeAuthServer) -> None:
    client = Client()
    response = sign_in(client, auth_server, next_url="/admin/content/portfolioitem/")
    assert location(response) == "/admin/content/portfolioitem/"
    assert signed_in(client)
    assert client.get("/admin/").status_code == 200
    owner = User.objects.get(username="owner")
    assert owner.is_staff and owner.is_superuser and not owner.has_usable_password()
    grant = auth_server.grants[-1]
    assert grant.redirect_uri == CALLBACK and grant.client_secret == "test-client-secret"
    assert "admin_oauth" not in client.session


def test_second_login_reuses_the_owner_user_and_restores_staff(
    auth_server: FakeAuthServer,
) -> None:
    User.objects.create_user("owner", password=None)  # e.g. demoted by hand
    client = Client()
    sign_in(client, auth_server)
    assert signed_in(client)
    owner = User.objects.get(username="owner")
    assert owner.is_staff and owner.is_superuser
    assert User.objects.filter(username="owner").count() == 1


def test_deactivated_owner_user_stays_out(auth_server: FakeAuthServer) -> None:
    User.objects.create_user("owner", is_active=False)
    client = Client()
    assert sign_in(client, auth_server).status_code == 403
    assert not signed_in(client)


@pytest.mark.parametrize(
    "claims",
    [
        pytest.param({"sub": "someone-else"}, id="other-sub"),
        pytest.param({"iss": "https://evil.example"}, id="wrong-iss"),
        pytest.param({"aud": "https://news.sandcorp.co.kr/mcp"}, id="wrong-aud"),
        pytest.param({"scope": "admin"}, id="no-login-scope"),
        pytest.param({"exp": -60}, id="expired"),  # seconds from now, past the 30 s leeway
    ],
)
def test_bad_tokens_make_no_session(
    auth_server: FakeAuthServer, claims: dict[str, str | int]
) -> None:
    if "exp" in claims:
        claims = {"exp": int(auth_server.clock.now().timestamp()) + int(claims["exp"])}
    client = Client()
    response = sign_in(client, auth_server, claims=claims)
    assert response.status_code == 403
    assert not signed_in(client)
    assert not User.objects.exists()


def test_token_signed_by_another_key_makes_no_session(auth_server: FakeAuthServer) -> None:
    client = Client()
    response = sign_in(client, auth_server, signing_key=Ed25519PrivateKey.generate())
    assert response.status_code == 403
    assert not signed_in(client)


def test_state_mismatch_is_refused_before_the_code_is_used(auth_server: FakeAuthServer) -> None:
    client = Client()
    callback = auth_server.authorize(begin(client))
    response = client.get(callback.replace("state=", "state=x"))
    assert response.status_code == 403
    assert not signed_in(client) and auth_server.grants == []


def test_code_verifier_mismatch_is_refused(auth_server: FakeAuthServer) -> None:
    client = Client()
    callback = auth_server.authorize(begin(client))
    session = client.session
    session["admin_oauth"] = {**session["admin_oauth"], "verifier": "x" * 64}
    session.save()
    assert client.get(callback).status_code == 403
    assert not signed_in(client)


def test_callback_without_start_or_replayed_is_refused(auth_server: FakeAuthServer) -> None:
    client = Client()
    callback = auth_server.authorize(begin(client))
    assert location(client.get(callback)) == "/admin/"
    client.logout()
    assert client.get(callback).status_code == 403  # no pending login any more
    assert Client().get(callback).status_code == 403
    assert not signed_in(client)


def test_authorization_error_is_refused(auth_server: FakeAuthServer) -> None:
    client = Client()
    state = dict(urllib.parse.parse_qsl(begin(client).partition("?")[2]))["state"]
    response = client.get("/admin/oauth/callback/", {"error": "access_denied", "state": state})
    assert response.status_code == 403
    assert not signed_in(client) and auth_server.grants == []


def test_next_never_leaves_the_site(auth_server: FakeAuthServer) -> None:
    client = Client()
    assert location(sign_in(client, auth_server, next_url="https://evil.example/")) == "/admin/"


def test_without_client_settings_only_the_oauth_login_is_off(settings: Settings) -> None:
    settings.AUTH_CLIENT_ID = ""
    settings.AUTH_CLIENT_SECRET = ""
    client = Client()
    assert client.get(START).status_code == 503
    assert client.get("/admin/oauth/callback/?code=x&state=y").status_code == 503
    assert client.get("/admin/login/").status_code == 200
    assert client.get("/").status_code == 200


def test_logout_ends_the_session(auth_server: FakeAuthServer) -> None:
    client = Client()
    sign_in(client, auth_server)
    assert signed_in(client)
    assert client.post("/admin/logout/").status_code == 200
    assert not signed_in(client)
    assert location(client.get("/admin/")).startswith("/admin/login/")


@pytest.fixture
def secret_admin_path() -> Iterator[None]:
    import config.urls

    with override_settings(ADMIN_PATH="x7k2-secret/"):
        reload(config.urls)
        clear_url_caches()
        yield
    reload(config.urls)
    clear_url_caches()


def test_oauth_paths_live_under_the_secret_admin_path(
    auth_server: FakeAuthServer, settings: Settings, secret_admin_path: None
) -> None:
    client = Client()
    assert client.get("/admin/").status_code == 404
    assert client.get(START).status_code == 404
    authorize = location(client.get("/x7k2-secret/oauth/login/"))
    params = dict(urllib.parse.parse_qsl(authorize.partition("?")[2]))
    assert params["redirect_uri"] == "https://sandcorp.co.kr/x7k2-secret/oauth/callback/"
    assert location(client.get(auth_server.authorize(authorize))) == "/x7k2-secret/"
    assert signed_in(client)

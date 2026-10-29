"""sandcorp-auth access tokens at the HTTP boundary: /mcp, the ninja admin API, the metadata.

Rules are sandcorp-auth docs/resource-server-token-validation.md (B*, T*, S*, J*).
"""

from typing import TYPE_CHECKING

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.test import Client
from pytest_django.fixtures import Settings

from adapters.fake_jwks import Claim, FakeAuthServer

META = 'resource_metadata="https://sandcorp.co.kr/.well-known/oauth-protected-resource"'
NO_TOKEN = f"Bearer {META}"
INVALID = f'Bearer {META}, error="invalid_token"'
PING = {"jsonrpc": "2.0", "id": 1, "method": "ping"}

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse


def post_mcp(client: Client, headers: dict[str, str]) -> _MonkeyPatchedWSGIResponse:
    return client.post("/mcp", PING, content_type="application/json", headers=headers)


def test_protected_resource_metadata_names_sandcorp_auth(client: Client) -> None:
    for path in (
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/mcp",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"
        assert response.json() == {
            "resource": "https://sandcorp.co.kr/mcp",
            "authorization_servers": ["https://auth.sandcorp.co.kr"],
            "scopes_supported": ["admin", "login"],
            "bearer_methods_supported": ["header"],
        }


def test_valid_token_passes(client: Client, auth_server: FakeAuthServer) -> None:
    response = post_mcp(client, auth_server.bearer())
    assert response.status_code == 200
    assert response.json() == {"jsonrpc": "2.0", "id": 1, "result": {}}


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Basic b3duZXI6cHc="}, {"Authorization": "Bearer"}],
    ids=["no-header", "basic", "empty-bearer"],
)
def test_no_token_is_401_with_resource_metadata(
    client: Client, auth_server: FakeAuthServer, headers: dict[str, str]
) -> None:
    response = post_mcp(client, headers)
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == NO_TOKEN


def test_token_in_query_string_is_ignored(client: Client, auth_server: FakeAuthServer) -> None:
    response = client.post(
        f"/mcp?access_token={auth_server.issue()}", PING, content_type="application/json"
    )
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == NO_TOKEN


def test_bearer_scheme_is_case_insensitive(client: Client, auth_server: FakeAuthServer) -> None:
    headers = {"Authorization": f"bEaReR {auth_server.issue()}"}
    assert post_mcp(client, headers).status_code == 200


def _other_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


BAD_TOKENS: dict[str, dict[str, Claim]] = {
    "wrong-aud": {"aud": "https://news.sandcorp.co.kr/mcp"},
    "aud-trailing-slash": {"aud": "https://sandcorp.co.kr/mcp/"},
    "aud-case": {"aud": "https://Sandcorp.co.kr/mcp"},
    "aud-list": {"aud": ["https://sandcorp.co.kr/mcp"]},
    "wrong-iss": {"iss": "https://evil.example"},
    "iss-trailing-slash": {"iss": "https://auth.sandcorp.co.kr/"},
    "not-owner": {"sub": "someone-else"},
    "owner-case": {"sub": "Owner"},
    "no-jti": {"jti": None},
    "no-client-id": {"client_id": None},
    "exp-not-int": {"exp": "9999999999"},
}


@pytest.mark.parametrize("claims", BAD_TOKENS.values(), ids=BAD_TOKENS.keys())
def test_bad_claims_are_401_invalid_token(
    client: Client, auth_server: FakeAuthServer, claims: dict[str, Claim]
) -> None:
    response = post_mcp(client, auth_server.bearer(auth_server.issue_with(claims)))
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == INVALID
    assert response.json() == {"error": "unauthorized"}  # the reason stays in the log


def test_expiry_allows_30_seconds_of_leeway(client: Client, auth_server: FakeAuthServer) -> None:
    token = auth_server.issue()  # exp = now + 600
    auth_server.clock.advance(600 + 30)
    assert post_mcp(client, auth_server.bearer(token)).status_code == 200
    auth_server.clock.advance(1)
    response = post_mcp(client, auth_server.bearer(token))
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == INVALID


def test_signature_from_another_key_is_401(client: Client, auth_server: FakeAuthServer) -> None:
    headers = auth_server.bearer(auth_server.issue(signing_key=_other_key()))
    response = post_mcp(client, headers)
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == INVALID


def test_tampered_payload_is_401(client: Client, auth_server: FakeAuthServer) -> None:
    header, _, signature = auth_server.issue(scope="login").split(".")
    forged = auth_server.issue(scope="admin").split(".")[1]
    headers = auth_server.bearer(f"{header}.{forged}.{signature}")
    response = post_mcp(client, headers)
    assert response.status_code == 401


@pytest.mark.parametrize("token", ["not-a-jwt", "a.b.c", "x.y"])
def test_malformed_token_is_401(client: Client, auth_server: FakeAuthServer, token: str) -> None:
    response = post_mcp(client, auth_server.bearer(token))
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == INVALID


def test_alg_other_than_eddsa_is_401(client: Client, auth_server: FakeAuthServer) -> None:
    import base64
    import json

    def b64(data: dict[str, object]) -> str:
        raw = json.dumps(data).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    claims_part = auth_server.issue().split(".")[1]
    for alg in ("none", "HS256", "RS256"):
        forged = f"{b64({'alg': alg, 'typ': 'JWT', 'kid': auth_server.kid})}.{claims_part}."
        response = post_mcp(client, auth_server.bearer(forged))
        assert response.status_code == 401, alg
        assert response["WWW-Authenticate"] == INVALID


def test_missing_kid_is_401(client: Client, auth_server: FakeAuthServer) -> None:
    import jwt

    token = jwt.encode({"sub": "owner"}, auth_server.private_key, algorithm="EdDSA")
    response = post_mcp(client, auth_server.bearer(token))
    assert response.status_code == 401


@pytest.mark.parametrize("scope", ["login", "administrator", "", "adminlogin"])
def test_missing_scope_is_403_insufficient_scope(
    client: Client, auth_server: FakeAuthServer, scope: str
) -> None:
    response = post_mcp(client, auth_server.bearer(scope=scope))
    assert response.status_code == 403
    assert response["WWW-Authenticate"] == 'Bearer error="insufficient_scope", scope="admin"'


def test_scope_is_a_space_separated_set(client: Client, auth_server: FakeAuthServer) -> None:
    headers = auth_server.bearer(scope="login  admin")
    assert post_mcp(client, headers).status_code == 200


def test_unknown_kid_refetches_jwks_once_and_follows_rotation(
    client: Client, auth_server: FakeAuthServer
) -> None:
    assert post_mcp(client, auth_server.bearer()).status_code == 200
    assert auth_server.fetches == 1
    auth_server.rotate("key-2")
    assert post_mcp(client, auth_server.bearer()).status_code == 200
    assert auth_server.fetches == 2


def test_unknown_kid_still_unknown_after_refetch_is_401(
    client: Client, auth_server: FakeAuthServer
) -> None:
    assert post_mcp(client, auth_server.bearer()).status_code == 200
    stray = auth_server.issue(headers={"kid": "nobody"})
    response = post_mcp(client, auth_server.bearer(stray))
    assert response.status_code == 401
    assert auth_server.fetches == 2
    # Within 60 s another unknown kid does not hit the JWKS again (rule J2).
    auth_server.clock.advance(59)
    post_mcp(client, auth_server.bearer(stray))
    assert auth_server.fetches == 2
    auth_server.clock.advance(1)
    post_mcp(client, auth_server.bearer(stray))
    assert auth_server.fetches == 3


def test_jwks_is_cached_for_ten_minutes(client: Client, auth_server: FakeAuthServer) -> None:
    for _ in range(3):
        post_mcp(client, auth_server.bearer())
    assert auth_server.fetches == 1
    auth_server.clock.advance(600)
    assert post_mcp(client, auth_server.bearer()).status_code == 200
    assert auth_server.fetches == 2


def test_jwks_failure_keeps_old_keys_and_waits_60_seconds(
    client: Client, auth_server: FakeAuthServer
) -> None:
    assert post_mcp(client, auth_server.bearer()).status_code == 200
    auth_server.failing = True
    auth_server.clock.advance(600)
    assert post_mcp(client, auth_server.bearer()).status_code == 200
    assert auth_server.fetches == 2
    auth_server.clock.advance(30)
    post_mcp(client, auth_server.bearer())
    assert auth_server.fetches == 2


def test_unreachable_jwks_with_empty_cache_is_401(
    client: Client, auth_server: FakeAuthServer
) -> None:
    auth_server.failing = True
    response = post_mcp(client, auth_server.bearer())
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == INVALID


def test_without_owner_setting_mcp_is_503_and_site_is_up(
    client: Client, auth_server: FakeAuthServer, settings: Settings
) -> None:
    settings.AUTH_OWNER_SUB = ""
    response = post_mcp(client, auth_server.bearer())
    assert response.status_code == 503
    assert client.get("/.well-known/oauth-protected-resource").status_code == 200
    assert auth_server.fetches == 0


def test_ninja_admin_api_uses_the_same_check(client: Client, auth_server: FakeAuthServer) -> None:
    response = client.get("/api/admin/whoami", headers=auth_server.bearer(scope="admin login"))
    assert response.status_code == 200
    assert response.json() == {
        "sub": "owner",
        "client_id": "test-client",
        "scopes": ["admin", "login"],
        "expires_at": int(auth_server.clock.now().timestamp()) + 600,
    }

    response = client.get("/api/admin/whoami")
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == NO_TOKEN

    response = client.get("/api/admin/whoami", headers=auth_server.bearer(aud="https://x/mcp"))
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == INVALID

    response = client.get("/api/admin/whoami", headers=auth_server.bearer(scope="login"))
    assert response.status_code == 403
    assert response["WWW-Authenticate"] == 'Bearer error="insufficient_scope", scope="admin"'

"""The one place this site reads auth settings; everything else comes from `sandcorp_authkit`.

Token checks, the bearer guard and the operator login live in the package (sandcorp-auth
`clients/python`). Here settings become function arguments, and these functions are the seams
tests replace (`jwks_cache`, `clock`, `token_transport`).
"""

from functools import cache

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_GET
from sandcorp_authkit.django import (
    AuthNotConfigured,
    BearerAuth,
    BearerConfig,
    metadata_response,
    require_bearer,
)
from sandcorp_authkit.login import LoginConfig, TokenTransport
from sandcorp_authkit.tokens import JwksCache, SystemClock, http_jwks_fetcher, owner_only

SITE_ORIGIN = "https://sandcorp.co.kr"
RESOURCE = "https://sandcorp.co.kr/mcp"
AUTHORIZATION_SERVER = "https://auth.sandcorp.co.kr"
SCOPES_SUPPORTED = ["admin", "login"]
RESOURCE_METADATA_URL = f"{SITE_ORIGIN}/.well-known/oauth-protected-resource"

clock = SystemClock()


@cache  # one cache per process (rule J1); tests replace `jwks_cache`
def jwks_cache() -> JwksCache:
    return JwksCache(http_jwks_fetcher(f"{AUTHORIZATION_SERVER}/.well-known/jwks.json"), clock)


def bearer_config() -> BearerConfig:
    if not settings.AUTH_OWNER_SUB:
        raise AuthNotConfigured("AUTH_OWNER_SUB is empty")  # 503, before the header is read
    return BearerConfig(
        issuer=AUTHORIZATION_SERVER,
        audience=RESOURCE,
        resource_metadata_url=RESOURCE_METADATA_URL,
        jwks=jwks_cache(),
        clock=clock,
        extra_claims_hook=owner_only(settings.AUTH_OWNER_SUB),
    )


def login_config() -> LoginConfig:
    """Registered at sandcorp-auth with the client; the redirect URI is built from settings,
    never the Host header. Incomplete (an empty client id/secret) means the login is off."""
    return LoginConfig(
        client_id=settings.AUTH_CLIENT_ID,
        client_secret=settings.AUTH_CLIENT_SECRET,
        redirect_uri=f"{settings.SITE_URL}/{settings.ADMIN_PATH}oauth/callback/",
        authorize_url=f"{AUTHORIZATION_SERVER}/authorize",
        token_url=f"{AUTHORIZATION_SERVER}/token",
        issuer=AUTHORIZATION_SERVER,
        resource=RESOURCE,
        scope="login",
    )


def token_transport() -> TokenTransport | None:
    """`None` is the package's urllib transport; tests return a `FakeTokenEndpoint`."""
    return None


admin_auth = BearerAuth("admin", config=bearer_config)  # ninja: auth=admin_auth
require_admin = require_bearer("admin", config=bearer_config)  # Django views


@require_GET
def protected_resource_metadata(request: HttpRequest) -> HttpResponse:
    """RFC 9728 metadata: tells MCP clients that sandcorp-auth issues tokens for /mcp."""
    return metadata_response(RESOURCE, AUTHORIZATION_SERVER, SCOPES_SUPPORTED)

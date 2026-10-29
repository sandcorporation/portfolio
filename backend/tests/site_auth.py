"""The fake sandcorp-auth as tests use it: the package's fakes plus this site's resource URL."""

from collections.abc import Mapping
from dataclasses import dataclass

from sandcorp_authkit.testing import (
    FakeJwks,
    FakeTokenEndpoint,
    FixedClock,
    SigningKey,
    bearer_header,
)

from oauth import auth


@dataclass
class SiteAuth:
    """A fake sandcorp-auth for this site: `jwks` (its JWKS endpoint), `endpoint` (`/authorize`
    approval and `/token`) and `clock`, plus tokens for this site's resource URL."""

    jwks: FakeJwks
    endpoint: FakeTokenEndpoint
    clock: FixedClock

    def issue(
        self,
        *,
        key: SigningKey | None = None,
        headers: Mapping[str, object] | None = None,
        **claims: object,
    ) -> str:
        """An `/mcp` access token (sub `owner`, scope `admin`); `claim=None` drops one."""
        return self.issue_with(claims, key=key, headers=headers)

    def issue_with(
        self,
        claims: Mapping[str, object],
        *,
        key: SigningKey | None = None,
        headers: Mapping[str, object] | None = None,
    ) -> str:
        """`issue` with the claims as a mapping (for names like `key` or `headers`)."""
        return self.jwks.issue_access_token(
            self.clock,
            audience=auth.RESOURCE,
            key=key,
            headers=headers,
            **{"sub": "owner", "scope": "admin", **claims},
        )

    def bearer(self, token: str | None = None, **claims: object) -> dict[str, str]:
        """Test-client `headers=` carrying `token` (or a fresh one with these claims)."""
        return bearer_header(token or self.issue_with(claims))

    def approve(
        self,
        authorize_url: str,
        *,
        sub: str = "owner",
        scope: str | None = None,
        access_overrides: Mapping[str, object] | None = None,
    ) -> dict[str, str]:
        """The owner approves an `/authorize` request; returns the callback query."""
        return self.endpoint.approve(
            authorize_url, sub=sub, scope=scope, access_overrides=access_overrides
        )

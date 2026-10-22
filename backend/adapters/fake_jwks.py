"""Fake sandcorp-auth for tests: an Ed25519 signing key, its JWKS and a frozen clock.

`FakeAuthServer.issue()` signs an access token the way sandcorp-auth does (EdDSA, `kid`
header, all eight claims); keyword arguments override or drop claims. `fetch_jwks` serves
the published keys and counts calls, so tests can see when the cache went to the network.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import cast

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jwt.algorithms import OKPAlgorithm

from oauth.bearer import RESOURCE
from oauth.tokens import ISSUER, Jwk, JwkSet

type Claim = str | int | list[str] | None


@dataclass
class FrozenClock:
    moment: datetime = field(default_factory=lambda: datetime(2026, 10, 22, 12, 0, tzinfo=UTC))

    def now(self) -> datetime:
        return self.moment

    def advance(self, seconds: float) -> None:
        self.moment += timedelta(seconds=seconds)


def public_jwk(private_key: Ed25519PrivateKey, kid: str) -> Jwk:
    jwk = cast(Jwk, OKPAlgorithm.to_jwk(private_key.public_key(), as_dict=True))
    jwk["kid"] = kid
    jwk["alg"] = "EdDSA"
    jwk["use"] = "sig"
    return jwk


@dataclass
class FakeAuthServer:
    owner_sub: str = "owner"
    clock: FrozenClock = field(default_factory=FrozenClock)
    kid: str = "key-1"
    private_key: Ed25519PrivateKey = field(default_factory=Ed25519PrivateKey.generate)
    published: list[Jwk] = field(default_factory=list)
    fetches: int = 0
    failing: bool = False

    def __post_init__(self) -> None:
        self.published.append(public_jwk(self.private_key, self.kid))

    def fetch_jwks(self) -> JwkSet:
        self.fetches += 1
        if self.failing:
            raise OSError("JWKS unreachable")
        return {"keys": list(self.published)}

    def rotate(self, kid: str) -> None:
        """Start signing with a new key and publish it next to the old one (rule J5)."""
        self.kid = kid
        self.private_key = Ed25519PrivateKey.generate()
        self.published.append(public_jwk(self.private_key, kid))

    def issue(
        self,
        *,
        signing_key: Ed25519PrivateKey | None = None,
        headers: dict[str, str] | None = None,
        **claims: Claim,
    ) -> str:
        """A signed access token; `claim=None` drops that claim."""
        return self.issue_with(claims, signing_key=signing_key, headers=headers)

    def issue_with(
        self,
        claims: Mapping[str, Claim],
        *,
        signing_key: Ed25519PrivateKey | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        now = int(self.clock.now().timestamp())
        payload: dict[str, Claim] = {
            "iss": ISSUER,
            "sub": self.owner_sub,
            "aud": RESOURCE,
            "client_id": "test-client",
            "scope": "admin",
            "iat": now,
            "exp": now + 600,
            "jti": uuid.uuid4().hex,
        }
        payload.update(claims)
        body = {name: value for name, value in payload.items() if value is not None}
        return jwt.encode(
            body,
            signing_key or self.private_key,
            algorithm="EdDSA",
            headers={"kid": self.kid, **(headers or {})},
        )

    def bearer(self, token: str | None = None, **claims: Claim) -> dict[str, str]:
        """Test-client `headers=` carrying `token` (or a fresh one with these claims)."""
        return {"Authorization": f"Bearer {token or self.issue_with(claims)}"}

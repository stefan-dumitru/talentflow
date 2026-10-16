"""Test doubles for sign-in: a local signing key standing in for Entra External ID's keys."""

import time
from types import SimpleNamespace
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

TEST_ISSUER = "https://tenant-id.ciamlogin.test/tenant-id/v2.0"
TEST_AUDIENCE = "api-client-id-for-tests"


def generate_rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class TokenFactory:
    """Signs tokens that look like the ones External ID issues for our API."""

    def __init__(self, private_key: rsa.RSAPrivateKey, kid: str = "test-key-1") -> None:
        self.private_key = private_key
        self.kid = kid

    @property
    def public_key(self) -> rsa.RSAPublicKey:
        return self.private_key.public_key()

    def make(
        self,
        *,
        oid: str | None = "oid-ann",
        email: str | None = "ann@example.com",
        name: str | None = "Ann Ionescu",
        kid: str | None = None,
        **overrides: Any,
    ) -> str:
        """A valid token. Pass a claim as None to leave it out, or any value to override it."""
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": TEST_ISSUER,
            "aud": TEST_AUDIENCE,
            "oid": oid,
            "sub": f"sub-{oid}",
            "email": email,
            "name": name,
            "iat": now,
            "nbf": now,
            "exp": now + 3600,
        }
        claims.update(overrides)
        claims = {key: value for key, value in claims.items() if value is not None}
        return jwt.encode(
            claims, self.private_key, algorithm="RS256", headers={"kid": kid or self.kid}
        )

    def make_unsigned(self, **overrides: Any) -> str:
        """The classic attack: a token that claims `alg: none` and carries no signature."""
        claims = {"iss": TEST_ISSUER, "aud": TEST_AUDIENCE, "oid": "oid-ann"} | overrides
        return jwt.encode(claims, key=None, algorithm="none", headers={"kid": self.kid})

    def make_hs256(self, **overrides: Any) -> str:
        """A token signed with a shared secret instead of RSA."""
        claims = {"iss": TEST_ISSUER, "aud": TEST_AUDIENCE, "oid": "oid-ann"} | overrides
        return jwt.encode(
            claims, "a-shared-secret-of-sufficient-length-32b", "HS256", headers={"kid": self.kid}
        )


class StubKeyProvider:
    """Looks up signing keys by `kid` from a fixed set, like External ID's published key list."""

    def __init__(self, public_keys: dict[str, Any]) -> None:
        self._public_keys = public_keys

    def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:
        kid = jwt.get_unverified_header(token).get("kid")
        if kid not in self._public_keys:
            raise PyJWKClientError(f"Unable to find a signing key that matches: {kid!r}")
        return SimpleNamespace(key=self._public_keys[kid])


class UnreachableKeyProvider:
    """Stands in for the key list being unreachable (network problem, provider outage)."""

    def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:
        raise PyJWKClientConnectionError("Fail to fetch data from the url")

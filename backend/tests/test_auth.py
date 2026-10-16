import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import (
    AuthenticationError,
    AuthUnavailableError,
    TokenValidator,
    get_token_validator,
)
from tests.auth_support import (
    TEST_AUDIENCE,
    TEST_ISSUER,
    StubKeyProvider,
    TokenFactory,
    UnreachableKeyProvider,
    generate_rsa_key,
)


class TestTokenValidation:
    def test_a_valid_token_yields_the_identity_claims(
        self, token_validator: TokenValidator, token_factory: TokenFactory
    ) -> None:
        token = token_factory.make(oid="oid-1", email="ann@example.com", name="Ann Ionescu")

        claims = token_validator.validate(token)

        assert claims.external_id == "oid-1"
        assert claims.email == "ann@example.com"
        assert claims.display_name == "Ann Ionescu"

    def test_email_and_name_are_optional(
        self, token_validator: TokenValidator, token_factory: TokenFactory
    ) -> None:
        claims = token_validator.validate(token_factory.make(email=None, name=None))

        assert claims.email is None
        assert claims.display_name is None

    def test_an_expired_token_is_rejected(
        self, token_validator: TokenValidator, token_factory: TokenFactory
    ) -> None:
        token = token_factory.make(exp=int(time.time()) - 600)

        with pytest.raises(AuthenticationError):
            token_validator.validate(token)

    def test_a_small_clock_difference_is_tolerated(
        self, token_validator: TokenValidator, token_factory: TokenFactory
    ) -> None:
        # Servers' clocks are never perfectly in step; 10 seconds past expiry is within the
        # 30 second allowance the validator is built with in these tests.
        token = token_factory.make(exp=int(time.time()) - 10)

        assert token_validator.validate(token).external_id == "oid-ann"

    def test_a_token_that_is_not_valid_yet_is_rejected(
        self, token_validator: TokenValidator, token_factory: TokenFactory
    ) -> None:
        token = token_factory.make(nbf=int(time.time()) + 600)

        with pytest.raises(AuthenticationError):
            token_validator.validate(token)

    def test_a_token_for_another_audience_is_rejected(
        self, token_validator: TokenValidator, token_factory: TokenFactory
    ) -> None:
        token = token_factory.make(aud="some-other-api")

        with pytest.raises(AuthenticationError):
            token_validator.validate(token)

    def test_a_token_from_another_issuer_is_rejected(
        self, token_validator: TokenValidator, token_factory: TokenFactory
    ) -> None:
        token = token_factory.make(iss="https://evil.example/tenant/v2.0")

        with pytest.raises(AuthenticationError):
            token_validator.validate(token)

    def test_a_token_signed_with_another_key_is_rejected(
        self, token_validator: TokenValidator, token_factory: TokenFactory
    ) -> None:
        # Same key id as the real one, but signed by someone else's private key.
        forger = TokenFactory(generate_rsa_key(), kid=token_factory.kid)

        with pytest.raises(AuthenticationError):
            token_validator.validate(forger.make())

    def test_a_token_with_an_unknown_key_id_is_rejected(
        self, token_validator: TokenValidator, token_factory: TokenFactory
    ) -> None:
        with pytest.raises(AuthenticationError):
            token_validator.validate(token_factory.make(kid="not-a-published-key"))

    def test_an_unsigned_alg_none_token_is_rejected(
        self, token_validator: TokenValidator, token_factory: TokenFactory
    ) -> None:
        with pytest.raises(AuthenticationError):
            token_validator.validate(token_factory.make_unsigned())

    def test_a_token_signed_with_a_shared_secret_is_rejected(
        self, token_validator: TokenValidator, token_factory: TokenFactory
    ) -> None:
        with pytest.raises(AuthenticationError):
            token_validator.validate(token_factory.make_hs256())

    @pytest.mark.parametrize("missing_claim", ["exp", "iss", "aud"])
    def test_a_token_without_a_required_claim_is_rejected(
        self, token_validator: TokenValidator, token_factory: TokenFactory, missing_claim: str
    ) -> None:
        token = token_factory.make(**{missing_claim: None})

        with pytest.raises(AuthenticationError):
            token_validator.validate(token)

    @pytest.mark.parametrize("bad_oid", [None, ""])
    def test_a_token_without_a_user_id_is_rejected(
        self, token_validator: TokenValidator, token_factory: TokenFactory, bad_oid: str | None
    ) -> None:
        with pytest.raises(AuthenticationError):
            token_validator.validate(token_factory.make(oid=bad_oid))

    @pytest.mark.parametrize("garbage", ["", "not-a-token", "a.b.c", "Bearer abc", "x" * 5000])
    def test_garbage_is_rejected(self, token_validator: TokenValidator, garbage: str) -> None:
        with pytest.raises(AuthenticationError):
            token_validator.validate(garbage)

    def test_unreachable_signing_keys_are_an_outage_not_a_bad_token(
        self, token_factory: TokenFactory
    ) -> None:
        validator = TokenValidator(
            issuer=TEST_ISSUER,
            audience=TEST_AUDIENCE,
            key_provider=UnreachableKeyProvider(),
            clock_skew_seconds=30,
        )

        with pytest.raises(AuthUnavailableError):
            validator.validate(token_factory.make())


class TestAuthorizationHeader:
    """How the API treats the Authorization header, using /api/me as the protected endpoint."""

    def test_no_header_is_unauthorized(self, api_client: TestClient) -> None:
        response = api_client.get("/api/me")

        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"

    def test_another_authentication_scheme_is_unauthorized(self, api_client: TestClient) -> None:
        response = api_client.get("/api/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})

        assert response.status_code == 401

    def test_a_garbage_bearer_token_is_unauthorized(self, api_client: TestClient) -> None:
        response = api_client.get("/api/me", headers={"Authorization": "Bearer not-a-token"})

        assert response.status_code == 401

    def test_the_error_does_not_say_why_the_token_was_refused(
        self, api_client: TestClient, token_factory: TokenFactory
    ) -> None:
        expired = token_factory.make(exp=int(time.time()) - 3600)

        response = api_client.get("/api/me", headers={"Authorization": f"Bearer {expired}"})

        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid or missing token"}

    def test_an_unreachable_key_list_gives_503_not_401(
        self, app: FastAPI, token_factory: TokenFactory
    ) -> None:
        broken = TokenValidator(
            issuer=TEST_ISSUER,
            audience=TEST_AUDIENCE,
            key_provider=UnreachableKeyProvider(),
            clock_skew_seconds=30,
        )
        app.dependency_overrides[get_token_validator] = lambda: broken

        with TestClient(app) as client:
            response = client.get(
                "/api/me", headers={"Authorization": f"Bearer {token_factory.make()}"}
            )

        assert response.status_code == 503

    def test_missing_auth_configuration_refuses_everything(
        self, app: FastAPI, token_factory: TokenFactory
    ) -> None:
        # No override and no AUTH_* settings in the test environment: the API must not fall
        # back to letting people in.
        with TestClient(app) as client:
            response = client.get(
                "/api/me", headers={"Authorization": f"Bearer {token_factory.make()}"}
            )

        assert response.status_code == 503
        assert "not configured" in response.json()["detail"]


def test_the_stub_key_provider_matches_the_validator_contract(
    token_factory: TokenFactory,
) -> None:
    # Guards the test double itself: if it stopped finding the real key, every auth test above
    # would "pass" for the wrong reason (all tokens rejected).
    provider = StubKeyProvider({token_factory.kid: token_factory.public_key})

    assert provider.get_signing_key_from_jwt(token_factory.make()).key is not None

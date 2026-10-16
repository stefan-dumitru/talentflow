"""Sign-in: checking the token Microsoft issued, and working out who is calling.

Flow for every request: the browser sends the access token Entra External ID gave it. We check
it is genuine and meant for this API (TokenValidator), then look the person up in our own
database (services/identity.py) to learn whether they are a candidate, staff, or disabled.
Routes then ask for the Principal, or for specific roles (require_roles).
"""

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any, Protocol

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientConnectionError, PyJWKClientError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import open_session
from app.core.principal import Principal, PrincipalKind
from app.core.tenancy import TenantScope
from app.models import Role
from app.services.identity import IdentityError, resolve_principal

logger = logging.getLogger(__name__)

# External ID signs its tokens with RSA. Naming the only accepted algorithm is what stops
# "alg: none" and shared-secret forgeries.
ALLOWED_ALGORITHMS = ["RS256"]


class AuthenticationError(Exception):
    """The token is not acceptable. The message is for our logs only, never for the caller."""


class AuthUnavailableError(Exception):
    """We could not check the token because Microsoft's signing keys were unreachable."""


@dataclass(frozen=True)
class TokenClaims:
    external_id: str  # the "oid" claim: the person's stable id in External ID
    email: str | None
    display_name: str | None


class SigningKey(Protocol):
    @property
    def key(self) -> Any: ...


class SigningKeyProvider(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> SigningKey: ...


class TokenValidator:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        key_provider: SigningKeyProvider,
        clock_skew_seconds: int,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._key_provider = key_provider
        self._clock_skew_seconds = clock_skew_seconds

    def validate(self, token: str) -> TokenClaims:
        try:
            signing_key = self._key_provider.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=ALLOWED_ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._clock_skew_seconds,
                options={"require": ["exp", "iss", "aud"]},
            )
        except PyJWKClientConnectionError as error:
            raise AuthUnavailableError("Could not download the signing keys") from error
        except (InvalidTokenError, PyJWKClientError) as error:
            raise AuthenticationError(type(error).__name__) from error

        external_id = payload.get("oid")
        if not isinstance(external_id, str) or not external_id:
            raise AuthenticationError("MissingUserId")
        email = payload.get("email")
        name = payload.get("name")
        return TokenClaims(
            external_id=external_id,
            email=email if isinstance(email, str) and email else None,
            display_name=name if isinstance(name, str) and name else None,
        )


@lru_cache
def get_token_validator() -> TokenValidator:
    """FastAPI dependency: the validator built from settings. Tests replace it."""
    settings = get_settings()
    if not (settings.auth_issuer and settings.auth_audience and settings.auth_jwks_url):
        # Fail closed: without settings we cannot tell real tokens from fake ones.
        logger.error("Authentication settings (AUTH_ISSUER, AUTH_AUDIENCE, AUTH_JWKS_URL) missing")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )
    return TokenValidator(
        issuer=settings.auth_issuer,
        audience=settings.auth_audience,
        key_provider=PyJWKClient(
            settings.auth_jwks_url,
            cache_jwk_set=True,
            lifespan=settings.auth_jwks_cache_seconds,
            timeout=settings.auth_jwks_timeout_seconds,
        ),
        clock_skew_seconds=settings.auth_clock_skew_seconds,
    )


# auto_error=False so a missing header reaches us and gets the same 401 as a bad token.
bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    # One generic message whatever went wrong, so callers learn nothing about why.
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    validator: Annotated[TokenValidator, Depends(get_token_validator)],
) -> Principal:
    """FastAPI dependency: who is making this request. Every endpoint depends on this."""
    if credentials is None:
        raise _unauthorized()

    try:
        claims = validator.validate(credentials.credentials)
    except AuthenticationError as error:
        logger.warning("Token rejected: %s", error)
        raise _unauthorized() from error
    except AuthUnavailableError as error:
        logger.error("Cannot check tokens right now: %s", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sign-in is temporarily unavailable",
        ) from error

    # Unrestricted: staff records have to be looked up before we know the person's company.
    with open_session(TenantScope.unrestricted()) as session:
        try:
            principal = resolve_principal(
                session,
                external_id=claims.external_id,
                email=claims.email,
                display_name=claims.display_name,
            )
        except IdentityError as error:
            logger.warning("Sign-in refused: %s", error)
            raise _unauthorized() from error
        session.commit()  # saves a first-time sign-in (new candidate, or staff linked)
    return principal


def require_roles(*allowed: Role) -> Callable[[Principal], Principal]:
    """Dependency factory: only active staff holding at least one of these roles get through."""

    def check(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if principal.kind is PrincipalKind.STAFF and principal.roles.intersection(allowed):
            return principal
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this."
        )

    return check


def get_scoped_db(principal: Annotated[Principal, Depends(get_principal)]) -> Iterator[Session]:
    """FastAPI dependency: a database session limited to what this person may see."""
    with open_session(principal.tenant_scope()) as session:
        yield session

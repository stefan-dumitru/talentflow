from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, read from environment variables (and `.env` locally).

    In production these come from Container Apps settings backed by Key Vault, never from code.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    environment: Literal["local", "test", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Sign-in (Microsoft Entra External ID). All three come from the tenant's OpenID metadata
    # and the API app registration. If any is missing, every authenticated endpoint answers 503
    # rather than letting anyone in.
    auth_issuer: str | None = None
    auth_audience: str | None = None
    auth_jwks_url: str | None = None
    # Servers' clocks drift a little; accept tokens this many seconds either side of their
    # not-before / expiry times.
    auth_clock_skew_seconds: int = 30
    # How long the downloaded signing keys are reused. An unknown key id triggers one re-download
    # straight away, so a key rotation does not have to wait for this to run out.
    auth_jwks_cache_seconds: int = 3600
    auth_jwks_timeout_seconds: int = 5


@lru_cache
def get_settings() -> Settings:
    # Cached so the environment is read once per process, not on every request.
    return Settings()

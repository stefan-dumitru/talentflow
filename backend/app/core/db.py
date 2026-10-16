from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core import tenancy  # noqa: F401  (importing it switches company scoping on)
from app.core.config import get_settings

# Fail fast instead of hanging a request when Postgres is unreachable.
CONNECT_TIMEOUT_SECONDS = 3


def build_engine(database_url: str) -> Engine:
    return create_engine(
        database_url,
        # Checks a pooled connection is still alive before using it (e.g. after a DB restart).
        pool_pre_ping=True,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )


@lru_cache
def get_engine() -> Engine:
    """FastAPI dependency: the process-wide engine. Tests override it."""
    return build_engine(get_settings().database_url)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed afterwards."""
    session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with session_factory() as session:
        yield session

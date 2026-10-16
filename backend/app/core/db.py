from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

# Importing app.core.tenancy is what switches company scoping on for every session.
from app.core.config import get_settings
from app.core.tenancy import TenantScope, set_scope

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


@contextmanager
def open_session(scope: TenantScope) -> Iterator[Session]:
    """A database session that has declared which company data it may touch.

    Every session must be opened through here (or get its scope from set_scope), because a
    session with no declared scope cannot read company data at all. Always closed afterwards.
    """
    session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with session_factory() as session:
        set_scope(session, scope)
        yield session

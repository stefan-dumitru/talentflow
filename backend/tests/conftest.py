import os
from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from alembic import command
from tests.auth_support import (
    TEST_AUDIENCE,
    TEST_ISSUER,
    StubKeyProvider,
    TokenFactory,
    generate_rsa_key,
)

# Tests run against the separate `talentflow_test` database from docker-compose.yml, never the
# dev database and never SQLite. CI sets TEST_DATABASE_URL; the default matches the local-only
# container. This must happen before the app is imported, because Settings reads the environment.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://talentflow:talentflow@127.0.0.1:5433/talentflow_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["ENVIRONMENT"] = "test"

from app.core.auth import TokenValidator, get_token_validator  # noqa: E402
from app.core.db import get_engine  # noqa: E402
from app.core.tenancy import TenantScope, set_scope  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Company, Plan  # noqa: E402
from tests.support import alembic_config  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def require_test_database() -> None:
    """Stop the whole run with a clear message instead of dozens of connection errors."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        pytest.exit(
            f"Test database unreachable at {TEST_DATABASE_URL.split('@')[-1]}. "
            "Start it with `docker compose up -d` from the repo root.",
            returncode=1,
        )


@pytest.fixture(scope="session", autouse=True)
def migrated_database(require_test_database: None) -> None:
    """Bring the test database to the latest schema once per run (also seeds the plans)."""
    command.upgrade(alembic_config(TEST_DATABASE_URL), "head")


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session() -> Iterator[Session]:
    """A database session whose changes are thrown away when the test ends.

    The session sits inside an outer transaction that is rolled back at the end. Code under test
    may commit; "create_savepoint" turns those commits into savepoints inside the outer
    transaction, so nothing ever reaches the database for real and tests can't affect each other.
    """
    connection = get_engine().connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    # Tests arrange their data like a system actor would. Tests of the scoping rules themselves
    # use the session_with_scope fixture below instead.
    set_scope(session, TenantScope.unrestricted())
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture
def session_with_scope(db_session: Session) -> Iterator[Callable[[TenantScope | None], Session]]:
    """Makes extra sessions that share db_session's transaction, so they see its test data.

    Pass the scope to declare, or None to leave it undeclared.
    """
    created: list[Session] = []

    def _make(scope: TenantScope | None) -> Session:
        session = Session(
            bind=db_session.get_bind(),
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        if scope is not None:
            set_scope(session, scope)
        created.append(session)
        return session

    yield _make
    for session in created:
        session.close()


@pytest.fixture(scope="session")
def token_factory() -> TokenFactory:
    """Signs test tokens. One key for the whole run, since generating RSA keys is slow."""
    return TokenFactory(generate_rsa_key())


@pytest.fixture
def token_validator(token_factory: TokenFactory) -> TokenValidator:
    return TokenValidator(
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
        key_provider=StubKeyProvider({token_factory.kid: token_factory.public_key}),
        clock_skew_seconds=30,
    )


def _empty_company_and_user_tables() -> None:
    # `plans` is left alone: the migration seeds it and tests rely on it.
    with get_engine().begin() as connection:
        connection.execute(
            text("TRUNCATE staff_roles, staff_members, companies, users RESTART IDENTITY CASCADE")
        )


@pytest.fixture
def clean_database() -> Iterator[None]:
    """For tests whose code really commits (HTTP requests, threads): wipe their rows after.

    The db_session fixture rolls everything back instead and doesn't need this.
    """
    _empty_company_and_user_tables()
    yield
    _empty_company_and_user_tables()


@pytest.fixture
def committed_session(clean_database: None) -> Iterator[Session]:
    """A system-level session whose commits are real, to arrange data for HTTP tests."""
    with Session(get_engine(), expire_on_commit=False) as session:
        set_scope(session, TenantScope.unrestricted())
        yield session


@pytest.fixture
def api_client(
    app: FastAPI, token_validator: TokenValidator, clean_database: None
) -> Iterator[TestClient]:
    """A client for the real app, trusting tokens signed by the test key."""
    app.dependency_overrides[get_token_validator] = lambda: token_validator
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def free_plan(db_session: Session) -> Plan:
    return db_session.scalars(select(Plan).where(Plan.name == "Free")).one()


@pytest.fixture
def make_company(db_session: Session, free_plan: Plan) -> Callable[..., Company]:
    def _make_company(slug: str = "acme") -> Company:
        company = Company(
            name=slug.title(),
            slug=slug,
            plan_id=free_plan.id,
            currency="EUR",
            time_zone="Europe/Bucharest",
        )
        db_session.add(company)
        db_session.flush()
        return company

    return _make_company

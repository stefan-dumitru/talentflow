import os
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

# Tests run against the separate `talentflow_test` database from docker-compose.yml, never the
# dev database and never SQLite. CI sets TEST_DATABASE_URL; the default matches the local-only
# container. This must happen before the app is imported, because Settings reads the environment.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://talentflow:talentflow@127.0.0.1:5433/talentflow_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["ENVIRONMENT"] = "test"

from app.core.db import get_engine  # noqa: E402
from app.main import create_app  # noqa: E402


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


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client

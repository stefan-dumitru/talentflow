import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from alembic import command
from tests.support import alembic_config

PHASE_1_TABLES = {"plans", "users", "companies", "staff_members", "staff_roles"}


@pytest.fixture
def scratch_database_url() -> Iterator[str]:
    """A throwaway database, so up/down migrations never disturb the shared test database."""
    # conftest.py points DATABASE_URL at the test database before anything else runs.
    base_url = make_url(os.environ["DATABASE_URL"])
    name = f"talentflow_migration_{uuid4().hex[:8]}"
    # CREATE/DROP DATABASE can't run inside a transaction, hence AUTOCOMMIT.
    admin_engine = create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield base_url.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin_engine.dispose()


def _table_names(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_migrations_upgrade_to_head_and_downgrade_to_nothing(scratch_database_url: str) -> None:
    config = alembic_config(scratch_database_url)

    command.upgrade(config, "head")
    assert _table_names(scratch_database_url) >= PHASE_1_TABLES

    command.downgrade(config, "base")
    assert not PHASE_1_TABLES & _table_names(scratch_database_url)

    # And back up again, proving the downgrade left nothing behind that blocks a re-upgrade.
    command.upgrade(config, "head")
    assert _table_names(scratch_database_url) >= PHASE_1_TABLES

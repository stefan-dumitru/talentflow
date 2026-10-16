from pathlib import Path

from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parent.parent


def alembic_config(database_url: str) -> Config:
    """Alembic settings pointed at a specific database (env.py honours sqlalchemy.url)."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config

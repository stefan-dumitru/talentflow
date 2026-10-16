from pathlib import Path

from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Plan

BACKEND_DIR = Path(__file__).resolve().parent.parent


def alembic_config(database_url: str) -> Config:
    """Alembic settings pointed at a specific database (env.py honours sqlalchemy.url)."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def create_company(session: Session, slug: str) -> Company:
    """Create and commit a company on the Free plan, for tests that need real commits."""
    plan = session.scalars(select(Plan).where(Plan.name == "Free")).one()
    company = Company(
        name=slug.title(),
        slug=slug,
        plan_id=plan.id,
        currency="EUR",
        time_zone="Europe/Bucharest",
    )
    session.add(company)
    session.commit()
    return company

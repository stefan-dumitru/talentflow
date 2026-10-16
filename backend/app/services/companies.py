from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Company, Plan


class CompanyError(Exception):
    """A company couldn't be created. The message is safe to show to whoever asked."""


def get_company_by_slug(session: Session, slug: str) -> Company | None:
    return session.scalar(select(Company).where(Company.slug == slug))


def create_company(
    session: Session, *, name: str, slug: str, plan_name: str, currency: str, time_zone: str
) -> Company:
    """Create a company on a named plan. Does not commit: the caller owns the transaction."""
    plan = session.scalar(select(Plan).where(Plan.name == plan_name))
    if plan is None:
        raise CompanyError(f"Plan '{plan_name}' not found. Have the database migrations been run?")

    company = Company(name=name, slug=slug, plan_id=plan.id, currency=currency, time_zone=time_zone)
    try:
        # A savepoint, so a rejected insert undoes only itself and the session stays usable.
        with session.begin_nested():
            session.add(company)
    except IntegrityError as error:
        raise CompanyError(
            f"Could not create company '{slug}': the slug must be lowercase letters, digits and "
            "single hyphens, and not already in use."
        ) from error
    return company

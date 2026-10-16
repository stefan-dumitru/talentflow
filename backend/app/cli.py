"""Command-line tool for setting up a database by hand. Run from backend/:

    uv run python -m app.cli seed-dev --acme-admin-email you+acme@example.com \\
                                      --globex-admin-email you+globex@example.com
    uv run python -m app.cli add-staff --company acme --email bob@example.com \\
                                       --name "Bob" --roles recruiter,interviewer
    uv run python -m app.cli make-platform-admin --email you@example.com --name "You"

This is the only way to create a platform admin. Every command is safe to run twice, and each
runs as one transaction: if anything is refused, nothing is saved.
"""

import argparse
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.db import open_session
from app.core.tenancy import TenantScope
from app.models import Role
from app.services.companies import CompanyError, create_company, get_company_by_slug
from app.services.platform import create_platform_admin
from app.services.staff import (
    StaffError,
    add_staff_member,
    find_staff_member_by_email,
    has_role,
)

# Deliberately simple: the real check is that the person can sign in with this address. This
# just catches typos like a missing "@" before they are saved.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CliError(Exception):
    """The command line was used wrongly. The message says how."""


@dataclass(frozen=True)
class DemoCompany:
    name: str
    slug: str
    admin_name: str


DEMO_COMPANIES = (
    DemoCompany(name="Acme Corp", slug="acme", admin_name="Acme Admin"),
    DemoCompany(name="Globex", slug="globex", admin_name="Globex Admin"),
)
# Pro, not Free: Free allows only 3 staff seats, too few to try out a hiring team.
DEMO_PLAN = "Pro"
DEMO_CURRENCY = "EUR"
DEMO_TIME_ZONE = "Europe/Bucharest"


def _require_email(value: str) -> None:
    if not EMAIL_PATTERN.match(value):
        raise CliError(f"'{value}' is not a valid email address.")


def parse_roles(text: str) -> set[Role]:
    """Turn "recruiter, interviewer" into roles, listing the valid names if one is wrong."""
    valid_names = ", ".join(role.value for role in Role)
    names = [name.strip() for name in text.split(",") if name.strip()]
    if not names:
        raise CliError(f"Give at least one role. Valid roles: {valid_names}.")

    roles = set()
    for name in names:
        try:
            roles.add(Role(name))
        except ValueError:
            raise CliError(f"Unknown role '{name}'. Valid roles: {valid_names}.") from None
    return roles


def seed_dev(session: Session, acme_admin_email: str, globex_admin_email: str) -> list[str]:
    """Create the two demo companies, each with one company admin. Safe to run twice."""
    report = []
    admin_emails = (acme_admin_email, globex_admin_email)
    for demo, admin_email in zip(DEMO_COMPANIES, admin_emails, strict=True):
        _require_email(admin_email)

        company = get_company_by_slug(session, demo.slug)
        if company is None:
            company = create_company(
                session,
                name=demo.name,
                slug=demo.slug,
                plan_name=DEMO_PLAN,
                currency=DEMO_CURRENCY,
                time_zone=DEMO_TIME_ZONE,
            )
            report.append(f"created company {demo.name} ({demo.slug})")
        else:
            report.append(f"company {demo.slug} already exists, left unchanged")

        existing = find_staff_member_by_email(session, admin_email)
        if (
            existing is not None
            and existing.company_id == company.id
            and has_role(session, existing, Role.COMPANY_ADMIN)
        ):
            report.append(f"admin {admin_email} already exists for {demo.slug}, left unchanged")
        else:
            # Anything else (email used by a candidate, another company, a non-admin) is refused
            # by add_staff_member rather than quietly changed.
            add_staff_member(session, company, admin_email, demo.admin_name, [Role.COMPANY_ADMIN])
            report.append(f"created admin {admin_email} for {demo.slug}")
    return report


def add_staff(
    session: Session, company_slug: str, email: str, name: str, roles_text: str
) -> list[str]:
    _require_email(email)
    roles = parse_roles(roles_text)
    company = get_company_by_slug(session, company_slug)
    if company is None:
        raise CliError(f"There is no company with the slug '{company_slug}'.")

    add_staff_member(session, company, email, name, roles)
    role_names = ", ".join(sorted(role.value for role in roles))
    return [f"added {email} to {company_slug} as {role_names}"]


def make_platform_admin(session: Session, email: str, name: str) -> list[str]:
    _require_email(email)
    if create_platform_admin(session, email, name):
        return [f"created platform admin {email}"]
    return [f"{email} is already a platform admin, left unchanged"]


Handler = Callable[[Session, argparse.Namespace], list[str]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    seed = commands.add_parser("seed-dev", help="create the two demo companies and their admins")
    seed.add_argument("--acme-admin-email", required=True)
    seed.add_argument("--globex-admin-email", required=True)
    seed.set_defaults(
        run=lambda session, args: seed_dev(session, args.acme_admin_email, args.globex_admin_email)
    )

    staff = commands.add_parser("add-staff", help="add a staff member to a company")
    staff.add_argument("--company", required=True, help="the company's slug, e.g. acme")
    staff.add_argument("--email", required=True)
    staff.add_argument("--name", required=True)
    staff.add_argument("--roles", required=True, help="comma separated, e.g. recruiter,interviewer")
    staff.set_defaults(
        run=lambda session, args: add_staff(
            session, args.company, args.email, args.name, args.roles
        )
    )

    admin = commands.add_parser("make-platform-admin", help="create a platform administrator")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    admin.set_defaults(
        run=lambda session, args: make_platform_admin(session, args.email, args.name)
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run: Handler = args.run
    try:
        # Unrestricted: setting up companies has to span every company by nature.
        with open_session(TenantScope.unrestricted()) as session:
            report = run(session, args)
            session.commit()
    except (CliError, StaffError, CompanyError) as error:
        # Leaving the `with` block without committing rolls everything back.
        print(f"Error: {error}", file=sys.stderr)
        return 1

    for line in report:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

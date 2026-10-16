from collections.abc import Collection
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Company, Role, StaffMember, StaffRole, User


class StaffError(Exception):
    """A staff rule was broken. The message is safe to show to the person who made the request."""


class EmailAlreadyInUseError(StaffError):
    pass


class LastCompanyAdminError(StaffError):
    pass


def add_staff_member(
    session: Session,
    company: Company,
    email: str,
    display_name: str,
    roles: Collection[Role],
) -> StaffMember:
    """Pre-create a staff user. They are linked to their External ID login on first sign-in.

    Does not commit: the caller (an API route or the CLI) owns the transaction.
    """
    email = email.strip()
    if not roles:
        raise StaffError("A staff member needs at least one role.")

    existing_user = session.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        raise EmailAlreadyInUseError(_describe_email_conflict(session, existing_user))

    user = User(email=email, display_name=display_name.strip())
    session.add(user)
    session.flush()  # assigns user.id, needed by the staff row below

    member = StaffMember(company_id=company.id, user_id=user.id)
    session.add(member)
    session.flush()

    for role in sorted(set(roles)):
        session.add(StaffRole(staff_member_id=member.id, company_id=company.id, role=role))
    session.flush()
    return member


def deactivate_staff_member(session: Session, member: StaffMember) -> None:
    """Deactivate a staff member, keeping at least one active company admin in the company.

    Reassigning the member's open work first (jobs, approvals, interviews) comes with Phase 5;
    for now this enforces only the "never lock a company out of its own admin" rule.
    """
    if not member.is_active:
        return

    if _is_company_admin(session, member) and _other_active_admins(session, member) == 0:
        raise LastCompanyAdminError(
            "This is the company's last active admin. Make someone else an admin first."
        )

    member.is_active = False
    member.deactivated_at = datetime.now(UTC)
    session.flush()


def _describe_email_conflict(session: Session, existing_user: User) -> str:
    # A user is staff, a platform admin, or a candidate: whichever it is, the email is taken.
    if existing_user.is_platform_admin:
        return "This email belongs to a platform administrator."
    is_staff = session.scalar(select(StaffMember.id).where(StaffMember.user_id == existing_user.id))
    if is_staff is not None:
        return "This email already belongs to a staff member."
    return "This email is used by a candidate account."


def _is_company_admin(session: Session, member: StaffMember) -> bool:
    return (
        session.scalar(
            select(StaffRole.staff_member_id).where(
                StaffRole.staff_member_id == member.id, StaffRole.role == Role.COMPANY_ADMIN
            )
        )
        is not None
    )


def _other_active_admins(session: Session, member: StaffMember) -> int:
    count = session.scalar(
        select(func.count())
        .select_from(StaffRole)
        .join(StaffMember, StaffMember.id == StaffRole.staff_member_id)
        .where(
            StaffMember.company_id == member.company_id,
            StaffMember.is_active.is_(True),
            StaffMember.id != member.id,
            StaffRole.role == Role.COMPANY_ADMIN,
        )
    )
    return count or 0

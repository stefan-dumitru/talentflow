"""Turns a validated sign-in into a Principal: who this is, and what they may do.

The token only proves *who* someone is to Microsoft. What they are in TalentFlow (candidate,
staff and which company, platform admin, disabled) is decided here from our own database.
"""

import logging

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.principal import Principal, PrincipalKind
from app.models import StaffMember, User

logger = logging.getLogger(__name__)


class IdentityError(Exception):
    """This sign-in can't be matched to a TalentFlow account. Never shown to the user in detail."""


def resolve_principal(
    session: Session, *, external_id: str, email: str | None, display_name: str | None
) -> Principal:
    """Find, link, or create the user for this sign-in, then work out what they are.

    The session must be unrestricted: it looks up staff records before the person's company is
    known. Does not commit; the caller does.
    """
    user = _find_or_create_user(session, external_id, email, display_name)
    return _build_principal(session, user)


def _find_or_create_user(
    session: Session, external_id: str, email: str | None, display_name: str | None
) -> User:
    user = _get_by_external_id(session, external_id)
    if user is not None:
        return user

    # First time we see this login. Matching or creating an account needs an email.
    if not email:
        raise IdentityError("The token has no email claim, so a new account can't be matched.")

    # 1. Someone an admin created in advance (staff, platform admin): link them by email.
    #    Only accounts with no login attached yet are eligible, so nobody can take over an
    #    account that already belongs to a different login.
    # 2. Otherwise this is a new candidate.
    linked = _link_pre_created_user(session, email, external_id)
    created = not linked and _create_candidate(session, external_id, email, display_name)
    if not (linked or created):
        logger.info(
            "Sign-in neither linked nor created an account; checking for a simultaneous one"
        )

    # Read the account back. This finds the one we just linked or created, and also one created
    # by a simultaneous request for the same login that beat us to it. If there is none, the
    # email already belongs to a different login.
    user = _get_by_external_id(session, external_id)
    if user is None:
        raise IdentityError("This email address belongs to a different sign-in.")
    return user


def _get_by_external_id(session: Session, external_id: str) -> User | None:
    # populate_existing: if this User is already in the session (loaded before we linked it),
    # refresh it instead of returning the stale copy that still has no login attached.
    return session.scalar(
        select(User)
        .where(User.external_id == external_id)
        .execution_options(populate_existing=True)
    )


def _link_pre_created_user(session: Session, email: str, external_id: str) -> bool:
    # One conditional UPDATE: it succeeds only if the account still has no login attached, so
    # two simultaneous sign-ins can't both claim it. RETURNING tells us whether we won.
    linked_id = session.scalar(
        update(User)
        .where(User.email == email, User.external_id.is_(None))
        .values(external_id=external_id)
        .returning(User.id)
        .execution_options(synchronize_session=False)
    )
    return linked_id is not None


def _create_candidate(
    session: Session, external_id: str, email: str, display_name: str | None
) -> bool:
    try:
        # A savepoint, so a failed insert undoes only itself and the session stays usable.
        with session.begin_nested():
            session.add(
                User(external_id=external_id, email=email, display_name=display_name or email)
            )
    except IntegrityError:
        return False
    return True


def _build_principal(session: Session, user: User) -> Principal:
    def principal_of_kind(kind: PrincipalKind) -> Principal:
        return Principal(
            user_id=user.id, email=user.email, display_name=user.display_name, kind=kind
        )

    if user.is_platform_admin:
        return principal_of_kind(PrincipalKind.PLATFORM_ADMIN)

    member = session.scalar(
        select(StaffMember)
        .where(StaffMember.user_id == user.id)
        .options(selectinload(StaffMember.roles))
    )
    if member is None:
        return principal_of_kind(PrincipalKind.CANDIDATE)
    if not member.is_active:
        # Deliberately no company and no roles: a disabled account gets access to nothing.
        return principal_of_kind(PrincipalKind.ACCOUNT_DISABLED)

    return Principal(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        kind=PrincipalKind.STAFF,
        company_id=member.company_id,
        roles=frozenset(staff_role.role for staff_role in member.roles),
    )

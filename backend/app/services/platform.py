from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.services.staff import EmailAlreadyInUseError, describe_email_conflict


def create_platform_admin(session: Session, email: str, display_name: str) -> bool:
    """Make a platform administrator. Returns False if the email already is one.

    This is the only way anyone becomes a platform admin: there is deliberately no API for it.
    The account is linked to their login on first sign-in, like pre-created staff.
    Does not commit: the caller owns the transaction.
    """
    email = email.strip()
    existing_user = session.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        if existing_user.is_platform_admin:
            return False
        raise EmailAlreadyInUseError(describe_email_conflict(session, existing_user))

    session.add(User(email=email, display_name=display_name.strip(), is_platform_admin=True))
    session.flush()
    return True

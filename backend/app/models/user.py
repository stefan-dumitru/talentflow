from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKey

if TYPE_CHECKING:
    from app.models.staff import StaffMember


class User(UuidPrimaryKey, TimestampMixin, Base):
    """One person who can sign in. Links the External ID identity to TalentFlow.

    A user is staff (has a StaffMember row), a platform admin, or neither, which makes them a
    candidate. Never more than one of those; the services enforce that.
    """

    __tablename__ = "users"

    # The External ID "oid" claim. Empty until the person first signs in, for staff that an
    # admin created in advance. Postgres allows many NULLs in a unique column.
    external_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    # citext = case-insensitive text, so "Ann@x.com" and "ann@x.com" are the same email.
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    # Set only by the CLI (app/cli.py), never through the API.
    is_platform_admin: Mapped[bool] = mapped_column(default=False, server_default="false")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when the account is anonymized after a GDPR deletion request (Phase 13).
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    staff_member: Mapped["StaffMember | None"] = relationship(back_populates="user", lazy="raise")

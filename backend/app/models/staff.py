import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.company import Company
from app.models.mixins import CompanyOwned, TimestampMixin, UuidPrimaryKey
from app.models.user import User


class Role(enum.StrEnum):
    COMPANY_ADMIN = "company_admin"
    RECRUITER = "recruiter"
    HIRING_MANAGER = "hiring_manager"
    INTERVIEWER = "interviewer"


class StaffMember(UuidPrimaryKey, TimestampMixin, CompanyOwned, Base):
    """A user's membership of exactly one company as staff."""

    __tablename__ = "staff_members"
    __table_args__ = (
        # Lets staff_roles point at (id, company_id) together, so a role row can never name a
        # different company than the staff member it belongs to.
        UniqueConstraint("id", "company_id", name="uq_staff_members_id_company_id"),
        CheckConstraint("is_active OR deactivated_at IS NOT NULL", name="deactivated_has_time"),
    )

    # unique=True: one staff record per user, so staff belong to one company only.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), unique=True
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(default=1, server_default="1")

    __mapper_args__ = {"version_id_col": version}

    user: Mapped[User] = relationship(back_populates="staff_member", lazy="raise")
    company: Mapped[Company] = relationship(lazy="raise")
    roles: Mapped[list["StaffRole"]] = relationship(back_populates="staff_member", lazy="raise")


class StaffRole(CompanyOwned, Base):
    """One role held by a staff member. A member can hold several."""

    __tablename__ = "staff_roles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["staff_member_id", "company_id"],
            ["staff_members.id", "staff_members.company_id"],
            ondelete="CASCADE",
            name="fk_staff_roles_staff_member_company",
        ),
    )

    # The primary key is the pair, which also makes "the same role twice" impossible.
    staff_member_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    role: Mapped[Role] = mapped_column(
        Enum(
            Role,
            name="staff_role",
            native_enum=False,
            length=20,
            create_constraint=True,
            values_callable=lambda members: [member.value for member in members],
        ),
        primary_key=True,
    )

    staff_member: Mapped[StaffMember] = relationship(back_populates="roles", lazy="raise")

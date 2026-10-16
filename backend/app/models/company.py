import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKey
from app.models.plan import Plan


class CompanyStatus(enum.StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class Company(UuidPrimaryKey, TimestampMixin, Base):
    """A tenant. Everything company-owned hangs off it."""

    __tablename__ = "companies"
    __table_args__ = (
        # Slugs go into public URLs (/careers/<slug>), so keep them lowercase and URL-safe.
        CheckConstraint(r"slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_format"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
        CheckConstraint(
            "retention_months IS NULL OR retention_months > 0", name="retention_positive"
        ),
    )

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(63), unique=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id", ondelete="RESTRICT"))
    status: Mapped[CompanyStatus] = mapped_column(
        Enum(
            CompanyStatus,
            name="company_status",
            native_enum=False,
            length=20,
            create_constraint=True,
            # Store the lowercase values ("active"), not the Python member names ("ACTIVE").
            values_callable=lambda members: [member.value for member in members],
        ),
        default=CompanyStatus.ACTIVE,
        server_default=CompanyStatus.ACTIVE.value,
    )
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    currency: Mapped[str] = mapped_column(String(3))  # ISO 4217, e.g. "EUR"
    time_zone: Mapped[str] = mapped_column(String(64))  # IANA name, e.g. "Europe/Bucharest"
    retention_months: Mapped[int | None]
    brand_color: Mapped[str | None] = mapped_column(String(7))
    logo_blob_name: Mapped[str | None] = mapped_column(String(300))
    careers_intro: Mapped[str | None] = mapped_column(Text)
    # Optimistic locking: SQLAlchemy adds "AND version = <loaded>" to every UPDATE and raises
    # StaleDataError when someone else saved first (the API turns that into a 409).
    version: Mapped[int] = mapped_column(default=1, server_default="1")

    __mapper_args__ = {"version_id_col": version}

    plan: Mapped[Plan] = relationship(lazy="raise")

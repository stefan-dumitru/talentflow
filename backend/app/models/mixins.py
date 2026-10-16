import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func, text
from sqlalchemy.orm import Mapped, mapped_column


class UuidPrimaryKey:
    """UUID primary key. Generated in Python so an object has its id before it's flushed, and in
    Postgres too so rows inserted by raw SQL (e.g. migration seed data) get one."""

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """created_at / updated_at as timestamptz. Postgres stores these in UTC internally, which is
    what CLAUDE.md asks for; conversion to a viewer's time zone happens only for display."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CompanyOwned:
    """Marks a table whose rows belong to exactly one company.

    The central company scoping in app/core/tenancy.py finds these models by this class and
    filters every query on them to the caller's company.
    """

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )

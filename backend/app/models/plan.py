from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin, UuidPrimaryKey


class Plan(UuidPrimaryKey, TimestampMixin, Base):
    """A subscription tier with usage limits. Nobody is billed; the limits are enforced in-app."""

    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("max_active_jobs > 0", name="jobs_positive"),
        CheckConstraint("max_staff_seats > 0", name="seats_positive"),
    )

    name: Mapped[str] = mapped_column(String(50), unique=True)
    max_active_jobs: Mapped[int]
    max_staff_seats: Mapped[int]
    # Plans are deactivated rather than deleted, so companies pointing at one never dangle.
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")

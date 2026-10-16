# Importing every model here registers it on Base.metadata, which Alembic reads to autogenerate
# migrations. A model that isn't imported is invisible to migrations.
from app.models.base import Base
from app.models.company import Company, CompanyStatus
from app.models.plan import Plan
from app.models.staff import Role, StaffMember, StaffRole
from app.models.user import User

__all__ = [
    "Base",
    "Company",
    "CompanyStatus",
    "Plan",
    "Role",
    "StaffMember",
    "StaffRole",
    "User",
]

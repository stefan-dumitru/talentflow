import enum
import uuid
from dataclasses import dataclass

from app.core.tenancy import TenantScope
from app.models import Role


class PrincipalKind(enum.StrEnum):
    CANDIDATE = "candidate"
    STAFF = "staff"
    PLATFORM_ADMIN = "platform_admin"
    # Staff whose account an admin deactivated. They can still sign in with Microsoft, so the
    # app has to recognise them and show a clear page, but they get access to nothing.
    ACCOUNT_DISABLED = "account_disabled"


@dataclass(frozen=True)
class Principal:
    """Who is making this request, as TalentFlow's own database sees them.

    Built once per request from the validated token plus the database. The token only proves
    identity; kind, company and roles always come from here.
    """

    user_id: uuid.UUID
    email: str
    display_name: str
    kind: PrincipalKind
    company_id: uuid.UUID | None = None
    roles: frozenset[Role] = frozenset()

    def tenant_scope(self) -> TenantScope:
        """Which company data this person's database sessions may touch."""
        if self.kind is PrincipalKind.STAFF and self.company_id is not None:
            return TenantScope.for_company(self.company_id)
        return TenantScope.no_company_data()

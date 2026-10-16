import uuid

from pydantic import BaseModel

from app.core.principal import PrincipalKind
from app.models import Role


class CompanyBrief(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class MeResponse(BaseModel):
    """What the app needs to know about the signed-in person to show the right screens."""

    kind: PrincipalKind
    user_id: uuid.UUID
    email: str
    display_name: str
    roles: list[Role]
    company: CompanyBrief | None

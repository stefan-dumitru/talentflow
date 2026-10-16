import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models import Role


class StaffMemberOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_active: bool
    roles: list[Role]
    created_at: datetime


class StaffPage(BaseModel):
    items: list[StaffMemberOut]
    total: int
    limit: int
    offset: int

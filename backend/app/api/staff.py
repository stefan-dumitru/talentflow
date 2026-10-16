import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.auth import get_scoped_db, require_roles
from app.core.principal import Principal
from app.models import Role, StaffMember
from app.schemas.staff import StaffMemberOut, StaffPage

router = APIRouter(prefix="/api/staff", tags=["staff"])

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

# No company filter anywhere below: the session is scoped to the caller's company, so it
# physically cannot return anyone else's staff (see app/core/tenancy.py).
CompanyAdmin = Annotated[Principal, Depends(require_roles(Role.COMPANY_ADMIN))]
ScopedSession = Annotated[Session, Depends(get_scoped_db)]


def _to_output(member: StaffMember) -> StaffMemberOut:
    return StaffMemberOut(
        id=member.id,
        email=member.user.email,
        display_name=member.user.display_name,
        is_active=member.is_active,
        roles=sorted(staff_role.role for staff_role in member.roles),
        created_at=member.created_at,
    )


@router.get("")
def list_staff(
    _admin: CompanyAdmin,
    session: ScopedSession,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> StaffPage:
    """The staff of the caller's company, newest last. Company admins only."""
    total = session.scalar(select(func.count()).select_from(StaffMember)) or 0
    members = session.scalars(
        select(StaffMember)
        # Relationships are set to raise when touched lazily, so load what the output needs now.
        .options(joinedload(StaffMember.user), selectinload(StaffMember.roles))
        .order_by(StaffMember.created_at, StaffMember.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return StaffPage(
        items=[_to_output(member) for member in members], total=total, limit=limit, offset=offset
    )


@router.get("/{staff_id}")
def read_staff_member(
    _admin: CompanyAdmin, session: ScopedSession, staff_id: uuid.UUID
) -> StaffMemberOut:
    """One staff member of the caller's company. Company admins only."""
    member = session.scalar(
        select(StaffMember)
        .where(StaffMember.id == staff_id)
        .options(joinedload(StaffMember.user), selectinload(StaffMember.roles))
    )
    if member is None:
        # Same answer for "doesn't exist" and "belongs to another company", so IDs can't be probed.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return _to_output(member)

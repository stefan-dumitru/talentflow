from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_principal, get_scoped_db
from app.core.principal import Principal
from app.models import Company
from app.schemas.me import CompanyBrief, MeResponse

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me")
def read_me(
    principal: Annotated[Principal, Depends(get_principal)],
    session: Annotated[Session, Depends(get_scoped_db)],
) -> MeResponse:
    """Who am I? The frontend calls this after sign-in to pick the right screens."""
    company = None
    if principal.company_id is not None:
        company_row = session.get(Company, principal.company_id)
        if company_row is not None:
            company = CompanyBrief(id=company_row.id, name=company_row.name, slug=company_row.slug)

    return MeResponse(
        kind=principal.kind,
        user_id=principal.user_id,
        email=principal.email,
        display_name=principal.display_name,
        roles=sorted(principal.roles),
        company=company,
    )

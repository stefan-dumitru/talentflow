"""Central company scoping: one place that keeps each company's data away from the others.

Every model that belongs to a company inherits `CompanyOwned`. Every ORM session must declare
which company it acts for (`TenantScope`). From then on this module quietly adds
`company_id = <that company>` to every query, update and delete that touches company-owned
data, so route and service code never has to remember to filter.

Fail-closed: a session that declared nothing cannot read or change company data at all.
Forgetting a filter therefore causes an error in a test, never a data leak in production.

Not covered, by design: raw SQL (`text()`), which bypasses the ORM, and ORM *inserts*. Rows
being created must carry the right `company_id` explicitly; the services do that.
"""

import enum
import uuid
from dataclasses import dataclass
from typing import cast

from sqlalchemy import Table, event
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria
from sqlalchemy.sql import visitors
from sqlalchemy.sql.base import Executable
from sqlalchemy.sql.visitors import ExternallyTraversible

from app.models.base import Base
from app.models.mixins import CompanyOwned

# Where a session keeps its declared scope (Session.info is a free-form dict SQLAlchemy offers).
SCOPE_KEY = "tenant_scope"


class TenancyError(Exception):
    """Company data was requested by a session that isn't allowed to see it."""


class ScopeKind(enum.Enum):
    COMPANY = "company"
    UNRESTRICTED = "unrestricted"
    NO_COMPANY_DATA = "no_company_data"


@dataclass(frozen=True)
class TenantScope:
    """Which company data a session may touch."""

    kind: ScopeKind
    company_id: uuid.UUID | None = None

    @classmethod
    def for_company(cls, company_id: uuid.UUID) -> "TenantScope":
        """Staff of one company: that company's rows only."""
        return cls(ScopeKind.COMPANY, company_id)

    @classmethod
    def unrestricted(cls) -> "TenantScope":
        """Every company's rows. Only for code that legitimately spans companies: resolving who
        a signed-in user is, platform administration, the CLI, and tests that arrange data."""
        return cls(ScopeKind.UNRESTRICTED)

    @classmethod
    def no_company_data(cls) -> "TenantScope":
        """Global data only. This is what a candidate's requests get."""
        return cls(ScopeKind.NO_COMPANY_DATA)


def set_scope(session: Session, scope: TenantScope) -> None:
    """Declare what a session may touch. A scope can't be changed afterwards, so code holding a
    request's session can't quietly widen it."""
    existing = session.info.get(SCOPE_KEY)
    if existing is not None and existing != scope:
        raise TenancyError("This session already has a scope and it cannot be changed.")
    session.info[SCOPE_KEY] = scope


def _company_owned_table_names() -> set[str]:
    return {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if issubclass(mapper.class_, CompanyOwned) and isinstance(mapper.local_table, Table)
    }


def _touches_company_data(statement: Executable) -> bool:
    # Walk every table anywhere in the statement (selected columns, joins, subqueries, update and
    # delete targets). Looking only at the entities being selected would miss company tables
    # reached through `select_from(...)` or a join, e.g. `select(User.email).join(StaffMember)`.
    owned = _company_owned_table_names()
    # Every ORM statement is a SQL element at runtime; SQLAlchemy's type hints just don't say so.
    traversible = cast(ExternallyTraversible, statement)
    return any(
        isinstance(element, Table) and element.name in owned
        for element in visitors.iterate(traversible)
    )


def _apply_company_scope(state: ORMExecuteState) -> None:
    # Runs for every ORM query on every Session, including the follow-up queries SQLAlchemy
    # makes for eager-loaded relationships. Those matter: a query on a global table can still
    # pull in company data through a relationship, so they get the same check and filter.
    if not state.is_orm_statement or state.is_insert:
        return
    if not _touches_company_data(state.statement):
        return

    scope: TenantScope | None = state.session.info.get(SCOPE_KEY)
    if scope is None:
        raise TenancyError(
            "This query touches company-owned data, but the session has no company scope "
            "declared. Open it with a TenantScope."
        )
    if scope.kind is ScopeKind.NO_COMPANY_DATA:
        raise TenancyError("This session has no access to company data.")
    if scope.kind is ScopeKind.UNRESTRICTED:
        return

    company_id = scope.company_id
    # One criterion applied to every CompanyOwned model in the statement, joins included.
    state.statement = state.statement.options(
        with_loader_criteria(
            CompanyOwned,
            lambda model: model.company_id == company_id,
            include_aliases=True,
        )
    )


event.listen(Session, "do_orm_execute", _apply_company_scope)

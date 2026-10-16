from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.orm import Session, aliased, selectinload

from app.core.tenancy import TenancyError, TenantScope, set_scope
from app.models import Company, Plan, Role, StaffMember, StaffRole, User
from app.services.staff import add_staff_member

SessionWithScope = Callable[[TenantScope], Session]


@dataclass
class TwoCompanies:
    acme: Company
    globex: Company
    ann: StaffMember  # Acme admin
    bob: StaffMember  # Acme interviewer
    gina: StaffMember  # Globex admin


@pytest.fixture
def two_companies(db_session: Session, make_company: Callable[..., Company]) -> TwoCompanies:
    acme, globex = make_company("acme"), make_company("globex")
    return TwoCompanies(
        acme=acme,
        globex=globex,
        ann=add_staff_member(
            db_session, acme, "ann@acme.test", "Ann", [Role.COMPANY_ADMIN, Role.RECRUITER]
        ),
        bob=add_staff_member(db_session, acme, "bob@acme.test", "Bob", [Role.INTERVIEWER]),
        gina=add_staff_member(db_session, globex, "gina@globex.test", "Gina", [Role.COMPANY_ADMIN]),
    )


class TestCompanyScope:
    """A session scoped to Acme sees Acme's rows and nothing of Globex's."""

    def test_queries_return_only_the_scoped_companys_rows(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        session = session_with_scope(TenantScope.for_company(two_companies.acme.id))

        members = session.scalars(select(StaffMember)).all()

        assert {m.id for m in members} == {two_companies.ann.id, two_companies.bob.id}

    def test_another_companys_record_cannot_be_fetched_by_its_id(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        session = session_with_scope(TenantScope.for_company(two_companies.acme.id))

        by_get = session.get(StaffMember, two_companies.gina.id)
        by_query = session.scalars(
            select(StaffMember).where(StaffMember.id == two_companies.gina.id)
        ).first()

        assert by_get is None
        assert by_query is None

    def test_counts_only_count_the_scoped_company(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        session = session_with_scope(TenantScope.for_company(two_companies.globex.id))

        member_count = session.scalar(select(func.count()).select_from(StaffMember))
        role_count = session.scalar(select(func.count()).select_from(StaffRole))

        assert member_count == 1  # Gina
        assert role_count == 1  # Gina's admin role

    def test_joins_are_filtered(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        session = session_with_scope(TenantScope.for_company(two_companies.acme.id))

        emails = session.scalars(
            select(User.email).join(StaffMember, StaffMember.user_id == User.id)
        ).all()

        assert sorted(emails) == ["ann@acme.test", "bob@acme.test"]

    def test_children_loaded_alongside_global_rows_are_filtered_too(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        # Users are global, so every user comes back. But the staff record hanging off each one
        # is company data: Globex's must not slip in through the eager load.
        session = session_with_scope(TenantScope.for_company(two_companies.acme.id))

        users = session.scalars(select(User).options(selectinload(User.staff_member))).all()

        staff_by_email = {u.email: u.staff_member for u in users}
        assert staff_by_email["ann@acme.test"] is not None
        assert staff_by_email["gina@globex.test"] is None

    def test_an_update_cannot_touch_another_companys_rows(
        self,
        db_session: Session,
        session_with_scope: SessionWithScope,
        two_companies: TwoCompanies,
    ) -> None:
        session = session_with_scope(TenantScope.for_company(two_companies.acme.id))

        result = session.execute(
            update(StaffMember)
            .where(StaffMember.id == two_companies.gina.id)
            .values(is_active=False, deactivated_at=datetime.now(UTC))
        )

        assert result.rowcount == 0  # type: ignore[attr-defined]
        db_session.refresh(two_companies.gina)
        assert two_companies.gina.is_active is True

    def test_a_delete_cannot_touch_another_companys_rows(
        self,
        db_session: Session,
        session_with_scope: SessionWithScope,
        two_companies: TwoCompanies,
    ) -> None:
        session = session_with_scope(TenantScope.for_company(two_companies.acme.id))

        result = session.execute(
            delete(StaffRole).where(StaffRole.staff_member_id == two_companies.gina.id)
        )

        assert result.rowcount == 0  # type: ignore[attr-defined]
        remaining = db_session.scalar(
            select(func.count())
            .select_from(StaffRole)
            .where(StaffRole.staff_member_id == two_companies.gina.id)
        )
        assert remaining == 1

    def test_outer_joins_filter_the_company_side_without_dropping_global_rows(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        session = session_with_scope(TenantScope.for_company(two_companies.acme.id))

        rows = session.execute(
            select(User.email, StaffMember.id).outerjoin(
                StaffMember, StaffMember.user_id == User.id
            )
        ).all()

        staff_id_by_email = {email: staff_id for email, staff_id in rows}
        assert set(staff_id_by_email) == {"ann@acme.test", "bob@acme.test", "gina@globex.test"}
        assert staff_id_by_email["gina@globex.test"] is None

    def test_subqueries_are_filtered(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        session = session_with_scope(TenantScope.for_company(two_companies.acme.id))

        emails = session.scalars(
            select(User.email).where(User.id.in_(select(StaffMember.user_id)))
        ).all()

        assert sorted(emails) == ["ann@acme.test", "bob@acme.test"]

    def test_exists_checks_are_filtered(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        session = session_with_scope(TenantScope.for_company(two_companies.acme.id))

        emails = session.scalars(
            select(User.email).where(exists().where(StaffMember.user_id == User.id))
        ).all()

        assert sorted(emails) == ["ann@acme.test", "bob@acme.test"]

    def test_aliased_models_are_filtered(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        session = session_with_scope(TenantScope.for_company(two_companies.acme.id))
        colleague = aliased(StaffMember)

        found = session.scalars(select(colleague)).all()

        assert {m.id for m in found} == {two_companies.ann.id, two_companies.bob.id}

    def test_global_tables_are_not_filtered(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        session = session_with_scope(TenantScope.for_company(two_companies.acme.id))

        plan_names = set(session.scalars(select(Plan.name)))

        assert plan_names == {"Free", "Pro", "Business"}


class TestFailClosed:
    """No declared scope means no access to company data, rather than access to all of it."""

    def test_a_session_with_no_declared_scope_cannot_read_company_data(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        session = session_with_scope(None)

        with pytest.raises(TenancyError, match="no company scope"):
            session.scalars(select(StaffMember)).all()

    def test_an_undeclared_session_cannot_get_by_id_or_count_either(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        session = session_with_scope(None)

        with pytest.raises(TenancyError):
            session.get(StaffMember, two_companies.ann.id)
        with pytest.raises(TenancyError):
            session.scalar(select(func.count()).select_from(StaffRole))

    def test_company_data_cannot_sneak_in_through_an_eager_load(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        # The top-level query is on users (global), but the eager load fetches staff records.
        session = session_with_scope(None)

        with pytest.raises(TenancyError):
            session.scalars(select(User).options(selectinload(User.staff_member))).all()

    def test_global_tables_work_without_a_declared_scope(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        session = session_with_scope(None)

        assert session.scalars(select(Plan)).all()
        assert session.scalars(select(User)).all()
        assert session.scalars(select(Company)).all()

    def test_a_session_with_no_company_access_cannot_read_company_data(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        # This is the scope a candidate's requests get: candidates belong to no company.
        session = session_with_scope(TenantScope.no_company_data())

        with pytest.raises(TenancyError, match="no access to company data"):
            session.scalars(select(StaffMember)).all()
        assert session.scalars(select(Plan)).all()  # global data is still fine

    def test_unrestricted_has_to_be_declared_and_then_sees_every_company(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        session = session_with_scope(TenantScope.unrestricted())

        members = session.scalars(select(StaffMember)).all()

        assert {m.id for m in members} == {
            two_companies.ann.id,
            two_companies.bob.id,
            two_companies.gina.id,
        }

    def test_a_scope_cannot_be_widened_once_declared(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        session = session_with_scope(TenantScope.for_company(two_companies.acme.id))

        with pytest.raises(TenancyError, match="already has a scope"):
            set_scope(session, TenantScope.unrestricted())

    def test_declaring_the_same_scope_again_is_harmless(
        self, session_with_scope: SessionWithScope, two_companies: TwoCompanies
    ) -> None:
        scope = TenantScope.for_company(two_companies.acme.id)
        session = session_with_scope(scope)

        set_scope(session, scope)  # no error

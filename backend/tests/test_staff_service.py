from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Role, StaffMember, StaffRole, User
from app.services.staff import (
    EmailAlreadyInUseError,
    LastCompanyAdminError,
    StaffError,
    add_staff_member,
    deactivate_staff_member,
)


def _roles_of(session: Session, member: StaffMember) -> set[Role]:
    return set(
        session.scalars(select(StaffRole.role).where(StaffRole.staff_member_id == member.id))
    )


class TestAddStaffMember:
    def test_creates_the_user_the_staff_record_and_the_roles(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        acme = make_company()

        member = add_staff_member(
            db_session,
            acme,
            " Ann@Example.com ",
            " Ann Ionescu ",
            [Role.RECRUITER, Role.INTERVIEWER],
        )

        user = db_session.get(User, member.user_id)
        assert user is not None
        assert user.email == "Ann@Example.com"  # trimmed, original case kept for display
        assert user.display_name == "Ann Ionescu"
        assert user.external_id is None  # linked later, on first sign-in
        assert member.company_id == acme.id
        assert member.is_active is True
        assert _roles_of(db_session, member) == {Role.RECRUITER, Role.INTERVIEWER}

    def test_listing_a_role_twice_grants_it_once(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        member = add_staff_member(
            db_session, make_company(), "ann@example.com", "Ann", [Role.RECRUITER, Role.RECRUITER]
        )

        assert _roles_of(db_session, member) == {Role.RECRUITER}

    def test_needs_at_least_one_role(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        with pytest.raises(StaffError, match="at least one role"):
            add_staff_member(db_session, make_company(), "ann@example.com", "Ann", [])

    def test_refuses_an_email_that_belongs_to_a_candidate(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        db_session.add(User(email="cara@example.com", display_name="Cara", external_id="oid-9"))
        db_session.flush()

        with pytest.raises(EmailAlreadyInUseError, match="candidate account"):
            add_staff_member(
                db_session, make_company(), "cara@example.com", "Cara", [Role.RECRUITER]
            )

    def test_refuses_an_email_that_is_already_staff_in_any_company(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        add_staff_member(
            db_session, make_company("acme"), "ann@example.com", "Ann", [Role.RECRUITER]
        )

        with pytest.raises(EmailAlreadyInUseError, match="staff member"):
            add_staff_member(
                db_session, make_company("globex"), "ann@example.com", "Ann", [Role.RECRUITER]
            )

    def test_refuses_an_email_that_belongs_to_a_platform_admin(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        db_session.add(User(email="root@example.com", display_name="Root", is_platform_admin=True))
        db_session.flush()

        with pytest.raises(EmailAlreadyInUseError, match="platform administrator"):
            add_staff_member(
                db_session, make_company(), "root@example.com", "Root", [Role.COMPANY_ADMIN]
            )

    def test_email_conflicts_ignore_case(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        db_session.add(User(email="cara@example.com", display_name="Cara", external_id="oid-9"))
        db_session.flush()

        with pytest.raises(EmailAlreadyInUseError):
            add_staff_member(
                db_session, make_company(), "CARA@EXAMPLE.COM", "Cara", [Role.RECRUITER]
            )


class TestDeactivateStaffMember:
    def test_deactivating_sets_the_flag_and_the_time(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        member = add_staff_member(
            db_session, make_company(), "ann@example.com", "Ann", [Role.RECRUITER]
        )

        deactivate_staff_member(db_session, member)

        assert member.is_active is False
        assert member.deactivated_at is not None

    def test_the_last_active_admin_cannot_be_deactivated(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        admin = add_staff_member(
            db_session, make_company(), "boss@example.com", "Boss", [Role.COMPANY_ADMIN]
        )

        with pytest.raises(LastCompanyAdminError):
            deactivate_staff_member(db_session, admin)

        assert admin.is_active is True

    def test_an_admin_can_be_deactivated_when_another_admin_is_active(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        acme = make_company()
        first = add_staff_member(db_session, acme, "a@example.com", "A", [Role.COMPANY_ADMIN])
        add_staff_member(db_session, acme, "b@example.com", "B", [Role.COMPANY_ADMIN])

        deactivate_staff_member(db_session, first)

        assert first.is_active is False

    def test_an_inactive_admin_does_not_count_as_a_spare(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        acme = make_company()
        first = add_staff_member(db_session, acme, "a@example.com", "A", [Role.COMPANY_ADMIN])
        second = add_staff_member(db_session, acme, "b@example.com", "B", [Role.COMPANY_ADMIN])
        deactivate_staff_member(db_session, first)

        with pytest.raises(LastCompanyAdminError):
            deactivate_staff_member(db_session, second)

    def test_an_admin_of_another_company_does_not_count_as_a_spare(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        acme_admin = add_staff_member(
            db_session, make_company("acme"), "a@example.com", "A", [Role.COMPANY_ADMIN]
        )
        add_staff_member(
            db_session, make_company("globex"), "g@example.com", "G", [Role.COMPANY_ADMIN]
        )

        with pytest.raises(LastCompanyAdminError):
            deactivate_staff_member(db_session, acme_admin)

    def test_staff_without_the_admin_role_can_always_be_deactivated(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        acme = make_company()
        add_staff_member(db_session, acme, "boss@example.com", "Boss", [Role.COMPANY_ADMIN])
        recruiter = add_staff_member(db_session, acme, "r@example.com", "R", [Role.RECRUITER])

        deactivate_staff_member(db_session, recruiter)

        assert recruiter.is_active is False

    def test_deactivating_someone_already_inactive_changes_nothing(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        member = add_staff_member(
            db_session, make_company(), "ann@example.com", "Ann", [Role.RECRUITER]
        )
        deactivate_staff_member(db_session, member)
        first_deactivation = member.deactivated_at

        deactivate_staff_member(db_session, member)

        assert member.deactivated_at == first_deactivation

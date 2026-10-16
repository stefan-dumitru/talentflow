from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.models import Company, Plan, Role, StaffMember, StaffRole, User


def _make_staff_member(session: Session, company: Company, email: str) -> StaffMember:
    user = User(email=email, display_name="Test Person")
    session.add(user)
    session.flush()
    member = StaffMember(company_id=company.id, user_id=user.id)
    session.add(member)
    session.flush()
    return member


def test_the_three_plans_are_seeded_with_their_limits(db_session: Session) -> None:
    plans = db_session.scalars(select(Plan).order_by(Plan.max_active_jobs)).all()

    assert [(p.name, p.max_active_jobs, p.max_staff_seats) for p in plans] == [
        ("Free", 2, 3),
        ("Pro", 10, 15),
        ("Business", 50, 100),
    ]


def test_plan_limits_must_be_positive(db_session: Session) -> None:
    db_session.add(Plan(name="Broken", max_active_jobs=0, max_staff_seats=5))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_user_emails_are_unique_ignoring_case(db_session: Session) -> None:
    db_session.add(User(email="Ann@Example.com", display_name="Ann"))
    db_session.flush()

    db_session.add(User(email="ann@example.COM", display_name="Another Ann"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_many_users_can_have_no_external_id_yet(db_session: Session) -> None:
    # Pre-created staff have no External ID until their first sign-in; that must not collide.
    db_session.add_all(
        [
            User(email="one@example.com", display_name="One"),
            User(email="two@example.com", display_name="Two"),
        ]
    )

    db_session.flush()


def test_two_users_cannot_share_an_external_id(db_session: Session) -> None:
    db_session.add(User(email="a@example.com", display_name="A", external_id="oid-1"))
    db_session.flush()

    db_session.add(User(email="b@example.com", display_name="B", external_id="oid-1"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_a_user_has_at_most_one_staff_record(
    db_session: Session, make_company: Callable[..., Company]
) -> None:
    acme, globex = make_company("acme"), make_company("globex")
    member = _make_staff_member(db_session, acme, "ann@example.com")

    # Same user, different company: staff belong to exactly one company.
    db_session.add(StaffMember(company_id=globex.id, user_id=member.user_id))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_the_same_role_cannot_be_granted_twice(
    db_session: Session, make_company: Callable[..., Company]
) -> None:
    acme = make_company()
    member = _make_staff_member(db_session, acme, "ann@example.com")
    db_session.add(StaffRole(staff_member_id=member.id, company_id=acme.id, role=Role.RECRUITER))
    db_session.flush()

    db_session.add(StaffRole(staff_member_id=member.id, company_id=acme.id, role=Role.RECRUITER))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_a_role_cannot_name_a_different_company_than_its_staff_member(
    db_session: Session, make_company: Callable[..., Company]
) -> None:
    acme, globex = make_company("acme"), make_company("globex")
    member = _make_staff_member(db_session, acme, "ann@example.com")

    # Ann works at Acme, but this row claims her role belongs to Globex.
    db_session.add(
        StaffRole(staff_member_id=member.id, company_id=globex.id, role=Role.COMPANY_ADMIN)
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_an_unknown_role_is_rejected_by_the_database(
    db_session: Session, make_company: Callable[..., Company]
) -> None:
    acme = make_company()
    member = _make_staff_member(db_session, acme, "ann@example.com")

    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO staff_roles (staff_member_id, company_id, role) "
                "VALUES (:member, :company, 'superuser')"
            ),
            {"member": member.id, "company": acme.id},
        )


def test_an_inactive_staff_member_must_have_a_deactivation_time(
    db_session: Session, make_company: Callable[..., Company]
) -> None:
    member = _make_staff_member(db_session, make_company(), "ann@example.com")

    member.is_active = False
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deactivating_with_a_time_is_allowed(
    db_session: Session, make_company: Callable[..., Company]
) -> None:
    member = _make_staff_member(db_session, make_company(), "ann@example.com")

    member.is_active = False
    member.deactivated_at = datetime.now(UTC)

    db_session.flush()


@pytest.mark.parametrize("bad_slug", ["Acme", "acme corp", "-acme", "acme-", "a--b", "ac_me", ""])
def test_company_slugs_must_be_lowercase_and_url_safe(
    db_session: Session, make_company: Callable[..., Company], bad_slug: str
) -> None:
    with pytest.raises(IntegrityError):
        make_company(bad_slug)


@pytest.mark.parametrize("good_slug", ["acme", "acme-corp", "a1", "x-2-y"])
def test_valid_company_slugs_are_accepted(
    make_company: Callable[..., Company], good_slug: str
) -> None:
    assert make_company(good_slug).slug == good_slug


def test_company_slugs_are_unique(make_company: Callable[..., Company]) -> None:
    make_company("acme")

    with pytest.raises(IntegrityError):
        make_company("acme")


@pytest.mark.parametrize("bad_currency", ["eur", "E1R", "EU", ""])
def test_company_currency_must_be_three_capital_letters(
    db_session: Session, make_company: Callable[..., Company], bad_currency: str
) -> None:
    company = make_company()

    company.currency = bad_currency
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_a_new_company_starts_active_at_version_one(
    make_company: Callable[..., Company],
) -> None:
    company = make_company()

    assert company.status == "active"
    assert company.version == 1


def test_saving_a_company_that_changed_underneath_you_is_refused(
    db_session: Session, make_company: Callable[..., Company]
) -> None:
    company = make_company()
    # Someone else saves first, bumping the version behind our back.
    db_session.execute(
        text("UPDATE companies SET version = version + 1 WHERE id = :id"), {"id": company.id}
    )

    company.name = "Renamed by the slower editor"
    with pytest.raises(StaleDataError):
        db_session.flush()

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import open_session
from app.core.principal import Principal, PrincipalKind
from app.core.tenancy import ScopeKind, TenantScope
from app.models import Company, Role, User
from app.services.identity import IdentityError, resolve_principal
from app.services.staff import add_staff_member, deactivate_staff_member


def sign_in(
    session: Session,
    *,
    oid: str = "oid-ann",
    email: str | None = "ann@example.com",
    name: str | None = "Ann Ionescu",
) -> Principal:
    return resolve_principal(session, external_id=oid, email=email, display_name=name)


class TestFirstSignIn:
    def test_an_unknown_person_becomes_a_candidate(self, db_session: Session) -> None:
        principal = sign_in(db_session, oid="oid-new", email="new@example.com", name="New Person")

        assert principal.kind is PrincipalKind.CANDIDATE
        assert principal.company_id is None
        assert principal.roles == frozenset()
        user = db_session.get(User, principal.user_id)
        assert user is not None
        assert (user.external_id, user.email, user.display_name) == (
            "oid-new",
            "new@example.com",
            "New Person",
        )

    def test_signing_in_again_finds_the_same_user(self, db_session: Session) -> None:
        first = sign_in(db_session)
        second = sign_in(db_session)

        assert first.user_id == second.user_id
        assert db_session.scalar(select(func.count()).select_from(User)) == 1

    def test_the_email_is_the_display_name_when_the_token_has_no_name(
        self, db_session: Session
    ) -> None:
        principal = sign_in(db_session, name=None)

        assert principal.display_name == "ann@example.com"

    def test_a_new_person_without_an_email_claim_is_refused(self, db_session: Session) -> None:
        with pytest.raises(IdentityError, match="email"):
            sign_in(db_session, email=None)

    def test_a_known_person_can_sign_in_even_if_the_token_has_no_email(
        self, db_session: Session
    ) -> None:
        first = sign_in(db_session)

        again = sign_in(db_session, email=None)

        assert again.user_id == first.user_id


class TestLinkingPreCreatedStaff:
    def test_pre_created_staff_are_linked_on_first_sign_in_by_email(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        acme = make_company("acme")
        member = add_staff_member(
            db_session, acme, "ann@example.com", "Ann", [Role.RECRUITER, Role.INTERVIEWER]
        )

        principal = sign_in(db_session, oid="oid-ann", email="ann@example.com")

        assert principal.kind is PrincipalKind.STAFF
        assert principal.user_id == member.user_id
        assert principal.company_id == acme.id
        assert principal.roles == {Role.RECRUITER, Role.INTERVIEWER}
        user = db_session.get(User, member.user_id)
        assert user is not None
        assert user.external_id == "oid-ann"

    def test_matching_the_email_ignores_case(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        add_staff_member(db_session, make_company(), "Ann@Example.com", "Ann", [Role.RECRUITER])

        principal = sign_in(db_session, email="ANN@EXAMPLE.COM")

        assert principal.kind is PrincipalKind.STAFF

    def test_someone_else_cannot_take_over_an_already_linked_account(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        add_staff_member(db_session, make_company(), "ann@example.com", "Ann", [Role.COMPANY_ADMIN])
        sign_in(db_session, oid="oid-real-ann", email="ann@example.com")

        # A different login that claims the same email address.
        with pytest.raises(IdentityError):
            sign_in(db_session, oid="oid-impostor", email="ann@example.com")

        again = sign_in(db_session, oid="oid-real-ann", email="ann@example.com")
        assert again.kind is PrincipalKind.STAFF

    def test_a_pre_created_platform_admin_is_linked_too(self, db_session: Session) -> None:
        db_session.add(User(email="root@example.com", display_name="Root", is_platform_admin=True))
        db_session.flush()

        principal = sign_in(db_session, oid="oid-root", email="root@example.com")

        assert principal.kind is PrincipalKind.PLATFORM_ADMIN
        assert principal.company_id is None

    def test_deactivated_staff_are_recognised_but_disabled(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        member = add_staff_member(
            db_session, make_company(), "ann@example.com", "Ann", [Role.RECRUITER]
        )
        sign_in(db_session)
        deactivate_staff_member(db_session, member)

        principal = sign_in(db_session)

        assert principal.kind is PrincipalKind.ACCOUNT_DISABLED
        assert principal.roles == frozenset()
        assert principal.company_id is None

    def test_an_email_belonging_to_another_login_blocks_a_new_account(
        self, db_session: Session
    ) -> None:
        sign_in(db_session, oid="oid-1", email="shared@example.com")

        with pytest.raises(IdentityError):
            sign_in(db_session, oid="oid-2", email="shared@example.com")


class TestTenantScopeOfAPrincipal:
    def test_active_staff_are_scoped_to_their_company(
        self, db_session: Session, make_company: Callable[..., Company]
    ) -> None:
        acme = make_company()
        add_staff_member(db_session, acme, "ann@example.com", "Ann", [Role.RECRUITER])

        scope = sign_in(db_session).tenant_scope()

        assert scope == TenantScope.for_company(acme.id)

    @pytest.mark.parametrize("email", ["cara@example.com", "root@example.com"])
    def test_candidates_and_platform_admins_get_no_company_data(
        self, db_session: Session, email: str
    ) -> None:
        if email.startswith("root"):
            db_session.add(User(email=email, display_name="Root", is_platform_admin=True))
            db_session.flush()

        scope = sign_in(db_session, oid=f"oid-{email}", email=email).tenant_scope()

        assert scope.kind is ScopeKind.NO_COMPANY_DATA


@pytest.mark.usefixtures("clean_database")
def test_simultaneous_first_sign_ins_create_exactly_one_user() -> None:
    # The browser fires several API calls at once right after login, so the first few requests
    # of a brand-new user all try to create them. Needs real commits, so it uses real sessions.
    workers = 8
    start_together = threading.Barrier(workers)

    def first_sign_in(_: int) -> UUID:
        with open_session(TenantScope.unrestricted()) as session:
            start_together.wait()
            principal = resolve_principal(
                session, external_id="oid-race", email="race@example.com", display_name="Racer"
            )
            session.commit()
            return principal.user_id

    with ThreadPoolExecutor(max_workers=workers) as pool:
        user_ids = list(pool.map(first_sign_in, range(workers)))

    assert len(set(user_ids)) == 1
    with open_session(TenantScope.unrestricted()) as session:
        assert session.scalar(select(func.count()).select_from(User)) == 1

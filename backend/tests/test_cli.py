import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.cli import (
    CliError,
    add_staff,
    main,
    make_platform_admin,
    parse_roles,
    seed_dev,
)
from app.models import Company, Role, StaffMember, StaffRole, User
from app.services.companies import CompanyError
from app.services.staff import EmailAlreadyInUseError


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def roles_of(session: Session, email: str) -> set[Role]:
    return set(
        session.scalars(
            select(StaffRole.role)
            .join(StaffMember, StaffMember.id == StaffRole.staff_member_id)
            .join(User, User.id == StaffMember.user_id)
            .where(User.email == email)
        )
    )


class TestParseRoles:
    def test_comma_separated_names_become_roles(self) -> None:
        assert parse_roles("recruiter, interviewer") == {Role.RECRUITER, Role.INTERVIEWER}

    def test_a_single_role_works(self) -> None:
        assert parse_roles("company_admin") == {Role.COMPANY_ADMIN}

    def test_an_unknown_role_is_rejected_and_the_valid_ones_are_listed(self) -> None:
        with pytest.raises(CliError, match="superuser") as error:
            parse_roles("recruiter,superuser")

        assert "company_admin" in str(error.value)
        assert "hiring_manager" in str(error.value)

    @pytest.mark.parametrize("empty", ["", " ", ","])
    def test_an_empty_list_is_rejected(self, empty: str) -> None:
        with pytest.raises(CliError):
            parse_roles(empty)


class TestSeedDev:
    def test_creates_two_companies_each_with_an_admin(self, db_session: Session) -> None:
        seed_dev(db_session, "ann@example.com", "gina@example.com")

        companies = {c.slug: c for c in db_session.scalars(select(Company))}
        assert set(companies) == {"acme", "globex"}
        assert roles_of(db_session, "ann@example.com") == {Role.COMPANY_ADMIN}
        assert roles_of(db_session, "gina@example.com") == {Role.COMPANY_ADMIN}

    def test_each_admin_belongs_to_their_own_company(self, db_session: Session) -> None:
        seed_dev(db_session, "ann@example.com", "gina@example.com")

        rows = db_session.execute(
            select(User.email, Company.slug)
            .join(StaffMember, StaffMember.user_id == User.id)
            .join(Company, Company.id == StaffMember.company_id)
        )
        company_of = {email: slug for email, slug in rows}
        assert company_of == {"ann@example.com": "acme", "gina@example.com": "globex"}

    def test_running_it_again_changes_nothing(self, db_session: Session) -> None:
        seed_dev(db_session, "ann@example.com", "gina@example.com")

        second_run_report = seed_dev(db_session, "ann@example.com", "gina@example.com")

        assert count(db_session, Company) == 2
        assert count(db_session, StaffMember) == 2
        assert count(db_session, User) == 2
        assert all("already" in line for line in second_run_report)

    def test_the_report_says_what_was_created(self, db_session: Session) -> None:
        report = seed_dev(db_session, "ann@example.com", "gina@example.com")

        assert any("created company" in line and "acme" in line for line in report)
        assert any("created company" in line and "globex" in line for line in report)

    def test_refuses_an_admin_email_that_belongs_to_a_candidate(self, db_session: Session) -> None:
        db_session.add(User(email="cara@example.com", display_name="Cara", external_id="oid-9"))
        db_session.flush()

        with pytest.raises(EmailAlreadyInUseError, match="candidate"):
            seed_dev(db_session, "cara@example.com", "gina@example.com")

    def test_refuses_the_same_email_for_both_admins(self, db_session: Session) -> None:
        with pytest.raises(EmailAlreadyInUseError):
            seed_dev(db_session, "same@example.com", "same@example.com")

    def test_complains_clearly_when_the_plans_are_missing(self, db_session: Session) -> None:
        # (rolled back with the rest of the test)
        db_session.execute(text("DELETE FROM plans"))

        with pytest.raises(CompanyError, match="migrations"):
            seed_dev(db_session, "ann@example.com", "gina@example.com")

    @pytest.mark.parametrize("bad_email", ["not-an-email", "a@b", "@example.com", "a b@c.com", ""])
    def test_rejects_malformed_emails(self, db_session: Session, bad_email: str) -> None:
        with pytest.raises(CliError, match="email"):
            seed_dev(db_session, bad_email, "gina@example.com")


class TestAddStaff:
    def test_adds_a_staff_member_with_roles(self, db_session: Session) -> None:
        seed_dev(db_session, "ann@example.com", "gina@example.com")

        add_staff(db_session, "acme", "bob@example.com", "Bob", "recruiter,interviewer")

        assert roles_of(db_session, "bob@example.com") == {Role.RECRUITER, Role.INTERVIEWER}

    def test_the_new_member_joins_the_named_company(self, db_session: Session) -> None:
        seed_dev(db_session, "ann@example.com", "gina@example.com")

        add_staff(db_session, "globex", "bob@example.com", "Bob", "recruiter")

        member = db_session.scalars(
            select(StaffMember)
            .join(User, User.id == StaffMember.user_id)
            .where(User.email == "bob@example.com")
        ).one()
        globex = db_session.scalars(select(Company).where(Company.slug == "globex")).one()
        assert member.company_id == globex.id

    def test_an_unknown_company_is_reported(self, db_session: Session) -> None:
        with pytest.raises(CliError, match="no-such-co"):
            add_staff(db_session, "no-such-co", "bob@example.com", "Bob", "recruiter")

    def test_refuses_an_email_that_is_already_used(self, db_session: Session) -> None:
        seed_dev(db_session, "ann@example.com", "gina@example.com")

        with pytest.raises(EmailAlreadyInUseError):
            add_staff(db_session, "acme", "ann@example.com", "Ann Again", "recruiter")

    def test_refuses_an_email_that_belongs_to_a_candidate(self, db_session: Session) -> None:
        seed_dev(db_session, "ann@example.com", "gina@example.com")
        db_session.add(User(email="cara@example.com", display_name="Cara", external_id="oid-9"))
        db_session.flush()

        with pytest.raises(EmailAlreadyInUseError, match="candidate"):
            add_staff(db_session, "acme", "cara@example.com", "Cara", "recruiter")

    def test_rejects_unknown_roles(self, db_session: Session) -> None:
        seed_dev(db_session, "ann@example.com", "gina@example.com")

        with pytest.raises(CliError, match="superuser"):
            add_staff(db_session, "acme", "bob@example.com", "Bob", "superuser")


class TestMakePlatformAdmin:
    def test_creates_a_platform_admin(self, db_session: Session) -> None:
        make_platform_admin(db_session, "root@example.com", "Root")

        user = db_session.scalars(select(User).where(User.email == "root@example.com")).one()
        assert user.is_platform_admin is True
        assert user.external_id is None  # linked on first sign-in
        assert count(db_session, StaffMember) == 0

    def test_running_it_again_changes_nothing(self, db_session: Session) -> None:
        make_platform_admin(db_session, "root@example.com", "Root")

        report = make_platform_admin(db_session, "root@example.com", "Root")

        assert count(db_session, User) == 1
        assert "already" in report[0]

    def test_refuses_an_email_that_belongs_to_staff(self, db_session: Session) -> None:
        seed_dev(db_session, "ann@example.com", "gina@example.com")

        with pytest.raises(EmailAlreadyInUseError, match="staff member"):
            make_platform_admin(db_session, "ann@example.com", "Ann")

    def test_refuses_an_email_that_belongs_to_a_candidate(self, db_session: Session) -> None:
        db_session.add(User(email="cara@example.com", display_name="Cara", external_id="oid-9"))
        db_session.flush()

        with pytest.raises(EmailAlreadyInUseError, match="candidate"):
            make_platform_admin(db_session, "cara@example.com", "Cara")


class TestMainEndToEnd:
    """Runs the command line the way a person does, against the real test database."""

    def test_seed_dev_saves_to_the_database_and_can_be_repeated(
        self, committed_session: Session, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = [
            "seed-dev",
            "--acme-admin-email",
            "ann@example.com",
            "--globex-admin-email",
            "g@example.com",
        ]

        first_exit = main(argv)
        second_exit = main(argv)

        assert (first_exit, second_exit) == (0, 0)
        assert count(committed_session, Company) == 2
        assert count(committed_session, StaffMember) == 2
        output = capsys.readouterr().out
        assert "created company" in output
        assert "already" in output

    def test_a_failed_seed_leaves_nothing_behind(
        self, committed_session: Session, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Acme's admin would be fine, Globex's email is taken: nothing at all may be saved.
        committed_session.add(
            User(email="cara@example.com", display_name="Cara", external_id="oid-9")
        )
        committed_session.commit()

        exit_code = main(
            [
                "seed-dev",
                "--acme-admin-email",
                "ann@example.com",
                "--globex-admin-email",
                "cara@example.com",
            ]
        )

        assert exit_code == 1
        assert "candidate account" in capsys.readouterr().err
        assert count(committed_session, Company) == 0
        assert count(committed_session, StaffMember) == 0

    def test_add_staff_and_platform_admin_commands_save(self, committed_session: Session) -> None:
        main(
            [
                "seed-dev",
                "--acme-admin-email",
                "ann@example.com",
                "--globex-admin-email",
                "g@example.com",
            ]
        )

        staff_exit = main(
            [
                "add-staff",
                "--company",
                "acme",
                "--email",
                "bob@example.com",
                "--name",
                "Bob",
                "--roles",
                "recruiter",
            ]
        )
        admin_exit = main(["make-platform-admin", "--email", "root@example.com", "--name", "Root"])

        assert (staff_exit, admin_exit) == (0, 0)
        assert count(committed_session, StaffMember) == 3
        assert (
            committed_session.scalars(select(User).where(User.email == "root@example.com"))
            .one()
            .is_platform_admin
        )

    def test_unknown_commands_and_missing_options_are_usage_errors(self) -> None:
        with pytest.raises(SystemExit) as unknown:
            main(["make-coffee"])
        with pytest.raises(SystemExit) as missing:
            main(["seed-dev"])

        assert unknown.value.code == 2
        assert missing.value.code == 2

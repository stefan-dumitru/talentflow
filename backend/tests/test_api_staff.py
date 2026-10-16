import uuid
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Company, Role, StaffMember, User
from app.services.staff import add_staff_member, deactivate_staff_member
from tests.auth_support import TokenFactory
from tests.support import create_company


@dataclass
class World:
    """Two companies. Acme: Ann (admin), Bob (recruiter). Globex: Gina (admin)."""

    acme: Company
    globex: Company
    ann: StaffMember
    bob: StaffMember
    gina: StaffMember


@pytest.fixture
def world(committed_session: Session) -> World:
    acme = create_company(committed_session, "acme")
    globex = create_company(committed_session, "globex")
    world = World(
        acme=acme,
        globex=globex,
        ann=add_staff_member(committed_session, acme, "ann@acme.test", "Ann", [Role.COMPANY_ADMIN]),
        bob=add_staff_member(committed_session, acme, "bob@acme.test", "Bob", [Role.RECRUITER]),
        gina=add_staff_member(
            committed_session, globex, "gina@globex.test", "Gina", [Role.COMPANY_ADMIN]
        ),
    )
    committed_session.commit()
    return world


def as_user(token_factory: TokenFactory, oid: str, email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_factory.make(oid=oid, email=email)}"}


class TestListStaff:
    def test_a_company_admin_sees_only_their_own_companys_staff(
        self, api_client: TestClient, world: World, token_factory: TokenFactory
    ) -> None:
        response = api_client.get(
            "/api/staff", headers=as_user(token_factory, "oid-ann", "ann@acme.test")
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        emails = sorted(item["email"] for item in body["items"])
        assert emails == ["ann@acme.test", "bob@acme.test"]
        assert "gina@globex.test" not in response.text

    def test_each_item_shows_roles_and_status(
        self, api_client: TestClient, world: World, token_factory: TokenFactory
    ) -> None:
        response = api_client.get(
            "/api/staff", headers=as_user(token_factory, "oid-ann", "ann@acme.test")
        )

        by_email = {item["email"]: item for item in response.json()["items"]}
        assert by_email["ann@acme.test"]["roles"] == ["company_admin"]
        assert by_email["bob@acme.test"]["roles"] == ["recruiter"]
        assert by_email["bob@acme.test"]["is_active"] is True
        assert by_email["bob@acme.test"]["display_name"] == "Bob"

    def test_results_are_paginated(
        self, api_client: TestClient, world: World, token_factory: TokenFactory
    ) -> None:
        headers = as_user(token_factory, "oid-ann", "ann@acme.test")

        first = api_client.get("/api/staff?limit=1&offset=0", headers=headers).json()
        second = api_client.get("/api/staff?limit=1&offset=1", headers=headers).json()
        beyond = api_client.get("/api/staff?limit=1&offset=2", headers=headers).json()

        assert (first["total"], first["limit"], first["offset"]) == (2, 1, 0)
        assert len(first["items"]) == len(second["items"]) == 1
        assert first["items"][0]["id"] != second["items"][0]["id"]
        assert beyond["items"] == []
        assert beyond["total"] == 2

    def test_the_default_page_size_is_25(
        self, api_client: TestClient, world: World, token_factory: TokenFactory
    ) -> None:
        body = api_client.get(
            "/api/staff", headers=as_user(token_factory, "oid-ann", "ann@acme.test")
        ).json()

        assert body["limit"] == 25

    @pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=-1", "offset=-1", "limit=x"])
    def test_out_of_range_paging_is_rejected(
        self, api_client: TestClient, world: World, token_factory: TokenFactory, query: str
    ) -> None:
        response = api_client.get(
            f"/api/staff?{query}", headers=as_user(token_factory, "oid-ann", "ann@acme.test")
        )

        assert response.status_code == 422


class TestGetStaffMember:
    def test_a_company_admin_can_read_a_colleague(
        self, api_client: TestClient, world: World, token_factory: TokenFactory
    ) -> None:
        response = api_client.get(
            f"/api/staff/{world.bob.id}",
            headers=as_user(token_factory, "oid-ann", "ann@acme.test"),
        )

        assert response.status_code == 200
        assert response.json()["email"] == "bob@acme.test"

    def test_another_companys_staff_member_looks_exactly_like_one_that_does_not_exist(
        self,
        api_client: TestClient,
        world: World,
        token_factory: TokenFactory,
    ) -> None:
        headers = as_user(token_factory, "oid-ann", "ann@acme.test")

        other_company = api_client.get(f"/api/staff/{world.gina.id}", headers=headers)
        nonexistent = api_client.get(f"/api/staff/{uuid.uuid4()}", headers=headers)

        assert other_company.status_code == 404
        assert other_company.status_code == nonexistent.status_code
        assert other_company.json() == nonexistent.json()
        assert "gina" not in other_company.text.lower()

    def test_the_other_company_cannot_read_acme_either(
        self, api_client: TestClient, world: World, token_factory: TokenFactory
    ) -> None:
        response = api_client.get(
            f"/api/staff/{world.ann.id}",
            headers=as_user(token_factory, "oid-gina", "gina@globex.test"),
        )

        assert response.status_code == 404

    def test_a_malformed_id_is_rejected(
        self, api_client: TestClient, world: World, token_factory: TokenFactory
    ) -> None:
        response = api_client.get(
            "/api/staff/not-a-uuid", headers=as_user(token_factory, "oid-ann", "ann@acme.test")
        )

        assert response.status_code == 422


class TestWhoMayUseTheStaffEndpoints:
    def test_staff_without_the_admin_role_are_forbidden(
        self, api_client: TestClient, world: World, token_factory: TokenFactory
    ) -> None:
        headers = as_user(token_factory, "oid-bob", "bob@acme.test")  # a recruiter

        assert api_client.get("/api/staff", headers=headers).status_code == 403
        assert api_client.get(f"/api/staff/{world.ann.id}", headers=headers).status_code == 403

    def test_candidates_are_forbidden(
        self, api_client: TestClient, world: World, token_factory: TokenFactory
    ) -> None:
        headers = as_user(token_factory, "oid-cara", "cara@example.com")

        assert api_client.get("/api/staff", headers=headers).status_code == 403
        assert api_client.get(f"/api/staff/{world.ann.id}", headers=headers).status_code == 403

    def test_platform_admins_cannot_read_company_staff(
        self,
        api_client: TestClient,
        committed_session: Session,
        world: World,
        token_factory: TokenFactory,
    ) -> None:
        committed_session.add(
            User(email="root@example.com", display_name="Root", is_platform_admin=True)
        )
        committed_session.commit()
        headers = as_user(token_factory, "oid-root", "root@example.com")

        assert api_client.get("/api/staff", headers=headers).status_code == 403
        assert api_client.get(f"/api/staff/{world.ann.id}", headers=headers).status_code == 403

    def test_a_deactivated_admin_is_forbidden(
        self,
        api_client: TestClient,
        committed_session: Session,
        world: World,
        token_factory: TokenFactory,
    ) -> None:
        # Acme needs a second admin before Ann can be deactivated.
        add_staff_member(
            committed_session, world.acme, "dan@acme.test", "Dan", [Role.COMPANY_ADMIN]
        )
        deactivate_staff_member(committed_session, world.ann)
        committed_session.commit()

        response = api_client.get(
            "/api/staff", headers=as_user(token_factory, "oid-ann", "ann@acme.test")
        )

        assert response.status_code == 403

    def test_no_token_is_unauthorized(self, api_client: TestClient, world: World) -> None:
        assert api_client.get("/api/staff").status_code == 401
        assert api_client.get(f"/api/staff/{world.ann.id}").status_code == 401

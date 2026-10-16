from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Role, User
from app.services.staff import add_staff_member, deactivate_staff_member
from tests.auth_support import TokenFactory
from tests.support import create_company


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_a_brand_new_person_is_a_candidate(
    api_client: TestClient, committed_session: Session, token_factory: TokenFactory
) -> None:
    token = token_factory.make(oid="oid-cara", email="cara@example.com", name="Cara Pop")

    response = api_client.get("/api/me", headers=bearer(token))

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "candidate"
    assert body["email"] == "cara@example.com"
    assert body["display_name"] == "Cara Pop"
    assert body["roles"] == []
    assert body["company"] is None
    assert committed_session.scalar(select(func.count()).select_from(User)) == 1


def test_asking_twice_does_not_create_a_second_user(
    api_client: TestClient, committed_session: Session, token_factory: TokenFactory
) -> None:
    headers = bearer(token_factory.make(oid="oid-cara", email="cara@example.com"))

    first = api_client.get("/api/me", headers=headers).json()
    second = api_client.get("/api/me", headers=headers).json()

    assert first["user_id"] == second["user_id"]
    assert committed_session.scalar(select(func.count()).select_from(User)) == 1


def test_pre_created_staff_see_their_roles_and_company(
    api_client: TestClient, committed_session: Session, token_factory: TokenFactory
) -> None:
    acme = create_company(committed_session, "acme")
    add_staff_member(
        committed_session, acme, "ann@acme.test", "Ann", [Role.RECRUITER, Role.INTERVIEWER]
    )
    committed_session.commit()
    token = token_factory.make(oid="oid-ann", email="ann@acme.test", name="Ann")

    response = api_client.get("/api/me", headers=bearer(token))

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "staff"
    assert sorted(body["roles"]) == ["interviewer", "recruiter"]
    assert body["company"] == {"id": str(acme.id), "name": "Acme", "slug": "acme"}


def test_deactivated_staff_are_told_their_account_is_disabled(
    api_client: TestClient, committed_session: Session, token_factory: TokenFactory
) -> None:
    acme = create_company(committed_session, "acme")
    member = add_staff_member(committed_session, acme, "ann@acme.test", "Ann", [Role.RECRUITER])
    deactivate_staff_member(committed_session, member)
    committed_session.commit()
    token = token_factory.make(oid="oid-ann", email="ann@acme.test")

    response = api_client.get("/api/me", headers=bearer(token))

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "account_disabled"
    assert body["roles"] == []
    assert body["company"] is None


def test_a_platform_admin_is_recognised(
    api_client: TestClient, committed_session: Session, token_factory: TokenFactory
) -> None:
    committed_session.add(
        User(email="root@example.com", display_name="Root", is_platform_admin=True)
    )
    committed_session.commit()
    token = token_factory.make(oid="oid-root", email="root@example.com")

    response = api_client.get("/api/me", headers=bearer(token))

    assert response.json()["kind"] == "platform_admin"


def test_the_response_does_not_expose_the_external_identity(
    api_client: TestClient, committed_session: Session, token_factory: TokenFactory
) -> None:
    token = token_factory.make(oid="oid-secret-identity", email="cara@example.com")

    response = api_client.get("/api/me", headers=bearer(token))

    assert "oid-secret-identity" not in response.text
    assert "external_id" not in response.json()


def test_a_new_person_whose_token_has_no_email_is_refused(
    api_client: TestClient, committed_session: Session, token_factory: TokenFactory
) -> None:
    response = api_client.get("/api/me", headers=bearer(token_factory.make(email=None)))

    assert response.status_code == 401
    assert committed_session.scalar(select(func.count()).select_from(User)) == 0

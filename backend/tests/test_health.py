from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.db import build_engine, get_engine

# Port 1 on localhost refuses connections immediately, so this fails fast.
UNREACHABLE_DATABASE_URL = "postgresql+psycopg://nobody:nothing@127.0.0.1:1/missing"


def test_live_returns_ok(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ok_when_database_is_reachable(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_503_when_database_is_unreachable(app: FastAPI) -> None:
    app.dependency_overrides[get_engine] = lambda: build_engine(UNREACHABLE_DATABASE_URL)

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_live_still_ok_when_database_is_unreachable(app: FastAPI) -> None:
    app.dependency_overrides[get_engine] = lambda: build_engine(UNREACHABLE_DATABASE_URL)

    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200


def test_ready_failure_does_not_leak_connection_details(app: FastAPI) -> None:
    app.dependency_overrides[get_engine] = lambda: build_engine(UNREACHABLE_DATABASE_URL)

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert "127.0.0.1" not in response.text
    assert "nobody" not in response.text

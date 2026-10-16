import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Routes that are allowed to answer without a signed-in user. Adding to this list is a
# deliberate security decision: it should be rare and reviewed.
PUBLIC_PATHS = {"/health/live", "/health/ready"}

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _routes(app: FastAPI) -> list[tuple[str, str]]:
    """Every (method, path) the app exposes, read from its public OpenAPI description.

    Going through OpenAPI rather than FastAPI's internal route objects keeps this check working
    however FastAPI organises its routers.
    """
    return [
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method in HTTP_METHODS
    ]


def _routes_open_to_anonymous_callers(app: FastAPI, client: TestClient) -> list[str]:
    open_routes = []
    for method, path in _routes(app):
        if path in PUBLIC_PATHS:
            continue
        # Any path parameter gets a well-formed UUID, so a 422 can't mask the auth answer.
        concrete_path = "/".join(
            str(uuid.uuid4()) if part.startswith("{") else part for part in path.split("/")
        )
        response = client.request(method, concrete_path)  # no Authorization header
        if response.status_code != 401:
            open_routes.append(f"{method} {path} answered {response.status_code}")
    return open_routes


def test_every_route_refuses_anonymous_callers_unless_explicitly_public(
    app: FastAPI, api_client: TestClient
) -> None:
    # Default-deny: a developer who adds an endpoint and forgets its auth dependency fails
    # here, instead of shipping an open endpoint.
    assert _routes_open_to_anonymous_callers(app, api_client) == []


def test_the_check_actually_looks_at_the_apps_routes(app: FastAPI) -> None:
    # Guards against the check passing vacuously because it found no routes to test.
    paths = {path for _, path in _routes(app)}

    assert {"/api/me", "/api/staff", "/api/staff/{staff_id}"} <= paths


def test_the_public_list_only_names_routes_that_exist(app: FastAPI) -> None:
    # Stops the allow-list quietly drifting out of date.
    assert {path for _, path in _routes(app)} >= PUBLIC_PATHS


def test_the_check_would_notice_an_open_route(app: FastAPI, api_client: TestClient) -> None:
    # Proves the check can fail: add a route with no auth and it must be flagged.
    @app.get("/api/oops-forgot-auth")
    def oops() -> dict[str, str]:
        return {}

    app.openapi_schema = None  # make FastAPI rebuild its description to include the new route

    assert _routes_open_to_anonymous_callers(app, api_client) == [
        "GET /api/oops-forgot-auth answered 200"
    ]

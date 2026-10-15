import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

INTERNAL_DETAIL = "secret-internal-detail-42"


def _app_with_failing_route(app: FastAPI) -> FastAPI:
    @app.get("/test-only/boom")
    def boom() -> None:
        raise RuntimeError(INTERNAL_DETAIL)

    return app


def test_unhandled_error_returns_generic_500(app: FastAPI) -> None:
    client = TestClient(_app_with_failing_route(app))

    response = client.get("/test-only/boom")

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert INTERNAL_DETAIL not in response.text
    assert "RuntimeError" not in response.text


def test_unhandled_error_response_carries_request_id(app: FastAPI) -> None:
    client = TestClient(_app_with_failing_route(app))

    response = client.get("/test-only/boom")

    body_request_id = response.json()["request_id"]
    assert body_request_id
    assert response.headers["X-Request-ID"] == body_request_id


def test_request_id_is_generated_when_missing(client: TestClient) -> None:
    response = client.get("/health/live")

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


def test_valid_client_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "abc-123.retry_1"})

    assert response.headers["X-Request-ID"] == "abc-123.retry_1"


def test_unsafe_client_request_id_is_replaced(client: TestClient) -> None:
    # Spaces and over-long values could be used to forge log lines; they're never trusted.
    unsafe_ids = ["has space", "x" * 65, "line\tbreak"]

    for unsafe_id in unsafe_ids:
        response = client.get("/health/live", headers={"X-Request-ID": unsafe_id})

        assert response.headers["X-Request-ID"] != unsafe_id
        assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])

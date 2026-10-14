import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import API_CSP, DOCS_CSP, MAX_BODY_BYTES, create_app
from tests.conftest import make_settings

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cache-control": "no-store",
}


def assert_security_headers(headers: Any, csp: str = API_CSP) -> None:
    for name, value in SECURITY_HEADERS.items():
        assert headers[name] == value
    assert headers["content-security-policy"] == csp


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("content_type", [None, "text/plain", "application/x-www-form-urlencoded"])
def test_state_changing_requests_must_be_json(
    client: TestClient, method: str, content_type: str | None
) -> None:
    headers = {"content-type": content_type} if content_type else {}
    response = client.request(method, "/api/auth/logout", content=b"{}", headers=headers)
    assert response.status_code == 415
    assert response.json() == {"detail": "Requests must be sent as JSON."}
    assert_security_headers(response.headers)


def test_json_with_charset_is_accepted(client: TestClient) -> None:
    response = client.post(
        "/api/auth/logout",
        content=b"{}",
        headers={"content-type": "application/json; charset=utf-8"},
    )
    assert response.status_code == 204


def test_get_requests_need_no_content_type(client: TestClient) -> None:
    assert client.get("/api/health").status_code == 200


@pytest.mark.parametrize("origin", ["https://evil.example", "null", "http://127.0.0.1:5174"])
def test_foreign_origin_is_rejected(client: TestClient, origin: str) -> None:
    for method in ("GET", "POST"):
        response = client.request(method, "/api/health", json={}, headers={"origin": origin})
        assert response.status_code == 403
        assert response.json() == {"detail": "This request is not allowed from this origin."}
        assert_security_headers(response.headers)


@pytest.mark.parametrize("origin", ["http://127.0.0.1:5173", "http://localhost:5173/"])
def test_allowed_origin_passes(client: TestClient, origin: str) -> None:
    response = client.post("/api/auth/logout", json={}, headers={"origin": origin})
    assert response.status_code == 204


def test_declared_oversized_body_is_rejected(client: TestClient) -> None:
    body = b'{"x": "' + b"a" * MAX_BODY_BYTES + b'"}'
    response = client.post(
        "/api/auth/login", content=body, headers={"content-type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "The request body is too large."}


def test_streamed_oversized_body_is_rejected(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"email": "'
        yield b"a" * (MAX_BODY_BYTES + 1)
        yield b'"}'

    response = client.post(
        "/api/auth/login", content=chunks(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 413
    assert_security_headers(response.headers)


def test_security_headers_on_success_and_not_found(client: TestClient) -> None:
    assert_security_headers(client.get("/api/health").headers)
    missing = client.get("/api/nope")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Not Found"}
    assert_security_headers(missing.headers)


def test_unhandled_error_is_generic_and_logged_without_message(
    app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    def boom() -> None:
        raise RuntimeError("leaky detail patient@example.com")

    app.add_api_route("/api/boom", boom)
    with TestClient(app) as client, caplog.at_level(logging.ERROR, logger="app.main"):
        response = client.get("/api/boom")
    assert response.status_code == 500
    assert response.json() == {"detail": "Something went wrong. Please try again."}
    assert_security_headers(response.headers)
    assert "RuntimeError" in caplog.text
    assert "leaky detail" not in caplog.text
    assert "patient@example.com" not in response.text


def test_docs_only_in_development() -> None:
    with TestClient(create_app(make_settings(app_env="production"))) as client:
        assert client.get("/api/docs").status_code == 404
        assert client.get("/api/openapi.json").status_code == 404
        assert client.get("/docs").status_code == 404

    with TestClient(create_app(make_settings(app_env="development"))) as client:
        docs = client.get("/api/docs")
        assert docs.status_code == 200
        assert_security_headers(docs.headers, csp=DOCS_CSP)
        schema = client.get("/api/openapi.json")
        assert schema.status_code == 200
        assert_security_headers(schema.headers)
        assert "/api/appointments/current/queue" in schema.json()["paths"]
        assert client.get("/docs/oauth2-redirect").status_code == 404

from collections.abc import Iterator
from datetime import date
from unittest import mock

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError
from supabase_auth.types import AuthResponse

import app.main as main_module
from app.config import Settings
from app.gateway import AuthResult, SupabaseGateway
from app.main import _session_cookies, create_app
from app.schemas import AppointmentRequest
from app.throttle import AuthThrottle
from tests.conftest import make_settings, set_session


def test_module_app_and_factory_without_environment() -> None:
    assert isinstance(main_module.app, FastAPI)
    app = create_app(Settings(_env_file=None))
    assert isinstance(app.state.gateway, SupabaseGateway)
    assert isinstance(app.state.auth_throttle, AuthThrottle)
    assert app.state.auth_throttle.enabled is True
    assert (
        create_app(make_settings(auth_throttle_enabled=False)).state.auth_throttle.enabled is False
    )
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok", "supabase_configured": False}


def test_health_reports_configured(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok", "supabase_configured": True}


def test_unconfigured_backend_answers_503_for_session_calls() -> None:
    with TestClient(create_app(Settings(_env_file=None))) as client:
        set_session(client, "some-access-token")
        response = client.get("/api/auth/me")
        assert response.status_code == 503
        assert response.json() == {
            "detail": "The service is temporarily unavailable. Please try again shortly."
        }
        login = client.post("/api/auth/login", json={"email": "a@example.com", "password": "x"})
        assert login.status_code == 503


def test_error_after_response_started_is_not_masked(app: FastAPI) -> None:
    def broken_stream() -> Iterator[bytes]:
        yield b"partial"
        raise RuntimeError("mid-stream failure")

    app.add_api_route("/api/stream", lambda: StreamingResponse(broken_stream()))
    with TestClient(app) as client, pytest.raises(RuntimeError):
        client.get("/api/stream")


def test_session_cookie_helper_ignores_incomplete_sessions() -> None:
    assert _session_cookies(None, secure=True) == []
    assert _session_cookies(AuthResult("u", "e", "a", None), secure=True) == []
    headers = _session_cookies(AuthResult("u", "e", "a", "r", 60), secure=True)
    assert len(headers) == 2
    assert all("Secure" in h and "HttpOnly" in h for h in headers)


def test_gateway_defensive_branches_for_empty_auth_responses() -> None:
    gateway = SupabaseGateway(make_settings())
    client = mock.MagicMock()
    client.auth.sign_up.return_value = AuthResponse(user=None, session=None)
    client.auth.get_user.return_value = None
    with mock.patch("app.gateway.create_client", return_value=client):
        from app.errors import ServiceUnavailable

        with pytest.raises(ServiceUnavailable):
            gateway.sign_up("a@example.com", "pw-123456")
        assert gateway.get_user("jwt") is None


def test_schema_accepts_date_objects_and_settings_reject_bad_origins() -> None:
    body = AppointmentRequest(doctor_id="dr-a", date=date(2026, 10, 15), time="10:00")
    assert body.date == date(2026, 10, 15)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, allowed_origins=5)

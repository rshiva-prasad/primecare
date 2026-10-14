"""SupabaseGateway against the real supabase-py stack with an in-process transport (no network)."""

import datetime as dt
import json
import logging
from collections.abc import Callable
from typing import Any
from unittest import mock

import httpx
import pytest

from app import gateway as gateway_module
from app.errors import (
    InvalidCredentials,
    InvalidInput,
    NotAuthenticated,
    NotFound,
    PatientDetailsRequired,
    RateLimited,
    RegistrationFailed,
    ServiceUnavailable,
    SlotTaken,
)
from app.gateway import AuthResult, SupabaseGateway, UserInfo
from tests.conftest import make_settings

BASE = "https://example-ref.supabase.co"
KEY = "sb_publishable_test"
USER_JWT = "user.jwt.token"
AUTH_HEADERS = {"x-supabase-api-version": "2024-01-01"}

USER = {
    "id": "11111111-1111-1111-1111-111111111111",
    "aud": "authenticated",
    "email": "pat@example.com",
    "app_metadata": {},
    "user_metadata": {},
    "created_at": "2026-10-13T00:00:00Z",
}
SESSION = {
    "access_token": "new-access",
    "refresh_token": "new-refresh",
    "expires_in": 3600,
    "token_type": "bearer",
    "user": USER,
}

Handler = Callable[[httpx.Request], httpx.Response]


class Recorder:
    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]


def make_gateway(handler: Handler) -> tuple[SupabaseGateway, Recorder]:
    recorder = Recorder(handler)
    return SupabaseGateway(make_settings(), transport=httpx.MockTransport(recorder)), recorder


def reply(status: int = 200, body: Any = None, headers: dict[str, str] | None = None) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if body is None:
            return httpx.Response(status, headers=headers)
        return httpx.Response(status, json=body, headers=headers)

    return handler


def auth_error(status: int, code: str) -> Handler:
    return reply(status, {"code": code, "msg": "upstream detail"}, AUTH_HEADERS)


def pg_error(code: str, message: str = "upstream detail", status: int = 400) -> Handler:
    return reply(status, {"code": code, "message": message, "details": None, "hint": None})


def body_of(request: httpx.Request) -> Any:
    return json.loads(request.content)


# client construction


def test_unconfigured_gateway_is_unavailable() -> None:
    gateway = SupabaseGateway(make_settings(supabase_url=None, supabase_publishable_key=None))
    with pytest.raises(ServiceUnavailable):
        gateway.list_doctors(USER_JWT)
    with pytest.raises(ServiceUnavailable):
        gateway.sign_in("a@example.com", "pw")


def test_fresh_stateless_client_per_call() -> None:
    gateway = SupabaseGateway(make_settings(supabase_timeout_seconds=4))
    clients: list[Any] = []

    def fake_create(url: str, key: str, options: Any) -> Any:
        clients.append((url, key, options))
        client = mock.MagicMock()
        client.rpc.return_value.execute.return_value.data = []
        return client

    with mock.patch.object(gateway_module, "create_client", side_effect=fake_create):
        gateway.current_appointment("jwt-a")
        gateway.current_appointment("jwt-b")

    assert len(clients) == 2
    (url, key, first), (_, _, second) = clients
    assert (url, key) == (BASE, KEY)
    assert first is not second
    for options, jwt in ((first, "jwt-a"), (second, "jwt-b")):
        assert options.persist_session is False
        assert options.auto_refresh_token is False
        assert options.headers["Authorization"] == f"Bearer {jwt}"
        assert options.httpx_client.timeout.read == 4
        assert options.httpx_client.is_closed  # closed after the call


def test_data_calls_send_publishable_key_and_user_jwt() -> None:
    gateway, recorder = make_gateway(reply(200, []))
    gateway.list_doctors(USER_JWT)
    request = recorder.last
    assert request.headers.get_list("apikey") == [KEY]
    assert request.headers.get_list("authorization") == [f"Bearer {USER_JWT}"]


def test_sign_in_never_leaks_into_later_calls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SESSION if request.url.path == "/auth/v1/token" else [])

    gateway, recorder = make_gateway(handler)
    gateway.sign_in("pat@example.com", "pw-123456")  # emits SIGNED_IN inside supabase-py
    assert recorder.last.headers["authorization"] == f"Bearer {KEY}"
    gateway.list_doctors("other-user-jwt")
    assert recorder.last.headers["authorization"] == "Bearer other-user-jwt"
    gateway.sign_in("pat@example.com", "pw-123456")
    assert recorder.last.headers["authorization"] == f"Bearer {KEY}"


def test_transport_failure_is_unavailable(caplog: pytest.LogCaptureFixture) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused to secret-host", request=request)

    gateway, _ = make_gateway(fail)
    with caplog.at_level(logging.WARNING), pytest.raises(ServiceUnavailable):
        gateway.get_patient(USER_JWT, USER["id"])
    with pytest.raises(ServiceUnavailable):
        gateway.sign_in("a@example.com", "pw")
    assert "ConnectError" in caplog.text
    assert "secret-host" not in caplog.text


# auth


def test_sign_in_success() -> None:
    gateway, recorder = make_gateway(reply(200, SESSION))
    result = gateway.sign_in("pat@example.com", "pw-123456")
    assert result == AuthResult(USER["id"], "pat@example.com", "new-access", "new-refresh", 3600)
    request = recorder.last
    assert request.url.path == "/auth/v1/token"
    assert request.url.params["grant_type"] == "password"
    assert request.headers["apikey"] == KEY
    assert body_of(request)["email"] == "pat@example.com"


@pytest.mark.parametrize(
    ("handler", "error"),
    [
        (auth_error(400, "invalid_credentials"), InvalidCredentials),
        (auth_error(400, "email_not_confirmed"), InvalidCredentials),
        (auth_error(400, "validation_failed"), InvalidCredentials),
        (auth_error(429, "over_request_rate_limit"), RateLimited),
        (auth_error(400, "over_email_send_rate_limit"), RateLimited),
        (auth_error(500, "unexpected_failure"), ServiceUnavailable),
        (reply(503), ServiceUnavailable),
        (lambda r: httpx.Response(500, text="<html>oops</html>"), ServiceUnavailable),
    ],
)
def test_sign_in_errors(handler: Handler, error: type[Exception]) -> None:
    gateway, _ = make_gateway(handler)
    with pytest.raises(error):
        gateway.sign_in("pat@example.com", "pw-123456")


def test_sign_in_without_session_is_rejected() -> None:
    gateway, _ = make_gateway(reply(200, USER))
    with pytest.raises(InvalidCredentials):
        gateway.sign_in("pat@example.com", "pw-123456")


def test_sign_up_with_session_and_pending_confirmation() -> None:
    gateway, recorder = make_gateway(reply(200, SESSION))
    assert gateway.sign_up("pat@example.com", "pw-123456").access_token == "new-access"
    assert recorder.last.url.path == "/auth/v1/signup"

    gateway, _ = make_gateway(reply(200, USER))
    assert gateway.sign_up("pat@example.com", "pw-123456") == AuthResult(
        USER["id"], "pat@example.com"
    )


def test_sign_up_unexpected_body_is_unavailable() -> None:
    gateway, _ = make_gateway(reply(200, {"unexpected": True}))
    with pytest.raises(ServiceUnavailable):
        gateway.sign_up("pat@example.com", "pw-123456")


@pytest.mark.parametrize(
    ("handler", "error"),
    [
        (auth_error(422, "user_already_exists"), RegistrationFailed),
        (auth_error(422, "email_exists"), RegistrationFailed),
        (auth_error(400, "email_address_not_authorized"), RegistrationFailed),
        (auth_error(429, "over_email_send_rate_limit"), RateLimited),
        (auth_error(500, "unexpected_failure"), ServiceUnavailable),
        (
            reply(
                422,
                {"code": "weak_password", "msg": "x", "weak_password": {"reasons": ["pwned"]}},
                AUTH_HEADERS,
            ),
            InvalidInput,
        ),
        (reply(422, {"msg": "weak", "weak_password": {"reasons": ["length"]}}), InvalidInput),
    ],
)
def test_sign_up_errors(handler: Handler, error: type[Exception]) -> None:
    gateway, _ = make_gateway(handler)
    with pytest.raises(error) as info:
        gateway.sign_up("pat@example.com", "pw-123456")
    assert "upstream detail" not in str(info.value)


def test_get_user() -> None:
    gateway, recorder = make_gateway(reply(200, USER))
    assert gateway.get_user(USER_JWT) == UserInfo(USER["id"], "pat@example.com")
    assert recorder.last.url.path == "/auth/v1/user"
    assert recorder.last.headers["authorization"] == f"Bearer {USER_JWT}"
    assert recorder.last.headers["apikey"] == KEY


@pytest.mark.parametrize(
    ("handler", "outcome"),
    [
        (auth_error(403, "bad_jwt"), None),
        (auth_error(401, "no_authorization"), None),
        (auth_error(404, "user_not_found"), None),
        (auth_error(429, "over_request_rate_limit"), RateLimited),
        (auth_error(500, "unexpected_failure"), ServiceUnavailable),
    ],
)
def test_get_user_failures(handler: Handler, outcome: type[Exception] | None) -> None:
    gateway, _ = make_gateway(handler)
    if outcome is None:
        assert gateway.get_user(USER_JWT) is None
    else:
        with pytest.raises(outcome):
            gateway.get_user(USER_JWT)


def test_refresh() -> None:
    gateway, recorder = make_gateway(reply(200, SESSION))
    result = gateway.refresh("old-refresh")
    assert result is not None
    assert (result.access_token, result.refresh_token) == ("new-access", "new-refresh")
    assert recorder.last.url.params["grant_type"] == "refresh_token"
    assert body_of(recorder.last) == {"refresh_token": "old-refresh"}


@pytest.mark.parametrize(
    ("handler", "outcome"),
    [
        (auth_error(400, "refresh_token_not_found"), None),
        (auth_error(400, "refresh_token_already_used"), None),
        (reply(200, USER), None),  # no session in the body
        (auth_error(429, "over_request_rate_limit"), RateLimited),
        (reply(502), ServiceUnavailable),
    ],
)
def test_refresh_failures(handler: Handler, outcome: type[Exception] | None) -> None:
    gateway, _ = make_gateway(handler)
    if outcome is None:
        assert gateway.refresh("old-refresh") is None
    else:
        with pytest.raises(outcome):
            gateway.refresh("old-refresh")


def test_sign_out_uses_user_jwt_and_local_scope() -> None:
    gateway, recorder = make_gateway(reply(204))
    assert gateway.sign_out(USER_JWT) is True
    request = recorder.last
    assert (request.method, request.url.path) == ("POST", "/auth/v1/logout")
    assert request.url.params["scope"] == "local"
    assert request.headers["authorization"] == f"Bearer {USER_JWT}"
    assert request.headers["apikey"] == KEY


@pytest.mark.parametrize(
    "handler", [auth_error(401, "bad_jwt"), auth_error(403, "session_not_found"), reply(500)]
)
def test_sign_out_never_raises_and_reports_nothing_revoked(handler: Handler) -> None:
    gateway, _ = make_gateway(handler)
    assert gateway.sign_out(USER_JWT) is False
    assert SupabaseGateway(make_settings(supabase_url=None)).sign_out(USER_JWT) is False


# data


def test_get_patient() -> None:
    row = {"first_name": "Pat", "last_name": "Lee", "mobile": "0400000000", "email": "p@e.com"}
    gateway, recorder = make_gateway(reply(200, [row]))
    assert gateway.get_patient(USER_JWT, USER["id"]) == row
    params = recorder.last.url.params
    assert recorder.last.url.path == "/rest/v1/patients"
    assert params["select"] == "first_name,last_name,mobile,email"
    assert params["id"] == f"eq.{USER['id']}"
    assert params["limit"] == "1"

    gateway, _ = make_gateway(reply(200, []))
    assert gateway.get_patient(USER_JWT, USER["id"]) is None


def test_upsert_patient() -> None:
    data = {"first_name": "Pat", "last_name": "Lee", "mobile": "0400000000", "email": "p@e.com"}
    gateway, recorder = make_gateway(reply(201, [{**data, "id": USER["id"]}]))
    assert (
        gateway.upsert_patient(USER_JWT, USER["id"], {**data, "id": "spoofed"})["id"] == USER["id"]
    )
    request = recorder.last
    assert request.method == "POST"
    assert request.url.params["on_conflict"] == "id"
    assert "resolution=merge-duplicates" in request.headers["prefer"]
    assert "return=representation" in request.headers["prefer"]
    assert body_of(request) == {**data, "id": USER["id"]}

    gateway, _ = make_gateway(reply(201, []))
    with pytest.raises(ServiceUnavailable):
        gateway.upsert_patient(USER_JWT, USER["id"], data)


def test_clinic_today_reads_the_scalar_rpc_result() -> None:
    # PostgREST returns a scalar function result as a bare JSON string, not a row.
    gateway, recorder = make_gateway(reply(200, "2026-10-14"))
    assert gateway.clinic_today(USER_JWT) == dt.date(2026, 10, 14)
    request = recorder.last
    assert (request.method, request.url.path) == ("POST", "/rest/v1/rpc/clinic_today")
    assert body_of(request) == {}
    assert request.headers["authorization"] == f"Bearer {USER_JWT}"
    assert request.headers["apikey"] == KEY


@pytest.mark.parametrize(
    ("handler", "error"),
    [
        (reply(200, ["2026-10-14"]), ServiceUnavailable),
        (reply(200, {"clinic_today": "2026-10-14"}), ServiceUnavailable),
        (reply(200, "14/10/2026"), ServiceUnavailable),
        (reply(200, None), ServiceUnavailable),
        (pg_error("PGRST301", status=401), NotAuthenticated),
        (pg_error("42501", status=403), NotAuthenticated),
        (lambda r: httpx.Response(502, text="Bad gateway"), ServiceUnavailable),
    ],
)
def test_clinic_today_errors(
    handler: Handler, error: type[Exception], caplog: pytest.LogCaptureFixture
) -> None:
    gateway, _ = make_gateway(handler)
    with caplog.at_level(logging.WARNING), pytest.raises(error):
        gateway.clinic_today(USER_JWT)
    assert "14/10/2026" not in caplog.text


def test_list_doctors() -> None:
    rows = [{"id": "dr-a", "name": "A", "specialty": "GP"}]
    gateway, recorder = make_gateway(reply(200, rows))
    assert gateway.list_doctors(USER_JWT) == rows
    params = recorder.last.url.params
    assert params["active"] == "eq.true"
    assert params["order"] == "name.asc"


def test_available_slots() -> None:
    rows = [{"slot_time": "09:00:00", "label": "09:00 AM"}]
    gateway, recorder = make_gateway(reply(200, rows))
    assert gateway.available_slots(USER_JWT, "dr-a", dt.date(2026, 10, 15)) == rows
    assert recorder.last.url.path == "/rest/v1/rpc/available_slots"
    assert body_of(recorder.last) == {"p_doctor_id": "dr-a", "p_date": "2026-10-15"}


BOOKED = {
    "id": "appt-1",
    "patient_id": USER["id"],
    "doctor_id": "dr-a",
    "appointment_date": "2026-10-15",
    "slot_time": "10:00:00",
    "token_number": 24,
    "token": "PC-024",
    "status": "waiting",
    "created_at": "2026-10-13T00:00:00+00:00",
}
CURRENT = {**BOOKED, "slot_label": "10:00 AM", "doctor_name": "Dr. A", "doctor_specialty": "GP"}


def routed(routes: dict[str, Handler]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        return routes[request.url.path.rsplit("/", 1)[-1]](request)

    return handler


@pytest.mark.parametrize("booked_shape", [BOOKED, [BOOKED]])
def test_book_appointment_returns_enriched_row(booked_shape: Any) -> None:
    gateway, recorder = make_gateway(
        routed(
            {
                "book_appointment": reply(200, booked_shape),
                "current_appointment": reply(200, [CURRENT]),
            }
        )
    )
    assert gateway.book_appointment(USER_JWT, "dr-a", dt.date(2026, 10, 15), "10:00") == CURRENT
    book_request = recorder.requests[0]
    assert body_of(book_request) == {
        "p_doctor_id": "dr-a",
        "p_date": "2026-10-15",
        "p_slot_time": "10:00",
    }
    assert book_request.headers["authorization"] == f"Bearer {USER_JWT}"


@pytest.mark.parametrize(
    "current_handler",
    [reply(200, [{**CURRENT, "id": "other"}]), reply(200, []), pg_error("XX000", status=500)],
)
def test_book_appointment_falls_back_to_booked_row(current_handler: Handler) -> None:
    gateway, _ = make_gateway(
        routed({"book_appointment": reply(200, BOOKED), "current_appointment": current_handler})
    )
    assert gateway.book_appointment(USER_JWT, "dr-a", dt.date(2026, 10, 15), "10:00") == BOOKED


def test_book_appointment_without_row_is_unavailable() -> None:
    gateway, _ = make_gateway(reply(200, None))
    with pytest.raises(ServiceUnavailable):
        gateway.book_appointment(USER_JWT, "dr-a", dt.date(2026, 10, 15), "10:00")


@pytest.mark.parametrize(
    ("handler", "error"),
    [
        (pg_error("PC401"), NotAuthenticated),
        (pg_error("PC404"), NotFound),
        (pg_error("PC409"), SlotTaken),
        (pg_error("PC412"), PatientDetailsRequired),
        (pg_error("23505"), SlotTaken),
        (pg_error("PGRST301", status=401), NotAuthenticated),
        (pg_error("PGRST302", status=401), NotAuthenticated),
        (pg_error("PGRST303", status=401), NotAuthenticated),
        (pg_error("42501", status=403), NotAuthenticated),
        (pg_error("23514"), ServiceUnavailable),
        (lambda r: httpx.Response(502, text="Bad gateway"), ServiceUnavailable),
    ],
)
def test_data_error_mapping(handler: Handler, error: type[Exception]) -> None:
    gateway, _ = make_gateway(handler)
    with pytest.raises(error) as info:
        gateway.book_appointment(USER_JWT, "dr-a", dt.date(2026, 10, 15), "10:00")
    assert "upstream detail" not in str(info.value)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "Please choose a date within the next 90 days.",
            "Please choose a date within the next 90 days.",
        ),
        ("You already have an upcoming appointment.", "You already have an upcoming appointment."),
        ("", "Please check your booking details and try again."),
        ("x" * 201, "Please check your booking details and try again."),
    ],
)
def test_pc400_message_is_passed_through_when_safe(message: str, expected: str) -> None:
    gateway, _ = make_gateway(pg_error("PC400", message))
    with pytest.raises(InvalidInput) as info:
        gateway.book_appointment(USER_JWT, "dr-a", dt.date(2026, 10, 15), "10:00")
    assert info.value.message == expected


def test_current_appointment() -> None:
    gateway, recorder = make_gateway(reply(200, [CURRENT]))
    assert gateway.current_appointment(USER_JWT) == CURRENT
    assert recorder.last.url.path == "/rest/v1/rpc/current_appointment"
    gateway, _ = make_gateway(reply(200, []))
    assert gateway.current_appointment(USER_JWT) is None


def test_queue_snapshot() -> None:
    snapshot = {"token": "PC-024", "queue_position": 1, "total_in_queue": 1}
    gateway, recorder = make_gateway(reply(200, [snapshot]))
    assert gateway.queue_snapshot(USER_JWT, "appt-1") == snapshot
    assert body_of(recorder.last) == {"p_appointment_id": "appt-1"}
    gateway, _ = make_gateway(reply(200, []))
    with pytest.raises(NotFound):
        gateway.queue_snapshot(USER_JWT, "appt-1")


def test_rows_helpers() -> None:
    assert gateway_module._rows({"a": 1}) == [{"a": 1}]
    assert gateway_module._rows([{"a": 1}, "junk", 3]) == [{"a": 1}]
    assert gateway_module._rows("text") == []
    assert gateway_module._first_row([]) is None

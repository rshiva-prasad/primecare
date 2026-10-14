"""Supabase access. The only module that imports supabase.

supabase-py clients hold auth state (signing in switches a client's Authorization header to that
user), so a fresh client is built for every call and never shared between requests or users.
Data calls carry the publishable key as `apikey` and the user's JWT as the bearer token so that
Row Level Security applies.
"""

import datetime as dt
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from postgrest import APIError
from pydantic import ValidationError
from supabase import Client, ClientOptions, SupabaseException, create_client
from supabase_auth.errors import AuthError, AuthWeakPasswordError
from supabase_auth.types import Session

from app.config import Settings
from app.errors import (
    AppError,
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

logger = logging.getLogger(__name__)

Row = dict[str, Any]

PATIENT_COLUMNS = "first_name,last_name,mobile,email"
WEAK_CREDENTIAL_MESSAGE = "Please choose a stronger password that is harder to guess."
_PC400_FALLBACK = "Please check your booking details and try again."
_RATE_LIMIT_CODES = frozenset(
    {"over_request_rate_limit", "over_email_send_rate_limit", "over_sms_send_rate_limit"}
)
_DATA_ERRORS: dict[str, type[AppError]] = {
    "PC401": NotAuthenticated,
    "PC404": NotFound,
    "PC409": SlotTaken,
    "PC412": PatientDetailsRequired,
    "23505": SlotTaken,
    "PGRST301": NotAuthenticated,
    "PGRST302": NotAuthenticated,
    "PGRST303": NotAuthenticated,
    "42501": NotAuthenticated,
}


@dataclass(frozen=True)
class UserInfo:
    id: str
    email: str


@dataclass(frozen=True)
class AuthResult:
    user_id: str
    email: str
    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None


class Gateway(Protocol):
    def sign_up(self, email: str, password: str) -> AuthResult: ...
    def sign_in(self, email: str, password: str) -> AuthResult: ...
    def get_user(self, access_token: str) -> UserInfo | None: ...
    def refresh(self, refresh_token: str) -> AuthResult | None: ...
    def sign_out(self, access_token: str) -> bool: ...
    def get_patient(self, token: str, user_id: str) -> Row | None: ...
    def upsert_patient(self, token: str, user_id: str, data: Row) -> Row: ...
    def clinic_today(self, token: str) -> dt.date: ...
    def list_doctors(self, token: str) -> list[Row]: ...
    def available_slots(self, token: str, doctor_id: str, date: dt.date) -> list[Row]: ...
    def book_appointment(self, token: str, doctor_id: str, date: dt.date, time: str) -> Row: ...
    def current_appointment(self, token: str) -> Row | None: ...
    def queue_snapshot(self, token: str, appointment_id: str) -> Row: ...


class _Executable(Protocol):
    def execute(self) -> Any: ...


def _rows(data: Any) -> list[Row]:
    """RPC/table data may be a list of rows or, for functions returning a composite, one object."""
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _first_row(data: Any) -> Row | None:
    rows = _rows(data)
    return rows[0] if rows else None


def _map_data_error(exc: APIError) -> AppError:
    code = str(exc.code or "")
    if code == "PC400":
        message = (exc.message or "").strip()
        return InvalidInput(message if 0 < len(message) <= 200 else _PC400_FALLBACK)
    error_class = _DATA_ERRORS.get(code)
    if error_class is not None:
        return error_class()
    logger.warning("Supabase data call failed (code=%s)", code or "unknown")
    return ServiceUnavailable()


def _execute(query: _Executable) -> Any:
    try:
        return query.execute().data
    except APIError as exc:
        raise _map_data_error(exc) from None


def _auth_status(exc: AuthError) -> int | None:
    status = getattr(exc, "status", None)
    return status if isinstance(status, int) else None


def _is_rate_limited(exc: AuthError) -> bool:
    return exc.code in _RATE_LIMIT_CODES or _auth_status(exc) == 429


def _is_client_rejection(exc: AuthError) -> bool:
    status = _auth_status(exc)
    return status is not None and 400 <= status < 500


def _auth_unavailable(exc: AuthError) -> ServiceUnavailable:
    logger.warning("Supabase auth call failed (%s, code=%s)", type(exc).__name__, exc.code)
    return ServiceUnavailable()


def _map_sign_in_error(exc: AuthError) -> AppError:
    if _is_rate_limited(exc):
        return RateLimited()
    if _is_client_rejection(exc):
        # invalid_credentials, email_not_confirmed, user_banned, ...: never say which.
        return InvalidCredentials()
    return _auth_unavailable(exc)


def _map_sign_up_error(exc: AuthError) -> AppError:
    if _is_rate_limited(exc):
        return RateLimited()
    if isinstance(exc, AuthWeakPasswordError) or exc.code == "weak_password":
        return InvalidInput(WEAK_CREDENTIAL_MESSAGE)
    if _is_client_rejection(exc):
        return RegistrationFailed()
    return _auth_unavailable(exc)


def _session_result(session: Session) -> AuthResult:
    return AuthResult(
        user_id=session.user.id,
        email=session.user.email or "",
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in,
    )


class SupabaseGateway:
    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None) -> None:
        self._url = settings.supabase_url
        self._key = settings.supabase_publishable_key
        self._timeout = settings.supabase_timeout_seconds
        self._transport = transport  # tests inject httpx.MockTransport; never set in the app

    @contextmanager
    def _client(self, access_token: str | None = None) -> Iterator[Client]:
        if not self._url or self._key is None:
            raise ServiceUnavailable()
        with httpx.Client(timeout=self._timeout, transport=self._transport) as http:
            options = ClientOptions(
                persist_session=False, auto_refresh_token=False, httpx_client=http
            )
            if access_token:
                options.headers["Authorization"] = f"Bearer {access_token}"
            try:
                yield create_client(self._url, self._key.get_secret_value(), options)
            except (httpx.HTTPError, SupabaseException, ValidationError) as exc:
                logger.warning("Supabase request failed (%s)", type(exc).__name__)
                raise ServiceUnavailable() from None

    # Auth

    def sign_up(self, email: str, password: str) -> AuthResult:
        with self._client() as client:
            try:
                response = client.auth.sign_up({"email": email, "password": password})
            except AuthError as exc:
                raise _map_sign_up_error(exc) from None
        if response.session is not None:
            return _session_result(response.session)
        if response.user is None:
            raise ServiceUnavailable()
        # Email confirmation pending (or an obfuscated existing user): no session yet.
        return AuthResult(user_id=response.user.id, email=response.user.email or email)

    def sign_in(self, email: str, password: str) -> AuthResult:
        with self._client() as client:
            try:
                response = client.auth.sign_in_with_password({"email": email, "password": password})
            except AuthError as exc:
                raise _map_sign_in_error(exc) from None
        if response.session is None:
            raise InvalidCredentials()
        return _session_result(response.session)

    def get_user(self, access_token: str) -> UserInfo | None:
        with self._client() as client:
            try:
                response = client.auth.get_user(access_token)
            except AuthError as exc:
                if _is_rate_limited(exc):
                    raise RateLimited() from None
                if _is_client_rejection(exc):
                    return None
                raise _auth_unavailable(exc) from None
        if response is None:
            return None
        return UserInfo(id=response.user.id, email=response.user.email or "")

    def refresh(self, refresh_token: str) -> AuthResult | None:
        with self._client() as client:
            try:
                response = client.auth.refresh_session(refresh_token)
            except AuthError as exc:
                if _is_rate_limited(exc):
                    raise RateLimited() from None
                if _is_client_rejection(exc):
                    return None
                raise _auth_unavailable(exc) from None
        return None if response.session is None else _session_result(response.session)

    def sign_out(self, access_token: str) -> bool:
        """Revoke the session server-side (scope 'local'). Best effort: never raises.

        False means nothing was revoked (typically an expired access token), so the caller can
        retry with a freshly refreshed one.
        """
        try:
            with self._client() as client:
                client.auth.admin.sign_out(access_token, "local")
        except Exception as exc:  # logout must always succeed locally
            logger.info("Supabase sign-out skipped (%s)", type(exc).__name__)
            return False
        return True

    # Data (RLS applies: every call uses the caller's JWT)

    def get_patient(self, token: str, user_id: str) -> Row | None:
        with self._client(token) as client:
            query = client.table("patients").select(PATIENT_COLUMNS).eq("id", user_id).limit(1)
            return _first_row(_execute(query))

    def upsert_patient(self, token: str, user_id: str, data: Row) -> Row:
        with self._client(token) as client:
            query = client.table("patients").upsert({**data, "id": user_id}, on_conflict="id")
            row = _first_row(_execute(query))
        if row is None:
            raise ServiceUnavailable()
        return row

    def clinic_today(self, token: str) -> dt.date:
        """The clinic's date per SQL public.clinic_today(), the only place "today" is decided."""
        with self._client(token) as client:
            data = _execute(client.rpc("clinic_today", {}))
        # A scalar function result is a bare JSON string ("2026-10-14"), not a row: no _rows().
        if isinstance(data, str):
            try:
                return dt.date.fromisoformat(data)
            except ValueError:
                pass
        logger.warning("Supabase clinic_today returned an unexpected value")
        raise ServiceUnavailable()

    def list_doctors(self, token: str) -> list[Row]:
        with self._client(token) as client:
            query = (
                client.table("doctors").select("id,name,specialty").eq("active", True).order("name")
            )
            return _rows(_execute(query))

    def available_slots(self, token: str, doctor_id: str, date: dt.date) -> list[Row]:
        params = {"p_doctor_id": doctor_id, "p_date": date.isoformat()}
        with self._client(token) as client:
            return _rows(_execute(client.rpc("available_slots", params)))

    def book_appointment(self, token: str, doctor_id: str, date: dt.date, time: str) -> Row:
        params = {"p_doctor_id": doctor_id, "p_date": date.isoformat(), "p_slot_time": time}
        with self._client(token) as client:
            booked = _first_row(_execute(client.rpc("book_appointment", params)))
            if booked is None:
                raise ServiceUnavailable()
            # Re-read through current_appointment() for doctor and slot labels. The booking has
            # already succeeded, so a failure here must not turn into an error response.
            try:
                current = _first_row(_execute(client.rpc("current_appointment", {})))
            except (AppError, httpx.HTTPError, ValidationError):
                current = None
        if current is not None and current.get("id") == booked.get("id"):
            return current
        return booked

    def current_appointment(self, token: str) -> Row | None:
        with self._client(token) as client:
            return _first_row(_execute(client.rpc("current_appointment", {})))

    def queue_snapshot(self, token: str, appointment_id: str) -> Row:
        with self._client(token) as client:
            params = {"p_appointment_id": appointment_id}
            row = _first_row(_execute(client.rpc("queue_snapshot", params)))
        if row is None:
            raise NotFound()
        return row

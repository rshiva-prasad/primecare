import logging
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.cookies import REFRESH_MAX_AGE
from app.deps import get_auth_throttle, get_gateway
from app.errors import RateLimited, ServiceUnavailable
from app.main import create_app
from app.throttle import AuthThrottle
from tests.conftest import make_settings, set_session
from tests.fakes import FakeGateway

CREDS = {"email": "New.Patient@Example.com", "password": "correct-horse"}


def set_cookie_headers(response: Any) -> list[str]:
    return list(response.headers.get_list("set-cookie"))


def cookie_named(response: Any, name: str) -> str:
    return next(h for h in set_cookie_headers(response) if h.startswith(f"{name}="))


# register


def test_register_starts_session(client: TestClient, fake: FakeGateway) -> None:
    response = client.post("/api/auth/register", json=CREDS)
    assert response.status_code == 201
    body = response.json()
    assert body == {
        "user": {
            "id": fake.users["new.patient@example.com"].id,
            "email": "new.patient@example.com",
        },
        "session_started": True,
    }
    access = cookie_named(response, "pc_access")
    refresh = cookie_named(response, "pc_refresh")
    for header in (access, refresh):
        assert "HttpOnly" in header
        assert "Path=/api" in header
        assert "SameSite=lax" in header
        assert "Secure" not in header  # COOKIE_SECURE=false in this test config
    assert "Max-Age=3600" in access
    assert f"Max-Age={REFRESH_MAX_AGE}" in refresh
    assert client.get("/api/auth/me").json()["user"]["email"] == "new.patient@example.com"


def test_register_needing_email_confirmation(client: TestClient, fake: FakeGateway) -> None:
    fake.confirm_email = True
    response = client.post("/api/auth/register", json=CREDS)
    assert response.status_code == 202
    assert response.json() == {
        "user": None,
        "session_started": False,
        "detail": "Check your email to confirm your account, then log in.",
    }
    assert set_cookie_headers(response) == []


def test_register_existing_account(client: TestClient, fake: FakeGateway) -> None:
    fake.add_user("new.patient@example.com")
    response = client.post("/api/auth/register", json=CREDS)
    assert response.status_code == 400
    assert response.json() == {
        "detail": "Unable to create an account with those details. "
        "If you already have an account, please log in."
    }


def test_register_validation(client: TestClient) -> None:
    response = client.post("/api/auth/register", json={"email": "nope", "password": "short"})
    assert response.status_code == 422
    assert response.json() == {
        "detail": "Please correct the highlighted fields.",
        "fields": {
            "email": "Please enter a valid email address.",
            "password": "Password must be at least 8 characters.",
        },
    }
    assert "short" not in response.text


def test_register_rate_limited(client: TestClient, fake: FakeGateway) -> None:
    fake.failures["sign_up"] = RateLimited()
    response = client.post("/api/auth/register", json=CREDS)
    assert response.status_code == 429
    assert response.json() == {"detail": "Too many attempts. Please wait a moment and try again."}


def test_secure_cookies_when_configured(fake: FakeGateway) -> None:
    app = create_app(make_settings(cookie_secure=True))
    from app.deps import get_gateway

    app.dependency_overrides[get_gateway] = lambda: fake
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/api/auth/register", json=CREDS)
        assert response.status_code == 201
        assert all("Secure" in h for h in set_cookie_headers(response))
        logout = client.post("/api/auth/logout", json={})
        assert all("Secure" in h for h in set_cookie_headers(logout))


# login


def test_login_success(client: TestClient, fake: FakeGateway) -> None:
    user = fake.add_user("pat@example.com", "s3cret-pass")
    response = client.post(
        "/api/auth/login", json={"email": " PAT@example.com ", "password": "s3cret-pass"}
    )
    assert response.status_code == 200
    assert response.json() == {"user": {"id": user.id, "email": "pat@example.com"}}
    assert fake.called("sign_in") == [("pat@example.com",)]
    assert cookie_named(response, "pc_access").startswith("pc_access=access-")


@pytest.mark.parametrize("password", ["wrong-pass", "s3cret-pass"])
def test_login_any_credential_failure_is_generic(
    client: TestClient, fake: FakeGateway, password: str
) -> None:
    fake.add_user("someone-else@example.com", "s3cret-pass")
    response = client.post(
        "/api/auth/login", json={"email": "pat@example.com", "password": password}
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password."}


def test_login_rate_limited(client: TestClient, fake: FakeGateway) -> None:
    fake.failures["sign_in"] = RateLimited()
    response = client.post("/api/auth/login", json={"email": "a@example.com", "password": "x"})
    assert response.status_code == 429
    assert response.json() == {"detail": "Too many attempts. Please wait a moment and try again."}


def test_login_service_unavailable(client: TestClient, fake: FakeGateway) -> None:
    fake.failures["sign_in"] = ServiceUnavailable()
    response = client.post("/api/auth/login", json={"email": "a@example.com", "password": "x"})
    assert response.status_code == 503
    assert response.json() == {
        "detail": "The service is temporarily unavailable. Please try again shortly."
    }


def test_login_validation_and_bad_json(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={})
    assert response.status_code == 422
    assert response.json()["fields"] == {
        "email": "Email is required.",
        "password": "Password is required.",
    }
    broken = client.post(
        "/api/auth/login", content=b'{"email": ', headers={"content-type": "application/json"}
    )
    assert broken.status_code == 422
    assert broken.json()["fields"] == {"body": "The request body must be valid JSON."}
    not_object = client.post("/api/auth/login", json=["a"])
    assert not_object.status_code == 422
    assert not_object.json()["fields"] == {"body": "The request body must be a JSON object."}


def test_session_endpoint_returning_tokens_without_refresh_is_unavailable(
    client: TestClient, fake: FakeGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.gateway import AuthResult

    monkeypatch.setattr(fake, "sign_in", lambda e, p: AuthResult("u1", e, "access-x", None, 60))
    response = client.post("/api/auth/login", json={"email": "a@example.com", "password": "x"})
    assert response.status_code == 503
    assert set_cookie_headers(response) == []


# me / current user dependency


def test_me_requires_login(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Please log in to continue."}


def test_me_with_valid_session(client: TestClient, login: Callable[..., Any]) -> None:
    session = login()
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == {"user": {"id": session.user_id, "email": "pat@example.com"}}
    assert set_cookie_headers(response) == []


def test_expired_access_token_is_refreshed_transparently(
    client: TestClient, fake: FakeGateway, login: Callable[..., Any]
) -> None:
    old = login()
    fake.expire(old.access_token)
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    new_access = cookie_named(response, "pc_access")
    assert new_access.startswith("pc_access=access-")
    assert old.access_token not in new_access
    assert cookie_named(response, "pc_refresh").startswith("pc_refresh=refresh-")
    assert fake.called("refresh") == [(old.refresh_token,)]
    # The rotated cookies were stored by the client, so the next call needs no refresh.
    assert client.get("/api/auth/me").status_code == 200
    assert len(fake.called("refresh")) == 1


def test_missing_access_cookie_with_refresh_cookie_refreshes(
    client: TestClient, fake: FakeGateway, login: Callable[..., Any]
) -> None:
    session = login()
    set_session(client, None, session.refresh_token)
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert cookie_named(response, "pc_access")
    assert fake.called("get_user") == []


def test_refresh_failure_clears_cookies(client: TestClient, fake: FakeGateway) -> None:
    set_session(client, "access-unknown", "refresh-unknown")
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Your session has expired. Please log in again."}
    for name in ("pc_access", "pc_refresh"):
        cleared = cookie_named(response, name)
        assert "Max-Age=0" in cleared
        assert "Path=/api" in cleared


def test_invalid_access_without_refresh_cookie_is_expired(client: TestClient) -> None:
    set_session(client, "access-unknown")
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Your session has expired. Please log in again."}


def test_refreshed_cookies_survive_an_error_response(
    client: TestClient, fake: FakeGateway, login: Callable[..., Any]
) -> None:
    old = login()
    fake.expire(old.access_token)
    fake.failures["list_doctors"] = ServiceUnavailable()
    response = client.get("/api/doctors")
    assert response.status_code == 503
    assert cookie_named(response, "pc_access").startswith("pc_access=access-")
    assert cookie_named(response, "pc_refresh").startswith("pc_refresh=refresh-")


def test_upstream_outage_during_auth_check_keeps_cookies(
    client: TestClient, fake: FakeGateway, login: Callable[..., Any]
) -> None:
    login()
    fake.failures["get_user"] = ServiceUnavailable()
    response = client.get("/api/auth/me")
    assert response.status_code == 503
    assert set_cookie_headers(response) == []


def test_data_call_rejecting_token_clears_session(
    client: TestClient, fake: FakeGateway, login: Callable[..., Any]
) -> None:
    from app.errors import NotAuthenticated

    login()
    fake.failures["get_patient"] = NotAuthenticated()
    response = client.get("/api/patients/me")
    assert response.status_code == 401
    assert "Max-Age=0" in cookie_named(response, "pc_access")


# logout


def test_logout_revokes_and_clears(
    client: TestClient, fake: FakeGateway, login: Callable[..., Any]
) -> None:
    session = login()
    response = client.post("/api/auth/logout", json={})
    assert response.status_code == 204
    assert response.content == b""
    assert fake.called("sign_out") == [(session.access_token,)]
    assert "Max-Age=0" in cookie_named(response, "pc_access")
    assert "Max-Age=0" in cookie_named(response, "pc_refresh")
    assert client.get("/api/auth/me").status_code == 401


def test_logout_without_session(client: TestClient, fake: FakeGateway) -> None:
    response = client.post("/api/auth/logout", json={})
    assert response.status_code == 204
    assert fake.called("sign_out") == []


def test_logout_with_only_refresh_cookie_revokes_via_refresh(
    client: TestClient, fake: FakeGateway, login: Callable[..., Any]
) -> None:
    session = login()
    set_session(client, None, session.refresh_token)
    response = client.post("/api/auth/logout", json={})
    assert response.status_code == 204
    assert fake.called("refresh") == [(session.refresh_token,)]
    assert len(fake.called("sign_out")) == 1
    assert session.refresh_token not in fake.refresh_tokens


def test_logout_never_fails(
    client: TestClient, fake: FakeGateway, login: Callable[..., Any]
) -> None:
    session = login()
    set_session(client, None, session.refresh_token)
    fake.failures["refresh"] = ServiceUnavailable()
    response = client.post("/api/auth/logout", json={})
    assert response.status_code == 204
    assert "Max-Age=0" in cookie_named(response, "pc_refresh")
    assert fake.called("sign_out") == []


def test_logout_with_expired_access_cookie_still_revokes_session(
    client: TestClient, fake: FakeGateway, login: Callable[..., Any]
) -> None:
    session = login()
    fake.expire(session.access_token)  # the browser still sends the expired pc_access
    response = client.post("/api/auth/logout", json={})
    assert response.status_code == 204
    assert "Max-Age=0" in cookie_named(response, "pc_access")
    assert "Max-Age=0" in cookie_named(response, "pc_refresh")
    assert fake.called("refresh") == [(session.refresh_token,)]
    (first,), (second,) = fake.called("sign_out")
    assert first == session.access_token
    assert second != session.access_token
    assert not any(uid == session.user_id for uid in fake.refresh_tokens.values())
    assert not any(uid == session.user_id for uid in fake.access.values())


def test_logout_with_valid_access_does_not_refresh(
    client: TestClient, fake: FakeGateway, login: Callable[..., Any]
) -> None:
    session = login()
    assert client.post("/api/auth/logout", json={}).status_code == 204
    assert fake.called("refresh") == []
    assert session.refresh_token not in fake.refresh_tokens


@pytest.mark.parametrize("with_refresh", [True, False])
def test_logout_with_rejected_access_never_fails(
    client: TestClient, fake: FakeGateway, with_refresh: bool
) -> None:
    set_session(client, "access-unknown", "refresh-unknown" if with_refresh else None)
    response = client.post("/api/auth/logout", json={})
    assert response.status_code == 204
    assert "Max-Age=0" in cookie_named(response, "pc_access")
    assert fake.called("sign_out") == [("access-unknown",)]
    assert fake.called("refresh") == ([("refresh-unknown",)] if with_refresh else [])


# login/register throttle

THROTTLED = {"detail": "Too many attempts. Please wait a moment and try again."}


def attempt_login(
    client: TestClient,
    email: str = "pat@example.com",
    password: str = "x",
    headers: dict[str, str] | None = None,
) -> Any:
    return client.post(
        "/api/auth/login", json={"email": email, "password": password}, headers=headers
    )


def test_sixth_failed_login_for_an_account_is_throttled_before_supabase(
    client: TestClient, fake: FakeGateway
) -> None:
    fake.add_user("pat@example.com", "s3cret-pass")
    for _ in range(5):
        assert attempt_login(client, "pat@example.com", "wrong-pass").status_code == 401
    response = attempt_login(client, " PAT@Example.com ", "s3cret-pass")  # even the right password
    assert response.status_code == 429
    assert response.json() == THROTTLED
    assert set_cookie_headers(response) == []
    assert len(fake.called("sign_in")) == 5  # the throttled attempt never reached the gateway


def test_successful_login_resets_the_failure_count(client: TestClient, fake: FakeGateway) -> None:
    fake.add_user("pat@example.com", "s3cret-pass")
    for _ in range(4):
        attempt_login(client, password="wrong-pass")
    assert attempt_login(client, password="s3cret-pass").status_code == 200
    for _ in range(5):
        assert attempt_login(client, password="wrong-pass").status_code == 401
    assert attempt_login(client, password="wrong-pass").status_code == 429


def test_account_limit_is_per_email_and_per_client_ip(
    app: Any, client: TestClient, fake: FakeGateway
) -> None:
    fake.add_user("pat@example.com", "s3cret-pass")
    fake.add_user("other@example.com", "s3cret-pass")
    for _ in range(5):
        attempt_login(client, password="wrong-pass")
    assert attempt_login(client, password="s3cret-pass").status_code == 429
    assert attempt_login(client, "other@example.com", "s3cret-pass").status_code == 200
    with TestClient(app, client=("203.0.113.7", 50000)) as elsewhere:
        assert attempt_login(elsewhere, password="s3cret-pass").status_code == 200


def test_upstream_errors_do_not_count_as_failed_logins(
    client: TestClient, fake: FakeGateway
) -> None:
    fake.add_user("pat@example.com", "s3cret-pass")
    fake.failures["sign_in"] = ServiceUnavailable()
    for _ in range(6):
        assert attempt_login(client).status_code == 503
    del fake.failures["sign_in"]
    assert attempt_login(client, password="s3cret-pass").status_code == 200


def test_client_ip_cap_covers_login_and_register(app: Any, client: TestClient) -> None:
    for n in range(10):
        creds = {"email": f"new{n}@example.com", "password": "correct-horse"}
        assert client.post("/api/auth/register", json=creds).status_code == 201
        assert attempt_login(client, f"nobody{n}@example.com").status_code == 401
    assert client.post("/api/auth/register", json=CREDS).status_code == 429
    assert attempt_login(client, "new0@example.com", "correct-horse").json() == THROTTLED
    with TestClient(app, client=("203.0.113.7", 50000)) as elsewhere:
        assert elsewhere.post("/api/auth/register", json=CREDS).status_code == 201


def test_client_ip_ignores_forwarded_headers(client: TestClient) -> None:
    for n in range(20):
        attempt_login(client, f"nobody{n}@example.com")
    response = client.post(
        "/api/auth/login",
        json={"email": "a@example.com", "password": "x"},
        headers={
            "X-Forwarded-For": "198.51.100.9",
            "X-Real-IP": "198.51.100.9",
            "X-Vercel-Forwarded-For": "198.51.100.9",  # untrusted while the setting is unset
        },
    )
    assert response.status_code == 429


# TRUSTED_CLIENT_IP_HEADER

VERCEL_IP_HEADER = "x-vercel-forwarded-for"
PEER = "testclient"  # TestClient's socket peer


class RecordingThrottle(AuthThrottle):
    """Records the client IP each login/register attempt is counted against."""

    def __init__(self) -> None:
        super().__init__()
        self.client_ips: list[str] = []

    def check_register(self, client_ip: str) -> None:
        self.client_ips.append(client_ip)
        super().check_register(client_ip)

    def check_login(self, client_ip: str, email: str) -> None:
        self.client_ips.append(client_ip)
        super().check_login(client_ip, email)


def throttle_ips(fake: FakeGateway, headers: dict[str, str], **overrides: Any) -> list[str]:
    """The client IPs one login and one register with `headers` are throttled under."""
    app = create_app(make_settings(**overrides))
    throttle = RecordingThrottle()
    app.dependency_overrides[get_gateway] = lambda: fake
    app.dependency_overrides[get_auth_throttle] = lambda: throttle
    with TestClient(app) as client:
        attempt_login(client, headers=headers)
        client.post("/api/auth/register", json=CREDS, headers=headers)
    return throttle.client_ips


def test_forwarded_headers_are_ignored_by_default(fake: FakeGateway) -> None:
    spoofed = {
        "X-Vercel-Forwarded-For": "198.51.100.9",
        "X-Forwarded-For": "198.51.100.9",
        "X-Real-IP": "198.51.100.9",
    }
    assert throttle_ips(fake, spoofed) == [PEER, PEER]


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"X-Vercel-Forwarded-For": "198.51.100.9"}, "198.51.100.9"),
        ({"X-Vercel-Forwarded-For": " 198.51.100.9 , 203.0.113.7"}, "198.51.100.9"),  # first
        ({"X-Vercel-Forwarded-For": "2001:DB8:0::1"}, "2001:db8::1"),  # canonical IPv6
        ({"X-Vercel-Forwarded-For": "not-an-ip"}, PEER),
        ({"X-Vercel-Forwarded-For": "198.51.100.9:443"}, PEER),
        ({"X-Vercel-Forwarded-For": ", 198.51.100.9"}, PEER),  # the first value is empty
        ({"X-Vercel-Forwarded-For": ""}, PEER),
        ({"X-Forwarded-For": "198.51.100.9", "X-Real-IP": "198.51.100.9"}, PEER),  # not trusted
        ({}, PEER),  # header missing
    ],
)
def test_trusted_client_ip_header(
    fake: FakeGateway, headers: dict[str, str], expected: str
) -> None:
    ips = throttle_ips(fake, headers, trusted_client_ip_header=VERCEL_IP_HEADER)
    assert ips == [expected, expected]


def test_trusted_header_gives_clients_behind_one_proxy_their_own_cap(
    fake: FakeGateway, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(make_settings(trusted_client_ip_header=VERCEL_IP_HEADER))
    app.dependency_overrides[get_gateway] = lambda: fake
    first = {"X-Vercel-Forwarded-For": "198.51.100.9"}
    second = {"X-Vercel-Forwarded-For": "203.0.113.7"}
    with TestClient(app) as client, caplog.at_level(logging.INFO):
        for n in range(20):
            assert attempt_login(client, f"nobody{n}@example.com", headers=first).status_code == 401
        assert attempt_login(client, headers=first).status_code == 429
        assert attempt_login(client, headers=second).status_code == 401  # same peer, own cap
    assert "client limit" in caplog.text
    assert "198.51.100.9" not in caplog.text


def test_throttle_can_be_disabled(fake: FakeGateway) -> None:
    app = create_app(make_settings(auth_throttle_enabled=False))
    app.dependency_overrides[get_gateway] = lambda: fake
    with TestClient(app) as client:
        for _ in range(25):
            assert attempt_login(client).status_code == 401

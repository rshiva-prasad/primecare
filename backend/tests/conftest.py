from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.cookies import ACCESS_COOKIE, REFRESH_COOKIE
from app.deps import get_gateway
from app.main import create_app
from tests.fakes import FakeGateway

ENV_NAMES = (
    "SUPABASE_URL",
    "SUPABASE_PUBLISHABLE_KEY",
    "APP_ENV",
    "COOKIE_SECURE",
    "ALLOWED_ORIGINS",
    "SUPABASE_TIMEOUT_SECONDS",
    "AUTH_THROTTLE_ENABLED",
    "TRUSTED_CLIENT_IP_HEADER",
)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """`pipenv run` exports backend/.env; tests must never see real configuration."""
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "supabase_url": "https://example-ref.supabase.co",
        "supabase_publishable_key": "sb_publishable_test",
        "app_env": "test",
        "cookie_secure": False,
        "allowed_origins": ["http://127.0.0.1:5173", "http://localhost:5173"],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def fake() -> FakeGateway:
    return FakeGateway()


@pytest.fixture
def app(settings: Settings, fake: FakeGateway) -> FastAPI:
    application = create_app(settings)
    application.dependency_overrides[get_gateway] = lambda: fake
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def set_session(client: TestClient, access: str | None, refresh: str | None = None) -> None:
    client.cookies.clear()
    if access is not None:
        client.cookies.set(ACCESS_COOKIE, access, path="/api")
    if refresh is not None:
        client.cookies.set(REFRESH_COOKIE, refresh, path="/api")


@pytest.fixture
def login(client: TestClient, fake: FakeGateway) -> Callable[..., Any]:
    """Create a user (optionally with patient details) and put its session cookies on the client."""

    def _login(with_patient: bool = True, email: str = "pat@example.com") -> Any:
        user = fake.users.get(email) or fake.add_user(email)
        if with_patient:
            fake.patients[user.id] = {
                "id": user.id,
                "first_name": "Pat",
                "last_name": "Lee",
                "mobile": "+61 400 000 000",
                "email": email,
            }
        session = fake.login(email)
        set_session(client, session.access_token, session.refresh_token)
        return session

    return _login

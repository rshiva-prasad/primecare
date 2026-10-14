import base64
import json

import pytest
from pydantic import ValidationError

from app.config import BACKEND_DIR, Settings, get_settings, is_privileged_key


def jwt_with(payload: dict[str, str]) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{body}.signature"


def test_defaults_without_environment() -> None:
    settings = Settings(_env_file=None)
    assert settings.supabase_url is None
    assert settings.supabase_publishable_key is None
    assert settings.supabase_configured is False
    assert settings.cookie_secure is True  # secure by default
    assert settings.is_development is False
    assert settings.allowed_origins == ["http://127.0.0.1:5173", "http://localhost:5173"]
    assert settings.supabase_timeout_seconds == 10
    assert settings.auth_throttle_enabled is True  # on by default
    assert settings.trusted_client_ip_header is None  # forwarded headers ignored by default


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", " https://ref.supabase.co/ ")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_abc")
    monkeypatch.setenv("APP_ENV", " Development ")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://a.test:1/, ,http://b.test:2")
    monkeypatch.setenv("SUPABASE_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("AUTH_THROTTLE_ENABLED", "false")
    monkeypatch.setenv("TRUSTED_CLIENT_IP_HEADER", " X-Vercel-Forwarded-For ")
    settings = Settings(_env_file=None)
    assert settings.supabase_url == "https://ref.supabase.co"
    assert settings.supabase_publishable_key is not None
    assert settings.supabase_publishable_key.get_secret_value() == "sb_publishable_abc"
    assert "sb_publishable_abc" not in repr(settings)
    assert settings.supabase_configured is True
    assert settings.is_development is True
    assert settings.cookie_secure is False
    assert settings.allowed_origins == ["http://a.test:1", "http://b.test:2"]
    assert settings.supabase_timeout_seconds == 3.5
    assert settings.auth_throttle_enabled is False
    assert settings.trusted_client_ip_header == "x-vercel-forwarded-for"


def test_blank_values_mean_unconfigured() -> None:
    settings = Settings(_env_file=None, supabase_url="  ", supabase_publishable_key="")
    assert settings.supabase_configured is False


def test_blank_trusted_client_ip_header_means_unset() -> None:
    assert Settings(_env_file=None, trusted_client_ip_header="  ").trusted_client_ip_header is None


@pytest.mark.parametrize(
    "header",
    [
        "x vercel-forwarded-for",
        "x-vercel-forwarded-for:",
        "x-forwarded-for,x-real-ip",
        "x-real-ip\r\nset-cookie",
        "x-client-ïp",
    ],
)
def test_rejects_invalid_trusted_client_ip_header(header: str) -> None:
    with pytest.raises(ValidationError, match="TRUSTED_CLIENT_IP_HEADER must be an HTTP header"):
        Settings(_env_file=None, trusted_client_ip_header=header)


def test_rejects_non_http_url() -> None:
    with pytest.raises(ValidationError, match="SUPABASE_URL must be an http"):
        Settings(_env_file=None, supabase_url="ftp://ref.supabase.co")


@pytest.mark.parametrize(
    "key", ["sb_secret_abc123", jwt_with({"role": "service_role", "iss": "supabase"})]
)
def test_rejects_privileged_keys_without_echoing_them(key: str) -> None:
    with pytest.raises(ValidationError) as info:
        Settings(_env_file=None, supabase_publishable_key=key)
    assert "never a secret or service_role key" in str(info.value)
    assert key not in str(info.value)


def test_is_privileged_key() -> None:
    assert is_privileged_key("sb_secret_x")
    assert is_privileged_key(jwt_with({"role": "service_role"}))
    assert not is_privileged_key(jwt_with({"role": "anon"}))
    assert not is_privileged_key("sb_publishable_x")
    assert not is_privileged_key("a.!!!notbase64!!!.c")
    assert not is_privileged_key("a." + base64.urlsafe_b64encode(b"[1]").decode() + ".c")


def test_get_settings_is_cached_and_env_file_is_backend_relative() -> None:
    assert get_settings() is get_settings()
    assert Settings.model_config["env_file"] == BACKEND_DIR / ".env"
    assert BACKEND_DIR.name == "backend"

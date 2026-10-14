"""Application settings loaded from environment variables and backend/.env."""

import base64
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ALLOWED_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")
_HTTP_URL = re.compile(r"^https?://[^\s/]+")
# An HTTP field name (RFC 9110 token), lowercased.
_HEADER_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9a-z-]+")


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def is_privileged_key(key: str) -> bool:
    """True for keys that bypass RLS: new-style secret keys or a legacy service_role JWT."""
    if key.startswith("sb_secret_"):
        return True
    parts = key.split(".")
    if len(parts) != 3:
        return False
    try:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("role") == "service_role"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    supabase_url: str | None = None
    supabase_publishable_key: SecretStr | None = None
    app_env: str = "production"
    cookie_secure: bool = True
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_ORIGINS)
    )
    supabase_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    # Login/register throttle (app/throttle.py). On by default; only test harnesses turn it off.
    auth_throttle_enabled: bool = True
    # Header that a proxy in front of this app overwrites with the client's IP, used by the
    # throttle instead of the socket peer (on Vercel: x-vercel-forwarded-for). Unset by default, so
    # forwarded headers are ignored. Never set it for a header clients can send unmodified.
    trusted_client_ip_header: str | None = None

    @field_validator("supabase_url", mode="before")
    @classmethod
    def _clean_url(cls, value: Any) -> Any:
        value = _blank_to_none(value)
        return value.rstrip("/") if isinstance(value, str) else value

    @field_validator("supabase_url")
    @classmethod
    def _check_url(cls, value: str | None) -> str | None:
        if value is not None and not _HTTP_URL.match(value):
            raise ValueError("SUPABASE_URL must be an http(s) URL.")
        return value

    @field_validator("supabase_publishable_key", mode="before")
    @classmethod
    def _clean_key(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("supabase_publishable_key")
    @classmethod
    def _reject_privileged_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and is_privileged_key(value.get_secret_value()):
            raise ValueError(
                "SUPABASE_PUBLISHABLE_KEY must be the publishable (anon) key, "
                "never a secret or service_role key."
            )
        return value

    @field_validator("app_env", mode="before")
    @classmethod
    def _clean_env(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: Any) -> Any:
        items = value.split(",") if isinstance(value, str) else value
        if not isinstance(items, list | tuple):
            return value
        return [str(item).strip().rstrip("/") for item in items if str(item).strip()]

    @field_validator("trusted_client_ip_header", mode="before")
    @classmethod
    def _clean_header(cls, value: Any) -> Any:
        value = _blank_to_none(value)
        return value.lower() if isinstance(value, str) else value

    @field_validator("trusted_client_ip_header")
    @classmethod
    def _check_header(cls, value: str | None) -> str | None:
        if value is not None and not _HEADER_NAME.fullmatch(value):
            raise ValueError("TRUSTED_CLIENT_IP_HEADER must be an HTTP header name.")
        return value

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_publishable_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()

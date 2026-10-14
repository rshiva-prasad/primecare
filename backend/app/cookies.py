"""Session cookies: HttpOnly, SameSite=Lax, scoped to /api."""

from starlette.responses import Response

ACCESS_COOKIE = "pc_access"
REFRESH_COOKIE = "pc_refresh"
COOKIE_PATH = "/api"
REFRESH_MAX_AGE = 7 * 24 * 60 * 60
DEFAULT_ACCESS_MAX_AGE = 60 * 60


def set_session_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    expires_in: int | None,
    secure: bool,
) -> None:
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=expires_in if expires_in and expires_in > 0 else DEFAULT_ACCESS_MAX_AGE,
        path=COOKIE_PATH,
        secure=secure,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=REFRESH_MAX_AGE,
        path=COOKIE_PATH,
        secure=secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookies(response: Response, *, secure: bool) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(name, path=COOKIE_PATH, secure=secure, httponly=True, samesite="lax")


def session_cookie_headers(
    *, access_token: str, refresh_token: str, expires_in: int | None, secure: bool
) -> list[str]:
    """Set-Cookie header values for a session, for code that only has raw ASGI headers."""
    carrier = Response()
    set_session_cookies(
        carrier,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        secure=secure,
    )
    return [value.decode("latin-1") for key, value in carrier.raw_headers if key == b"set-cookie"]

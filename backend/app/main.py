"""App factory: middleware, exception handlers and router wiring."""

import logging
import traceback
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import Settings, get_settings
from app.cookies import clear_session_cookies, session_cookie_headers
from app.deps import REFRESHED_SESSION_STATE
from app.errors import AppError, NotAuthenticated
from app.gateway import AuthResult, SupabaseGateway
from app.routers import appointments, auth, doctors, health, patients
from app.schemas import VALIDATION_DETAIL, field_errors
from app.throttle import AuthThrottle

logger = logging.getLogger(__name__)

API_PREFIX = "/api"
DOCS_PATH = f"{API_PREFIX}/docs"
OPENAPI_PATH = f"{API_PREFIX}/openapi.json"
MAX_BODY_BYTES = 16 * 1024
STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
UNEXPECTED_ERROR = "Something went wrong. Please try again."

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
API_CSP = "default-src 'none'; frame-ancestors 'none'"
# Swagger UI (development only) loads its bundle from jsDelivr and boots with an inline script.
DOCS_CSP = (
    "default-src 'none'; "
    "script-src 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)


def _json_error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status_code)


def _session_cookies(session: object, *, secure: bool) -> list[str]:
    """Set-Cookie values for a session rotated by get_current_user during this request."""
    if not isinstance(session, AuthResult) or not session.access_token or not session.refresh_token:
        return []
    return session_cookie_headers(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in,
        secure=secure,
    )


class SecurityMiddleware:
    """Request hygiene (JSON-only writes, Origin allow-list, body size), security headers,
    rotated-session cookies, and a last-resort 500 that never leaks internals."""

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self.app = app
        self.allowed_origins = frozenset(settings.allowed_origins)
        self.cookie_secure = settings.cookie_secure
        self.docs_enabled = settings.is_development

    def _reject(self, method: str, headers: Headers) -> JSONResponse | None:
        if method in STATE_CHANGING_METHODS:
            media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if media_type != "application/json":
                return _json_error(415, "Requests must be sent as JSON.")
        origin = headers.get("origin")
        if origin is not None and origin.rstrip("/") not in self.allowed_origins:
            return _json_error(403, "This request is not allowed from this origin.")
        length = headers.get("content-length")
        if length is not None and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return _json_error(413, "The request body is too large.")
        return None

    def _csp(self, path: str) -> str:
        return DOCS_CSP if self.docs_enabled and path == DOCS_PATH else API_CSP

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # Created up front so request.state in the endpoint shares this exact dict.
        state = scope.setdefault("state", {})
        csp = self._csp(scope["path"])
        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
                headers["Content-Security-Policy"] = csp
                if message["status"] != 401:
                    rotated = state.get(REFRESHED_SESSION_STATE)
                    for value in _session_cookies(rotated, secure=self.cookie_secure):
                        headers.append("set-cookie", value)
            await send(message)

        rejection = self._reject(scope["method"], Headers(scope=scope))
        if rejection is not None:
            await rejection(scope, receive, send_wrapper)
            return
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if started:
                raise
            frame = traceback.extract_tb(exc.__traceback__)[-1:]
            where = f"{frame[0].filename}:{frame[0].lineno}" if frame else "unknown"
            # Type and location only: messages can carry user data or upstream detail.
            logger.error("Unhandled %s at %s", type(exc).__name__, where)
            await _json_error(500, UNEXPECTED_ERROR)(scope, receive, send_wrapper)


def _register_exception_handlers(app: FastAPI, settings: Settings) -> None:
    async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
        error = cast(AppError, exc)  # registered for AppError only
        response = _json_error(error.status_code, error.message)
        if isinstance(error, NotAuthenticated):
            clear_session_cookies(response, secure=settings.cookie_secure)
        return response

    async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
        errors = cast(RequestValidationError, exc).errors()
        return JSONResponse(
            {"detail": VALIDATION_DETAIL, "fields": field_errors(errors)}, status_code=422
        )

    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    docs = settings.is_development
    app = FastAPI(
        title="PrimeCare Clinic API",
        version="1.0.0",
        docs_url=DOCS_PATH if docs else None,
        openapi_url=OPENAPI_PATH if docs else None,
        redoc_url=None,
        swagger_ui_oauth2_redirect_url=None,
    )
    app.state.settings = settings
    app.state.gateway = SupabaseGateway(settings)
    app.state.auth_throttle = AuthThrottle(enabled=settings.auth_throttle_enabled)
    _register_exception_handlers(app, settings)

    # add_middleware prepends, so SecurityMiddleware (added last) is the outermost layer and also
    # decorates the body-limit middleware's responses.
    app.add_middleware(RequestBodyLimitMiddleware, max_body_size=MAX_BODY_BYTES)
    app.add_middleware(SecurityMiddleware, settings=settings)

    for module in (health, auth, patients, doctors, appointments):
        app.include_router(module.router, prefix=API_PREFIX)
    return app


app = create_app()
